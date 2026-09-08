"""Read the Pskem delivery of workbooks into the project's station and basin frame.

Five spreadsheets arrived as station printouts rather than data: merged title rows,
Roman month numerals, one block per variable or per year, and totals interleaved
with observations. This build turns them into long-format tables keyed the way the
rest of the project is keyed - station id, year, month, variable, value - and
resolves each station to the level-12 basin it stands in.

Nothing here is new geography. Every station already exists in the ontology, so the
delivery is *mapped* rather than catalogued afresh:

    Пскем 2020-2024.xlsx      -> uz:station/meteo-419704   Пскем
    Пскем 2010-2019.xlsx      -> uz:station/meteo-419704   Пскем, and
                                 uz:station/meteo-413694   Ташкент
    Ойгаинг 2020-2022.xlsx    -> uz:station/meteo-422709   Ойгаинг
    Discharge_...Monthly.xlsx -> uz:station/gauge-16290    р. Пскем (с. Муллала)
    Пскем_2023.xls            -> a glacier inventory, not a station series

The workbooks disagree with each other about the same station: the 2010-2019 file
and the 2020-2024 file overlap nowhere in years, but the older one carries only
mean temperature and precipitation while the newer carries twenty variables. Both
are kept, and every row records which workbook it came from, because a series
stitched from two sources without saying so is the kind of thing nobody can audit
later.

    python PIPELINES/build_pskem_observations.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "storage"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
ENTITIES = ROOT / "ONTOLOGY/instances/entities.json"

METEO_CSV = PUBLISHED_DIR / "pskem-station-monthly.csv"
METEO_JSON = PUBLISHED_DIR / "pskem-station-monthly.json"
DISCHARGE_DAILY = PUBLISHED_DIR / "pskem-discharge-daily.csv"
DISCHARGE_MONTHLY = PUBLISHED_DIR / "pskem-discharge-monthly.csv"
DISCHARGE_JSON = PUBLISHED_DIR / "pskem-discharge-monthly.json"
GLACIERS_CSV = PUBLISHED_DIR / "pskem-glaciers.csv"
GLACIERS_GEOJSON = PUBLISHED_DIR / "pskem-glaciers.geojson"
STATION_LINKS = PUBLISHED_DIR / "pskem-station-basin-links.csv"
MANIFEST = PUBLISHED_DIR / "pskem-observations.manifest.json"

# Which workbook describes which station. The station ids are the ones already in
# the graph; this build never mints a station.
STATIONS = {
    "meteo-419704": {"label": "Пскем", "role": "meteorological"},
    "meteo-422709": {"label": "Ойгаинг", "role": "meteorological"},
    "meteo-413694": {"label": "Ташкент", "role": "meteorological"},
    "gauge-16290": {"label": "р. Пскем (с. Муллала)", "role": "river gauge"},
}

# The block headings in the two modern workbooks, decoded once. The unit travels
# in the heading itself, so it is parsed rather than assumed.
VARIABLES = {
    "средняя температура воздуха": ("air_temperature_mean", "°C"),
    "максимальная температура воздуха": ("air_temperature_max", "°C"),
    "минимальная температура воздуха": ("air_temperature_min", "°C"),
    "средняя температура поверхности почвы": ("soil_surface_temperature_mean", "°C"),
    "максимальная температура поверхности почвы": ("soil_surface_temperature_max", "°C"),
    "минимальная температура поверхности почвы": ("soil_surface_temperature_min", "°C"),
    "минимальная температура точки росы": ("dew_point_min", "°C"),
    "среднее парциальное давление водяного пара": ("vapour_pressure_mean", "hPa"),
    "средняя относительная влажность воздуха": ("relative_humidity_mean", "%"),
    "минимальная  относительная влажность воздуха": ("relative_humidity_min", "%"),
    "минимальная относительная влажность воздуха": ("relative_humidity_min", "%"),
    "средний дефицит насыщения": ("saturation_deficit_mean", "hPa"),
    "максимальный дефицит насыщения": ("saturation_deficit_max", "hPa"),
    "среднее атмосферное давление на уровне станции": ("station_pressure_mean", "hPa"),
    "средняя скорость ветра": ("wind_speed_mean", "m/s"),
    "максимальная скорость ветра (порыв)": ("wind_gust_max", "m/s"),
    "количество осадков": ("precipitation_total", "mm"),
    "максимальное количество осадков за сутки": ("precipitation_max_daily", "mm"),
    "максимальная высота снежного покрова": ("snow_depth_max", "cm"),
    "количество дней со снежным покровом": ("snow_cover_days", "days"),
}

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
         "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}

# "ND" is the delivery's own no-data marker and appears mid-series in 2014. It has
# to stay a gap: read as text it would poison a numeric column, read as zero it
# would claim a January in the Pskem valley averaged 0 °C.
NO_DATA = {"nd", "н/д", "-", "—", ""}

# But a dash does not always mean "not measured". In the accumulation and count
# blocks it means nothing fell, and the workbook proves it: the twelve monthly
# precipitation cells for 2022 read 159, 41.4, 318.3, 31, 53.2, 33.1, -, 5.3, -,
# 79.4, 204.5, 48.9 and the printed annual total is 974.1, which is exactly their
# sum with the dashes counted as zero. Publishing those months as gaps would throw
# away two real observations a year, so for these variables a dash becomes 0 and
# for every other variable it stays missing. check_precipitation_totals() re-runs
# that arithmetic on every year at build time rather than trusting this note.
ZERO_WHEN_ABSENT = {
    "precipitation_total", "precipitation_max_daily",
    "snow_depth_max", "snow_cover_days",
}
DASH = {"-", "—"}

MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_json(path: Path, payload: object, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=indent,
                  separators=(",", ":") if indent is None else None)
        handle.write("\n")
    os.replace(temporary, path)


def number(value):
    """A float, or None for a blank or an explicit no-data marker."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if float(value) != float(value) else float(value)
    text = str(value).strip().replace(",", ".")
    if text.lower() in NO_DATA:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean(value) -> str:
    return "" if value is None else str(value).strip()


