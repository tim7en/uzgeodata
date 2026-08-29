"""Inspect ArcGIS .lpkx packages and optionally extract their File Geodatabases."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath

import libarchive


def prepare_ntfs_file(output) -> None:
    """Enable sparse allocation, falling back to NTFS compression for large GIS tables."""
    if os.name != "nt":
        return
    import ctypes
    import msvcrt

    handle = msvcrt.get_osfhandle(output.fileno())
    returned = ctypes.c_ulong(0)
    sparse = ctypes.windll.kernel32.DeviceIoControl(
        handle, 0x000900C4, None, 0, None, 0, ctypes.byref(returned), None,
    )
    if not sparse:
        compression_format_default = ctypes.c_ushort(1)
        ctypes.windll.kernel32.DeviceIoControl(
            handle, 0x0009C040, ctypes.byref(compression_format_default), ctypes.sizeof(compression_format_default),
            None, 0, ctypes.byref(returned), None,
        )


def extract_package(package: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with libarchive.file_reader(str(package)) as archive:
        for entry in archive:
            parts = [part for part in PurePosixPath(entry.pathname).parts if part not in ("", ".", "..")]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if entry.isdir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output:
                prepare_ntfs_file(output)
                logical_size = 0
                for block in entry.get_blocks():
                    logical_size += len(block)
                    if block.count(0) == len(block):
                        output.seek(len(block), 1)
                    else:
                        output.write(block)
                output.truncate(logical_size)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract:
        extract_package(args.package, args.extract)
        print(args.extract)
        return
    with libarchive.file_reader(str(args.package)) as archive:
        for entry in archive:
            print(f"{entry.size:>12}  {entry.pathname}")


if __name__ == "__main__":
    main()
