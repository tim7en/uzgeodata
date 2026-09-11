"""A name bridge between two id spaces, and the limits of what it establishes."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES.build_station_crosswalk import OUT, SUMMARY, crosswalk, normalise, read


def observation(station_id, name, variable="air_temperature_mean", original=None):
    return {"station_id": station_id, "station_name": name, "province": "Tashkent",
            "station_name_original": original or name, "variable": variable}


def site(entity_id, latin, raw=None):
    return {"entity_id": entity_id, "name_latin": latin, "name_raw": raw or latin,
            "name_cyrillic": "", "longitude": "69.3", "latitude": "41.3"}


def test_a_station_code_used_as_a_name_prefix_is_not_part_of_the_name():
    assert normalise("38023Karakalpakia") == normalise("Karakalpakia")
    assert normalise(" Ak-Baytal ") == normalise("akbaytal")
    assert normalise("") == "" and normalise(None) == ""


def test_a_name_that_resolves_to_one_site_carries_its_coordinate():
    rows = crosswalk([observation("uz:station/meteo-38475", "Andijan")],
                     [site("uz:station/meteo-408724", "Andijan")])
    assert rows[0]["match_status"] == "matched_by_name"
    assert rows[0]["network_entity_id"] == "uz:station/meteo-408724"
    assert rows[0]["longitude"] and rows[0]["latitude"]
    assert rows[0]["evidence"]


def test_a_name_matching_two_sites_is_left_unresolved():
    rows = crosswalk([observation("uz:station/meteo-1", "Boz")],
                     [site("uz:station/meteo-a", "Boz"), site("uz:station/meteo-b", "Boz")])
    assert rows[0]["match_status"] == "ambiguous_name"
    assert rows[0]["candidates"] == 2
    assert not rows[0]["network_entity_id"], "no coordinate is guessed at"
    assert not rows[0]["longitude"]


def test_a_name_with_no_counterpart_is_published_as_unmatched():
    rows = crosswalk([observation("uz:station/meteo-9", "Oygaing")], [site("uz:station/meteo-z", "Nukus")])
    assert rows[0]["match_status"] == "no_name_match"
    assert rows[0]["candidates"] == 0 and not rows[0]["network_entity_id"]


def test_soil_and_air_records_at_one_place_reach_the_same_site():
    """The two deliveries name sites differently but describe the same network."""
    network = [site("uz:station/meteo-451583", "Aktumsuk")]
    rows = crosswalk([observation("uz:station/meteo-38023", "Aktumsuk"),
                      observation("uz:station/soil-aktumsuk", "Aktumsuk", "soil_temperature_mean")],
                     network)
    assert {r["match_status"] for r in rows} == {"matched_by_name"}
    assert len({r["network_entity_id"] for r in rows}) == 1


def test_the_published_crosswalk_claims_no_verified_identity():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "proposed_crosswalk_pending_review"
    assert "does not establish" in summary["meaning"]
    assert summary["matched"] + summary["ambiguous"] + summary["unmatched"] == summary["observation_stations"]
    assert summary["locatable_observations"] < summary["monthly_observations"], "coverage is partial"
    assert sum(summary["locatable_by_measure"].values()) == summary["locatable_observations"]


def test_every_matched_row_carries_a_coordinate_and_every_other_row_does_not():
    rows = read(OUT)
    assert len(rows) == 148
    for row in rows:
        if row["match_status"] == "matched_by_name":
            assert row["longitude"] and row["latitude"], row["observation_station_id"]
        else:
            assert not row["longitude"] and not row["network_entity_id"]