def variable_for(heading: str):
    """Decode a block heading into a column name and its unit."""
    text = re.sub(r"\s+", " ", heading).strip()
    name = text.split(",")[0].strip().lower()
    unit = text.split(",")[-1].strip() if "," in text else ""
    match = VARIABLES.get(name)
    if match is None:
        return None
    # The unit comes from the decoded table, never from the heading. The headings
    # mix alphabets - "mm" in one workbook and "мм" in another for the same
    # column - and a variable that carries two spellings of one unit cannot be
    # grouped or charted.
    del unit
    return match


def read_station_basins():
    """Level-12 basin for each station, by point-in-polygon on the two systems."""
    path = BASIN_SOURCE / "hydroatlas-level12-full-basins.geojson"
    entities = json.loads(ENTITIES.read_text(encoding="utf-8"))["entities"]
    located = {}
    for entity in entities:
        key = entity["id"].split("/")[-1]
        if key in STATIONS and entity.get("longitude") is not None:
            located[key] = (float(entity["longitude"]), float(entity["latitude"]))
    if not path.exists():
        return located, {}

    try:
        from shapely.geometry import Point, shape
        from shapely.strtree import STRtree
    except ImportError:
        return located, {}

    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    geometries, records = [], []
    for feature in features:
        geometry = shape(feature["geometry"])
        geometries.append(geometry if geometry.is_valid else geometry.buffer(0))
        records.append(feature["properties"])
    tree = STRtree(geometries)

    placed = {}
    for key, (longitude, latitude) in located.items():
        point = Point(longitude, latitude)
        for index in tree.query(point, predicate="intersects"):
            if geometries[int(index)].contains(point):
                props = records[int(index)]
                placed[key] = {
                    "hybas_id": int(props["HYBAS_ID"]),
                    "system_id": props["system_id"],
                    "in_headwater_formation": int(bool(props["in_headwater_formation"])),
                }
                break
    return located, placed


