"""Atomic evidence publishing, including brief Windows reader-lock retries."""
import csv
import json
import os
import tempfile
import time
from pathlib import Path


def atomic_write(path, emit):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                dir=path.parent, prefix=path.name+'.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            emit(handle)
        for attempt in range(12):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(.25)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path, payload):
    def emit(handle):
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    atomic_write(path, emit)


def write_csv(path, fieldnames, rows):
    def emit(handle):
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    atomic_write(path, emit)
