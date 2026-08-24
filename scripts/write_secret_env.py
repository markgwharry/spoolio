#!/usr/bin/env python3
"""Atomically write Spoolio's persisted shell environment with safe quoting."""

import argparse
import os
from pathlib import Path
import shlex
import tempfile


SECRET_NAMES = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "WIFI_CREDENTIAL_KEY",
)
OPTIONAL_SECRET_NAMES = (
    "REGISTRATION_TOKEN",
)


def write_secret_env(target_path: Path) -> None:
    target_path = target_path.resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    missing = [name for name in SECRET_NAMES if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required secrets: {', '.join(missing)}")

    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            dir=target_path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            for name in SECRET_NAMES:
                temporary.write(f"export {name}={shlex.quote(os.environ[name])}\n")
            for name in OPTIONAL_SECRET_NAMES:
                if os.environ.get(name):
                    temporary.write(f"export {name}={shlex.quote(os.environ[name])}\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, target_path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    write_secret_env(args.target)


if __name__ == "__main__":
    main()