def read_modern_meteo(path: Path, sheet: str, station: str, rows: list[dict], retrieved: str):
    """The 2020-2024 and 2020-2022 layout: one titled block per variable."""
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    grid = list(workbook[sheet].iter_rows(values_only=True))
    workbook.close()

    current = None
    for row in grid:
        heading = clean(row[0])
        decoded = variable_for(heading) if heading else None
        if decoded:
            current = decoded
            continue
        if current is None:
            continue
        year = number(row[0])
        # A block's data rows start with a four-digit year; the two header rows
        # under the title start with "Год" or nothing, so they fall out here.
        if year is None or not (1900 < year < 2100):
            continue
        for month in range(1, 13):
            raw = row[month] if month < len(row) else None
            value = number(raw)
            if value is None and current[0] in ZERO_WHEN_ABSENT and clean(raw) in DASH:
                value = 0.0
            if value is None:
                continue
            rows.append({
                "station_id": f"uz:station/{station}",
                "station_key": station.split("-")[-1],
                "station_label": STATIONS[station]["label"],
                "year": int(year), "month": month,
                "variable": current[0], "value": f"{value:g}", "unit": current[1],
                "source_file": path.name, "source_sheet": sheet,
                "retrieved_at": retrieved,
            })


def check_precipitation_totals(path: Path, sheet: str):
    """Re-derive the workbook's printed annual precipitation totals.

    This is the evidence for reading a dash as zero rather than as a gap. The
    block prints a "Сумма за год" column; if the twelve monthly cells sum to it
    only when dashes count as zero, the dash means a dry month. The result is
    published in the manifest so the decision can be checked, not just believed.
    """
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    grid = list(workbook[sheet].iter_rows(values_only=True))
    workbook.close()
    agree = disagree = 0
    inside = False
    for row in grid:
        heading = clean(row[0])
        decoded = variable_for(heading) if heading else None
        if decoded:
            # Only a decodable block title opens or closes a block. The two rows
            # under it start with "Год" and with nothing, and treating those as
            # headings closed the block again before a single value was read.
            inside = decoded[0] == "precipitation_total"
            continue
        if not inside:
            continue
        year = number(row[0])
        if year is None or not (1900 < year < 2100):
            continue
        months = [number(row[month]) or 0.0 for month in range(1, 13) if month < len(row)]
        printed = number(row[13]) if len(row) > 13 else None
        if printed is None:
            continue
        if abs(sum(months) - printed) < 0.05:
            agree += 1
        else:
            disagree += 1
    return agree, disagree


def read_legacy_meteo(path: Path, rows: list[dict], retrieved: str):
    """The 2010-2019 layout: two side-by-side blocks, temperature then precipitation.

    This workbook uses Uzbek headings (йиллар, температура, осадка) and puts the
    two variables in one row rather than in separate blocks, so the columns are
    located by their heading rather than by a fixed offset.
    """
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet, station in (("Пскем", "meteo-419704"), ("Тошкент", "meteo-413694")):
        if sheet not in workbook.sheetnames:
            continue
        grid = list(workbook[sheet].iter_rows(values_only=True))
        # Find the row that labels the year columns; the two "йиллар" cells in it
        # mark where each block begins.
        starts = []
        for row in grid:
            positions = [index for index, cell in enumerate(row) if clean(cell).lower() == "йиллар"]
            if len(positions) >= 2:
                starts = positions
                break
        if len(starts) < 2:
            continue
        blocks = [(starts[0], "air_temperature_mean", "°C"),
                  (starts[1], "precipitation_total", "mm")]
        for row in grid:
            for column, variable, unit in blocks:
                if column >= len(row):
                    continue
                year = number(row[column])
                if year is None or not (1900 < year < 2100):
                    continue
                for month in range(1, 13):
                    index = column + month
                    value = number(row[index]) if index < len(row) else None
                    if value is None:
                        continue
                    rows.append({
                        "station_id": f"uz:station/{station}",
                        "station_key": station.split("-")[-1],
                        "station_label": STATIONS[station]["label"],
                        "year": int(year), "month": month,
                        "variable": variable, "value": f"{value:g}", "unit": unit,
                        "source_file": path.name, "source_sheet": sheet,
                        "retrieved_at": retrieved,
                    })
    workbook.close()


