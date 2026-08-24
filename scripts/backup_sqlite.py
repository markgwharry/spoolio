#!/usr/bin/env python3
"""Create an atomic, integrity-checked SQLite backup, including WAL contents."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import quote


def backup_database(source_path: Path, target_path: Path) -> None:
    source_path = source_path.resolve(strict=True)
    target_path = target_path.resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_uri = f"file:{quote(str(source_path), safe='/')}?mode=ro"
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            dir=target_path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name

        with closing(sqlite3.connect(source_uri, uri=True, timeout=30)) as source:
            with closing(sqlite3.connect(temporary_name)) as destination:
                source.backup(destination)
                integrity = destination.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    raise RuntimeError(
                        f"SQLite backup integrity check failed: {integrity!r}"
                    )

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, target_path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    backup_database(args.source, args.target)


if __name__ == "__main__":
    main()
