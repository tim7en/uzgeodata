"""The publish gate refuses the two inconsistencies the 2026-09 review found."""
from qa.version_consistency import estimates_follow_record, matrices_follow_record

HISTORY = {"series": {"pre_mm_s": {"source_release": "terraclimate-v1.1@climatologylab"},
                      "soil_mm_s": {"source_release": "terraclimate-v1.1@climatologylab"}}}


def test_estimates_left_on_an_older_release_are_refused():
    catalogue = {"meta": {"pre_mm_s01": {"substitute": {"source_release": "terraclimate@IDAHO_EPSCOR/TERRACLIMATE"}},
                          "swc_pc_s01": {"substitute": {"source_release": "terraclimate-v1.1@climatologylab"}}}}
    problems = estimates_follow_record(catalogue, HISTORY)
    assert len(problems) == 1 and "pre_*" in problems[0] and "IDAHO" in problems[0]


def test_estimates_on_the_record_release_pass():
    catalogue = {"meta": {"pre_mm_s01": {"substitute": {"source_release": "terraclimate-v1.1@climatologylab"}}}}
    assert estimates_follow_record(catalogue, HISTORY) == []


def test_matrices_packaged_from_another_release_are_refused():
    catchments = {"series": {"pre_mm_s": {"provenance": [{"source_release": "terraclimate@IDAHO_EPSCOR/TERRACLIMATE"}]}}}
    assert matrices_follow_record(catchments, HISTORY)