def read_discharge(path: Path, retrieved: str):
    """Daily discharge, one block per year, months across and days down."""
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    daily, monthly = [], []
    station = "gauge-16290"
    for sheet in workbook.sheetnames:
        grid = list(workbook[sheet].iter_rows(values_only=True))
        year = None
        for index, row in enumerate(grid):
            joined = " ".join(clean(cell) for cell in row if cell is not None)
            found = re.search(r"(19|20)\d{2}", joined)
            # A block opens with a title carrying its year, and the row under it
            # is the Roman-numeral header. Both are needed to be sure this is a
            # block start rather than a stray number somewhere in the sheet.
            following = grid[index + 1] if index + 1 < len(grid) else ()
            header = [clean(cell).upper() for cell in following]
            if found and "I" in header and "XII" in header:
                year = int(found.group(0))
                columns = {ROMAN[cell]: position for position, cell in enumerate(header)
                           if cell in ROMAN}
                totals = {month: [] for month in columns}
                for data_row in grid[index + 2:]:
                    day = number(data_row[0]) if data_row else None
                    if day is None or not (1 <= day <= 31):
                        break
                    for month, position in columns.items():
                        value = number(data_row[position]) if position < len(data_row) else None
                        if value is None:
                            continue
                        daily.append({
                            "station_id": f"uz:station/{station}",
                            "station_key": station.split("-")[-1],
                            "year": year, "month": month, "day": int(day),
                            "discharge_cms": f"{value:g}",
                            "source_file": path.name, "source_sheet": sheet,
                            "retrieved_at": retrieved,
                        })
                        totals[month].append(value)
                for month in sorted(totals):
                    values = totals[month]
                    if not values:
                        continue
                    # The workbook prints its own monthly mean, but it is
                    # recomputed here from the days actually present so the
                    # published mean always matches the published series.
                    monthly.append({
                        "station_id": f"uz:station/{station}",
                        "station_key": station.split("-")[-1],
                        "year": year, "month": month,
                        "discharge_mean_cms": f"{sum(values) / len(values):.3f}",
                        "discharge_min_cms": f"{min(values):g}",
                        "discharge_max_cms": f"{max(values):g}",
                        "days_observed": len(values),
                        "days_in_month": MONTH_DAYS[month - 1] + (
                            1 if month == 2 and (year % 4 == 0 and (year % 100 or year % 400 == 0)) else 0),
                        "source_file": path.name, "source_sheet": sheet,
                        "retrieved_at": retrieved,
                    })
    workbook.close()
    return daily, monthly


def dms(value: str):
    """Decimal degrees from a 42° 05' 40.45" N string."""
    match = re.match(r"\s*(\d+)\D+(\d+)\D+([\d.]+)\D*([NSEW])", str(value).strip())
    if not match:
        return None
    degrees, minutes, seconds, hemisphere = match.groups()
    decimal = int(degrees) + int(minutes) / 60 + float(seconds) / 3600
    return -decimal if hemisphere in {"S", "W"} else decimal


