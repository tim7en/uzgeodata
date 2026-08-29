#!/usr/bin/env python3
"""Download every UZKAD agriculture region into a separate GeoPackage."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REGIONS = (
    ("1703", "andijon"),
    ("1706", "buxoro"),
    ("1708", "jizzax"),
    ("1710", "qashqadaryo"),
    ("1712", "navoiy"),
    ("1714", "namangan"),
    ("1718", "samarqand"),
    ("1722", "surxondaryo"),
    ("1724", "sirdaryo"),
    ("1726", "toshkent_shahri"),
    ("1727", "toshkent"),
    ("1730", "fargona"),
    ("1733", "xorazm"),
    ("1735", "qoraqalpogiston"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("WORKSPACE/downloads/uzkad_agriculture_regions"),
        help="Directory for regional GeoPackages and metadata files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    downloader = Path(__file__).with_name("download_uzkad_agriculture.py")

    for position, (code, slug) in enumerate(REGIONS, start=1):
        output = output_dir / f"{code}_{slug}.gpkg"
        print(
            f"\n=== Region {position}/{len(REGIONS)}: {code} {slug} ===",
            flush=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(downloader),
                "--where",
                f"soato_region='{code}'",
                "--output",
                str(output),
            ],
            check=True,
        )

    print(f"\nAll {len(REGIONS)} regional downloads are complete: {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
