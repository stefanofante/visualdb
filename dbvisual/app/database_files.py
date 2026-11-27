"""Create an empty, persistent database without replacing existing user files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Literal

from dbvisual.core.connections import ConnectionConfig, build_engine


def create_database_file(
    dialect: Literal["sqlite", "duckdb"], folder: str, filename: str
) -> Path:
    if dialect not in {"sqlite", "duckdb"}:
        raise ValueError("Choose SQLite or DuckDB.")
    filename = filename.strip()
    if (
        not filename
        or filename in {".", "..", ":memory:"}
        or Path(filename).name != filename
    ):
        raise ValueError("Enter a file name and select its folder separately.")
    if os.name == "nt" and (
        PureWindowsPath(filename).is_reserved()
        or filename.endswith(".")
        or any(c in '<>:"|?*' or ord(c) < 32 for c in filename)
    ):
        raise ValueError("Choose a valid Windows file name.")
    directory = Path(folder).expanduser()
    if not folder.strip() or not directory.is_absolute() or not directory.is_dir():
        raise ValueError("Select an existing folder or enter its full path.")
    target = directory / filename
    if not target.suffix:
        target = target.with_suffix("." + dialect)
    if os.path.lexists(target):
        raise FileExistsError(
            f"A file already exists at {target}. Choose another name."
        )

    # DuckDB requires a new path; SQLite needs an explicit write to persist a
    # valid header. Close all handles before publishing the finished file on Windows.
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        staged = Path(staging) / "database"
        engine = build_engine(ConnectionConfig(dialect=dialect, database=str(staged)))
        try:
            with engine.begin() as conn:
                if dialect == "sqlite":
                    conn.exec_driver_sql("PRAGMA user_version = 0")
                else:
                    conn.exec_driver_sql("SELECT 1")
        finally:
            engine.dispose()
        # Reserve the destination exclusively, including on volumes without hard links.
        # Two simultaneous creations cannot replace each other's database.
        target.touch(exist_ok=False)
        try:
            os.replace(staged, target)
        except OSError:
            target.unlink(missing_ok=True)
            raise
    return target