def read_glaciers(path: Path, retrieved: str):
    """The 2015 Pskem glacier catalogue, delivered as a flat .xls table."""
    import xlrd
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    header = [str(sheet.cell_value(0, column)).strip() for column in range(sheet.ncols)]
    index = {name: position for position, name in enumerate(header)}
    rows = []
    for position in range(1, sheet.nrows):
        cell = lambda name: (sheet.cell_value(position, index[name]) if name in index else "")
        longitude = dms(cell("Longitude_center"))
        latitude = dms(cell("Latitude_center"))
        if longitude is None or latitude is None:
            continue
        minimum, maximum = number(cell("Z_Min")), number(cell("Z_Max"))
        rows.append({
            "glacier_key": clean(cell("Name")),
            "name": clean(cell("CatName")),
            "name_en": clean(cell("Name_ENG")),
            "morphology": clean(cell("CatType")),
            "catalogue_number": "" if number(cell("NO_CAT")) is None else f"{int(number(cell('NO_CAT')))}",
            "number_1980": "" if number(cell("NO_1980")) is None else f"{int(number(cell('NO_1980')))}",
            "country": clean(cell("Country")),
            "perimeter_m": "" if number(cell("Perimeter")) is None else f"{number(cell('Perimeter')):.1f}",
            "length_m": "" if number(cell("MY_LENGTH")) is None else f"{number(cell('MY_LENGTH')):.1f}",
            "aspect": clean(cell("MY_ASPECT")),
            "elevation_min_m": "" if minimum is None else f"{minimum:.1f}",
            "elevation_max_m": "" if maximum is None else f"{maximum:.1f}",
            "elevation_range_m": "" if None in (minimum, maximum) else f"{maximum - minimum:.1f}",
            "longitude": f"{longitude:.6f}",
            "latitude": f"{latitude:.6f}",
            "source_file": path.name,
            "retrieved_at": retrieved,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        import openpyxl  # noqa: F401
        import xlrd  # noqa: F401
    except ImportError:
        raise SystemExit("This build needs openpyxl and xlrd: python -m pip install openpyxl xlrd")

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if not SOURCE_DIR.exists():
        raise SystemExit(f"Missing {SOURCE_DIR.relative_to(ROOT)}")

    located, placed = read_station_basins()
    print(f"Pskem | {len(located)} stations located, {len(placed)} resolved to a level-12 basin")

    meteo: list[dict] = []
    plan = [
        ("Пскем 2020-2024.xlsx", "Пскем ", "meteo-419704"),
        ("Ойгаинг 2020-2022.xlsx", "Ойгаинг", "meteo-422709"),
    ]
    totals_agree = totals_disagree = 0
    for name, sheet, station in plan:
        path = SOURCE_DIR / name
        if not path.exists():
            print(f"  skipped, absent: {name}")
            continue
        before = len(meteo)
        read_modern_meteo(path, sheet, station, meteo, retrieved)
        agree, disagree = check_precipitation_totals(path, sheet)
        totals_agree += agree
        totals_disagree += disagree
        print(f"  {name}: {len(meteo) - before:,} monthly values "
              f"(annual precipitation totals reconciled {agree}/{agree + disagree})")

    legacy = SOURCE_DIR / "Пскем 2010-2019.xlsx"
    if legacy.exists():
        before = len(meteo)
        read_legacy_meteo(legacy, meteo, retrieved)
        print(f"  {legacy.name}: {len(meteo) - before:,} monthly values")

    meteo.sort(key=lambda row: (row["station_key"], row["variable"], row["year"], row["month"]))
    write_csv(METEO_CSV, list(meteo[0]) if meteo else ["station_id"], meteo)

    daily, monthly = [], []
    discharge_path = SOURCE_DIR / "Discharge_Pskem_Muallala_Monthly.xlsx"
    if discharge_path.exists():
        daily, monthly = read_discharge(discharge_path, retrieved)
        print(f"  {discharge_path.name}: {len(daily):,} daily and {len(monthly):,} monthly values")
        daily.sort(key=lambda row: (row["year"], row["month"], row["day"]))
        monthly.sort(key=lambda row: (row["year"], row["month"]))
        write_csv(DISCHARGE_DAILY, list(daily[0]), daily)
        write_csv(DISCHARGE_MONTHLY, list(monthly[0]), monthly)

    glaciers = []
    glacier_path = SOURCE_DIR / "Пскем_2023.xls"
    if glacier_path.exists():
        glaciers = read_glaciers(glacier_path, retrieved)
        print(f"  {glacier_path.name}: {len(glaciers):,} glaciers")
        write_csv(GLACIERS_CSV, list(glaciers[0]), glaciers)
        write_json(GLACIERS_GEOJSON, {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [float(row["longitude"]), float(row["latitude"])]},
                "properties": {key: value for key, value in row.items()
                               if key not in {"longitude", "latitude", "retrieved_at"}},
            } for row in glaciers],
        })

    links = [{
        "station_id": f"uz:station/{key}",
        "station_key": key.split("-")[-1],
        "station_label": STATIONS[key]["label"],
        "station_role": STATIONS[key]["role"],
        "longitude": f"{located[key][0]:.6f}",
        "latitude": f"{located[key][1]:.6f}",
        "basin_level": 12,
        "hybas_id": placed[key]["hybas_id"] if key in placed else "",
        "system_id": placed[key]["system_id"] if key in placed else "",
        "in_headwater_formation": placed[key]["in_headwater_formation"] if key in placed else "",
        "method": "station coordinate inside a level-12 basin polygon",
        "retrieved_at": retrieved,
    } for key in sorted(located)]
    write_csv(STATION_LINKS, list(links[0]), links)

    # The JSON projections the browser reads: indexed by station and variable so a
    # chart does not have to scan a long table to draw one series.
    series: dict = {}
    for row in meteo:
        station = series.setdefault(row["station_id"], {
            "label": row["station_label"], "stationKey": row["station_key"], "variables": {},
        })
        variable = station["variables"].setdefault(row["variable"], {"unit": row["unit"], "years": {}})
        variable["years"].setdefault(str(row["year"]), [None] * 12)[row["month"] - 1] = float(row["value"])
    write_json(METEO_JSON, {
        "version": "1.0", "generatedAt": retrieved,
        "note": "Monthly station observations, one array of twelve months per year. "
                "null is a month the workbook left blank or marked ND.",
        "stations": series,
    })

    discharge_series: dict = {}
    for row in monthly:
        year = discharge_series.setdefault(str(row["year"]), {"mean": [None] * 12, "daysObserved": [0] * 12})
        year["mean"][row["month"] - 1] = float(row["discharge_mean_cms"])
        year["daysObserved"][row["month"] - 1] = row["days_observed"]
    write_json(DISCHARGE_JSON, {
        "version": "1.0", "generatedAt": retrieved,
        "station": "uz:station/gauge-16290",
        "label": STATIONS["gauge-16290"]["label"],
        "unit": "m3/s",
        "note": "Monthly means recomputed from the daily series in the workbook, "
                "not copied from its printed average row.",
        "years": discharge_series,
    })

    variables = sorted({row["variable"] for row in meteo})
    years = sorted({int(row["year"]) for row in meteo})
    # Values far outside a plausible range for their column. These are not
    # corrected - they are reported, because a decimal point that slipped in the
    # source is the source's fact, not this build's to overwrite.
    suspect = [row for row in daily
               if float(row["discharge_cms"]) < 5 or float(row["discharge_cms"]) > 2000]
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "station_observation",
        "spatialScope": "station",
        "sources": [{"file": name, "station": f"uz:station/{station}"}
                    for name, _, station in plan] + [
            {"file": legacy.name, "station": "uz:station/meteo-419704 and uz:station/meteo-413694"},
            {"file": discharge_path.name, "station": "uz:station/gauge-16290"},
            {"file": glacier_path.name, "station": None, "note": "glacier inventory, not a series"},
        ],
        "counts": {
            "monthlyStationValues": len(meteo),
            "variables": len(variables),
            "dailyDischargeValues": len(daily),
            "monthlyDischargeValues": len(monthly),
            "glaciers": len(glaciers),
            "stationsResolvedToBasin": len(placed),
        },
        "variables": variables,
        "precipitationTotalsReconciled": {
            "agree": totals_agree, "disagree": totals_disagree,
            "test": "twelve monthly cells, dashes read as zero, summed against the "
                    "workbook's printed annual total to within 0.05 mm",
        },
        "temporalCoverage": {"start": years[0] if years else None, "end": years[-1] if years else None},
        "dischargeCoverage": {
            "start": min((row["year"] for row in monthly), default=None),
            "end": max((row["year"] for row in monthly), default=None),
        },
        "stations": [{
            "id": row["station_id"], "label": row["station_label"], "role": row["station_role"],
            "hybasIdLevel12": row["hybas_id"] or None, "system": row["system_id"] or None,
            "inHeadwaterFormation": bool(row["in_headwater_formation"]) if row["in_headwater_formation"] != "" else None,
        } for row in links],
        "outputs": {
            "meteoCSV": str(METEO_CSV.relative_to(ROOT)).replace("\\", "/"),
            "meteoJSON": str(METEO_JSON.relative_to(ROOT)).replace("\\", "/"),
            "dischargeDailyCSV": str(DISCHARGE_DAILY.relative_to(ROOT)).replace("\\", "/"),
            "dischargeMonthlyCSV": str(DISCHARGE_MONTHLY.relative_to(ROOT)).replace("\\", "/"),
            "dischargeJSON": str(DISCHARGE_JSON.relative_to(ROOT)).replace("\\", "/"),
            "glacierCSV": str(GLACIERS_CSV.relative_to(ROOT)).replace("\\", "/"),
            "glacierGeoJSON": str(GLACIERS_GEOJSON.relative_to(ROOT)).replace("\\", "/"),
            "stationBasinLinkCSV": str(STATION_LINKS.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "Every station here already existed in the ontology. This build maps the "
            "workbooks onto those identifiers; it mints no station and moves no coordinate.",
            "The 2010-2019 workbook and the 2020-2024 workbook describe the same Pskem "
            "station but carry different variables, and they do not overlap in years. "
            "Rows record their source file so the join is never invisible.",
            "'ND' in the 2014 row of the older workbook is the delivery's no-data marker "
            "and is published as an empty cell, never as zero.",
            "A dash means two different things in these workbooks and is read as two "
            "different things. In precipitation and snow blocks it means nothing fell and "
            "becomes 0; everywhere else it means not measured and stays empty. The "
            "distinction is not a guess: summing the twelve monthly precipitation cells "
            "with dashes as zero reproduces the workbook's own printed annual total, and "
            "precipitationTotalsReconciled reports that check for every year.",
            f"{len(suspect)} daily discharge values fall outside 5-2000 m3/s and look like "
            "misplaced decimal points in the source (0.49 between two values near 50, for "
            "instance). They are published unchanged: correcting a source silently would "
            "be worse than reporting it. They are listed under suspectDailyValues.",
            "Monthly discharge means are recomputed from the days present rather than taken "
            "from the workbook's printed average, and days_observed says how many days each "
            "mean rests on. February 2001 and several other months are short.",
            "Пскем_2023.xls is not a station series despite its name: it is the 2015 Pskem "
            "glacier catalogue, 254 glaciers with centre coordinates and elevation range. It "
            "carries a perimeter but no area.",
        ],
        "suspectDailyValues": [{
            "year": row["year"], "month": row["month"], "day": row["day"],
            "value": float(row["discharge_cms"]),
        } for row in suspect],
    }
    write_json(MANIFEST, manifest, indent=1)

    print(f"  -> {len(meteo):,} station values over {len(variables)} variables, "
          f"{years[0] if years else '—'}-{years[-1] if years else '—'}")
    print(f"  -> {len(daily):,} daily discharge rows, {len(suspect)} flagged as suspect")
    print(f"  -> {len(glaciers):,} glaciers")
    print(f"  wrote {METEO_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
