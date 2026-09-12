"""Publication must not turn an unfinished extraction or superseded value into evidence."""
import csv
from PIPELINES.build_basin_history import collect, labelled, basin_payload


def test_completed_run_null_revision_and_provenance(tmp_path):
    with (tmp_path / 'run.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['run_id', 'status', 'started_at'])
        writer.writeheader()
        writer.writerow(dict(run_id='done', status='complete', started_at='2026-01-01'))
        writer.writerow(dict(run_id='busy', status='incomplete', started_at='2026-02-01'))
    attribute = 'uzgeodata.dated.v1.pre_mm_s'
    row = dict(observation_id='a', revision=1, supersedes='', basin_id='1',
               geometry_version='reg-test', attribute_id=attribute, month=1, value=5,
               run_id='done', source_release_id='source@1', recipe_version='method@1',
               temporal_statistic='monthly_mean')
    partition = tmp_path / 'time_kind=observation/year=2003'
    partition.mkdir(parents=True)
    with (partition / 'part.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerows([row, {**row, 'revision': 2, 'supersedes': 'a@1', 'value': ''},
                          {**row, 'observation_id': 'b', 'run_id': 'busy', 'value': 99}])
    known = labelled()
    series, releases = collect(tmp_path, [2003], known)
    result = basin_payload('1', [attribute], series, known, releases, [2003])
    published = result['series']['pre_mm_s']
    assert published['values'][0] is None
    assert published['run_ids'] == ['done']
    assert published['method'] == 'method@1'
    assert published['missing_months'] == 12


def test_snow_restriction_travels_in_download():
    snow = labelled()['uzgeodata.dated.v1.snw_pc_s']
    assert snow['trend_use'] == 'withdrawn'
    assert snow['asset'] == 'MODIS/061/MYD10A1'
