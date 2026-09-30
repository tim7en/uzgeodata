"""A release fingerprints content, so it verifies on any checkout, and names an immutable object."""
from ATLAS_MODULES.core import releases


def test_a_release_verifies_across_line_endings(tmp_path):
    data = tmp_path / "catalogue.json"
    data.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')
    blob = tmp_path / "cube.parquet"
    blob.write_bytes(b"PAR1\r\n\x00binary")
    record = releases.cut(tmp_path, [data, blob], base=tmp_path)
    assert record["schema_version"] == 2
    assert record["files"]["catalogue.json"]["object"] == f"objects/{record['files']['catalogue.json']['sha256']}"
    data.write_bytes(b'{\n  "a": 1\n}\n')           # the same file as git or Linux holds it
    assert releases.check(tmp_path, record["release_id"]) == []
    data.write_bytes(b'{\n  "a": 2\n}\n')           # changed content still fails
    assert releases.check(tmp_path, record["release_id"])


def test_binary_line_endings_are_content(tmp_path):
    blob = tmp_path / "cube.parquet"
    blob.write_bytes(b"PAR1\r\n")
    record = releases.cut(tmp_path, [blob], base=tmp_path)
    blob.write_bytes(b"PAR1\n")
    assert releases.check(tmp_path, record["release_id"])
