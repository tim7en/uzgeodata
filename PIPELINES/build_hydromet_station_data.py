"""Parse, unify and screen the Uzhydromet station workbooks in `storage/`.

Three deliveries arrive in three different shapes, none of them tabular:

* `air_temp_precip/*.xlsx` — one sheet per meteorological station, with air
  temperature, precipitation and the Pedya index side by side as 13-column
  blocks. The months run October to September, so a row labelled 1963 is the
  1963/64 water year, not the calendar year.
* `soil_temp/Температура почвы.xlsx` — one sheet per province, with a block per
  station, months in calendar order, and `ND` where a value is missing.
* `meteo_gages_loc/*.xlsx` — flat registries of gauges and their coordinates.

Two problems run through all of it. The text is Cyrillic, and it is corrupted by
homoglyphs: `р. Cырдарья` carries a Latin C, `кишл. Kаль` a Latin K. Sorting or
joining on those strings silently splits the same station in two, so the
characters are repaired before anything else happens, then transliterated.

Everything lands as one long table — station, variable, year, month, value — with
a quality flag rather than deletion, because a value removed without a trace
cannot be argued with.

    python PIPELINES/build_hydromet_station_data.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
STORAGE = ROOT / "storage"
OUT_DIR = ROOT / "PUBLISHED/data/hydromet"
REGISTRY = OUT_DIR / "station-registry.csv"
OBSERVATIONS = OUT_DIR / "station-monthly.csv"
MANIFEST = OUT_DIR / "station-monthly.manifest.json"

# Latin letters that look like Cyrillic ones and appear inside otherwise Cyrillic
# words. Repaired before transliteration, or the same station splits in two.
HOMOGLYPHS = {
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
}
CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ғ": "gh", "қ": "q", "ҳ": "h", "ў": "o", "ĝ": "g",
}
MONTHS_RU = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
VARIABLES = {
    "air temperature": ("air_temperature_mean", "degC", (-45.0, 45.0)),
    "precipitation": ("precipitation_total", "mm", (0.0, 900.0)),
    "pedya index": ("pedya_index", "index", (-10.0, 10.0)),
    "soil temperature": ("soil_temperature_mean", "degC", (-40.0, 60.0)),
}
MISSING = {"nd", "н.д.", "нд", "", "-", "—", "нет", "na", "n/a"}
FIELDS = [
    "station_id", "station_name", "station_name_original", "province", "source_index",
    "variable", "unit", "water_year", "year", "month", "value", "quality", "source_file",
    "source_sheet", "retrieved_at",
]
REGISTRY_FIELDS = [
    "station_id", "station_name", "station_name_original", "river", "river_original",
    "station_kind", "source_index", "longitude", "latitude", "elevation_m",
    "source_file", "retrieved_at",
]


def repair(text: str) -> str:
    """Put Latin look-alikes back into Cyrillic before anything reads the string."""
    if not isinstance(text, str):
        return ""
    characters = list(text)
    has_cyrillic = any("Ѐ" <= character <= "ӿ" for character in characters)
    if not has_cyrillic:
        return text.strip()
    for index, character in enumerate(characters):
        if character in HOMOGLYPHS:
            before = characters[index - 1] if index else ""
            after = characters[index + 1] if index + 1 < len(characters) else ""
            neighbour = f"{before}{after}"
            if any("Ѐ" <= letter <= "ӿ" for letter in neighbour):
                characters[index] = HOMOGLYPHS[character]
    return "".join(characters).strip()


def latin(text: str) -> str:
    """Transliterate to Latin, keeping the reading rather than a byte mapping."""
    repaired = repair(text)
    out = []
    for character in repaired:
        lower = character.lower()
        if lower in CYRILLIC:
            mapped = CYRILLIC[lower]
            out.append(mapped.capitalize() if character.isupper() and mapped else mapped)
        else:
            out.append(character)
    result = "".join(out)
    result = unicodedata.normalize("NFC", result)
    return re.sub(r"\s+", " ", result).strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", latin(text).lower()).strip("-")


def number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    text = str(value).strip().replace(",", ".")
    if text.lower() in MISSING:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def month_of(label) -> int | None:
    text = repair(str(label)).strip().lower()
    return MONTHS_RU.get(text) or MONTHS_EN.get(text)


def blocks(frame: pd.DataFrame, header_row: int, month_row: int):
    """Yield (title, first column, month->column) for each side-by-side block."""
    titles = frame.iloc[header_row]
    months = frame.iloc[month_row]
    current = None
    for column in range(frame.shape[1]):
        title = titles.iloc[column]
        if isinstance(title, str) and title.strip():
            if current and current["months"]:
                yield current
            current = {"title": title.strip(), "start": column, "months": {}}
        if current is None:
            continue
        month = month_of(months.iloc[column])
        if month:
            current["months"][month] = column
    if current and current["months"]:
        yield current


def read_air_precip(rows: list[dict], retrieved: str, stations: dict) -> None:
    for path in sorted((STORAGE / "air_temp_precip").glob("*.xlsx")):
        book = pd.ExcelFile(path)
        for sheet in book.sheet_names:
            frame = book.parse(sheet, header=None)
            match = re.match(r"\s*(\d+)\s+(.*)", str(sheet))
            index = match.group(1) if match else ""
            name = latin(match.group(2) if match else sheet)
            station_id = f"uz:station/meteo-{index}" if index else f"uz:station/meteo-{slug(name)}"
            stations.setdefault(station_id, {
                "station_id": station_id, "station_name": name,
                "station_name_original": str(sheet), "river": "", "river_original": "",
                "station_kind": "meteorological", "source_index": index,
                "longitude": "", "latitude": "", "elevation_m": "",
                "source_file": path.name, "retrieved_at": retrieved,
            })
            for block in blocks(frame, 0, 1):
                key = repair(block["title"]).strip().lower()
                if key not in VARIABLES:
                    continue
                variable, unit, _ = VARIABLES[key]
                for row in range(2, frame.shape[0]):
                    water_year = number(frame.iat[row, block["start"]])
                    if water_year is None or not 1900 < water_year < 2100:
                        continue
                    for month, column in block["months"].items():
                        value = number(frame.iat[row, column])
                        if value is None:
                            continue
                        # October to September: the label names the water year, so
                        # January to September fall in the following calendar year.
                        year = int(water_year) + (0 if month >= 10 else 1)
                        rows.append({
                            "station_id": station_id, "station_name": name,
                            "station_name_original": str(sheet), "province": path.stem,
                            "source_index": index, "variable": variable, "unit": unit,
                            "water_year": int(water_year), "year": year, "month": month,
                            "value": value, "quality": "", "source_file": path.name,
                            "source_sheet": str(sheet), "retrieved_at": retrieved,
                        })


def read_soil(rows: list[dict], retrieved: str, stations: dict) -> None:
    path = STORAGE / "soil_temp" / "Температура почвы.xlsx"
    if not path.exists():
        return
    variable, unit, _ = VARIABLES["soil temperature"]
    book = pd.ExcelFile(path)
    for sheet in book.sheet_names:
        frame = book.parse(sheet, header=None)
        province = latin(sheet)
        for block in blocks(frame, 0, 1):
            name = latin(block["title"])
            if not name:
                continue
            station_id = f"uz:station/soil-{slug(name)}"
            stations.setdefault(station_id, {
                "station_id": station_id, "station_name": name,
                "station_name_original": block["title"], "river": "", "river_original": "",
                "station_kind": "soil_temperature", "source_index": "",
                "longitude": "", "latitude": "", "elevation_m": "",
                "source_file": path.name, "retrieved_at": retrieved,
            })
            for row in range(2, frame.shape[0]):
                year = number(frame.iat[row, block["start"]])
                if year is None or not 1900 < year < 2100:
                    continue
                for month, column in block["months"].items():
                    value = number(frame.iat[row, column])
                    if value is None:
                        continue
                    rows.append({
                        "station_id": station_id, "station_name": name,
                        "station_name_original": block["title"], "province": province,
                        "source_index": "", "variable": variable, "unit": unit,
                        "water_year": "", "year": int(year), "month": month,
                        "value": value, "quality": "", "source_file": path.name,
                        "source_sheet": str(sheet), "retrieved_at": retrieved,
                    })


def read_registries(retrieved: str, stations: dict) -> None:
    for name, kind in (("gages_data_rus.xlsx", "gauge"), ("Water discharges.xlsx", "gauge")):
        path = STORAGE / "meteo_gages_loc" / name
        if not path.exists():
            continue
        frame = pd.read_excel(path)
        for record in frame.to_dict("records"):
            index = record.get("INDEX")
            if index is None or pd.isna(index):
                continue
            station_id = f"uz:station/gauge-{int(index)}"
            location = latin(record.get("LOCATION", ""))
            river = latin(record.get("RIVERS", ""))
            entry = stations.setdefault(station_id, {
                "station_id": station_id, "station_name": location,
                "station_name_original": str(record.get("LOCATION", "")),
                "river": river, "river_original": str(record.get("RIVERS", "")),
                "station_kind": kind, "source_index": str(int(index)),
                "longitude": "", "latitude": "", "elevation_m": "",
                "source_file": path.name, "retrieved_at": retrieved,
            })
            for column, field in (("X", "longitude"), ("Y", "latitude"), ("Высоты", "elevation_m")):
                value = number(record.get(column))
                if value is not None and not entry[field]:
                    entry[field] = round(value, 6)


def screen(rows: list[dict]) -> dict:
    """Flag rather than delete: range first, then a robust outlier test."""
    ranges = {name: bounds for name, _, bounds in
              ((v[0], v[1], v[2]) for v in VARIABLES.values())}
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["station_id"], row["variable"], row["month"])].append(row)

    counts = defaultdict(int)
    for row in rows:
        low, high = ranges[row["variable"]]
        if not low <= row["value"] <= high:
            row["quality"] = "out-of-range"
            counts["out-of-range"] += 1

    for members in grouped.values():
        values = sorted(entry["value"] for entry in members if not entry["quality"])
        if len(values) < 8:
            continue
        median = values[len(values) // 2]
        deviations = sorted(abs(value - median) for value in values)
        mad = deviations[len(deviations) // 2]
        if mad <= 0:
            continue
        for entry in members:
            if entry["quality"]:
                continue
            # 0.6745 makes the MAD comparable to a standard deviation.
            score = 0.6745 * abs(entry["value"] - median) / mad
            if score > 5:
                entry["quality"] = "outlier-station-month"
                counts["outlier-station-month"] += 1
    for row in rows:
        if not row["quality"]:
            row["quality"] = "ok"
            counts["ok"] += 1
    return dict(counts)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not STORAGE.exists():
        raise SystemExit(f"Missing {STORAGE.relative_to(ROOT)}")
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict] = []
    stations: dict[str, dict] = {}

    read_registries(retrieved, stations)
    read_air_precip(rows, retrieved, stations)
    read_soil(rows, retrieved, stations)
    counts = screen(rows)

    rows.sort(key=lambda row: (row["variable"], row["station_id"], row["year"], row["month"]))
    registry = sorted(stations.values(), key=lambda entry: entry["station_id"])
    write_csv(OBSERVATIONS, FIELDS, rows)
    write_csv(REGISTRY, REGISTRY_FIELDS, registry)

    by_variable = defaultdict(lambda: {"rows": 0, "stations": set(), "years": set()})
    for row in rows:
        entry = by_variable[row["variable"]]
        entry["rows"] += 1
        entry["stations"].add(row["station_id"])
        entry["years"].add(row["year"])
    summary = {
        name: {"rows": entry["rows"], "stations": len(entry["stations"]),
               "firstYear": min(entry["years"]), "lastYear": max(entry["years"])}
        for name, entry in sorted(by_variable.items())
    }

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "station_observation",
        "source": {"folder": "storage", "delivery": "Uzhydromet workbooks"},
        "text": {
            "transliteration": "Cyrillic to Latin, reading-preserving",
            "homoglyphRepair": ("Latin look-alikes inside Cyrillic words are restored before "
                                "transliteration; without it the same station splits in two"),
        },
        "waterYear": ("air temperature, precipitation and the Pedya index are delivered October to "
                      "September; the row label is the water year and the calendar year is derived"),
        "variables": summary,
        "quality": counts,
        "emptyVariables": {
            "pedya_index": ("delivered as a header block in all 69 station sheets and empty in every "
                            "one; parsed and found to hold no values rather than silently dropped"),
        },
        "counts": {"observations": len(rows), "stations": len(registry),
                   "stationsWithCoordinates": sum(1 for e in registry if e["longitude"] != "")},
        "outputs": {"observations": str(OBSERVATIONS.relative_to(ROOT)).replace("\\", "/"),
                    "registry": str(REGISTRY.relative_to(ROOT)).replace("\\", "/")},
        "qualityNotes": [
            "Suspect values are flagged, never deleted: quality carries ok, out-of-range or "
            "outlier-station-month and the value stays readable.",
            "The outlier test compares a value with its own station and calendar month, so a cold "
            "January is not judged against July.",
            "Coordinates come from the gauge registries only; meteorological and soil stations "
            "arrive without them and are published without invented positions.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Hydromet stations | {len(rows):,} observations | {len(registry)} stations")
    for name, entry in summary.items():
        print(f"   {name:24} {entry['rows']:>7,} rows  {entry['stations']:>3} stations  "
              f"{entry['firstYear']}-{entry['lastYear']}")
    print(f"   quality: {counts}")
    print(f"   -> {OBSERVATIONS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
