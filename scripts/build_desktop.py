"""Freeze DBVisual in the active Python environment on the target OS."""

import os
import platform
import subprocess
import sys
from pathlib import Path

import nicegui

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "DBVisual",
        "--onedir",
        "--windowed",
        "--specpath",
        str(ROOT / "build"),
        "--add-data",
        f"{Path(nicegui.__file__).parent}{os.pathsep}nicegui",
    ]
    for dist in ("dbvisual", "nicegui", "duckdb-engine", "keyring"):
        args.extend(["--copy-metadata", dist])
    for pkg in ("sqlglot.dialects", "duckdb_engine", "sqlalchemy.dialects"):
        args.extend(["--collect-submodules", pkg])
    for pkg in (
        "pymysql",
        "pyodbc",
        "psycopg",
        "psycopg_binary",
        "oracledb",
        "duckdb",
        "_duckdb",
    ):
        args.extend(["--hidden-import", pkg])
    if sys.platform in {"win32", "darwin"}:
        args.extend(["--hidden-import", "webview"])
    if sys.platform == "win32":
        args.extend(["--hidden-import", "keyring.backends.Windows"])
    if sys.platform == "darwin":
        if platform.machine() != "arm64":
            raise SystemExit("Use an arm64 Python interpreter on Apple Silicon.")
        args.extend(
            [
                "--target-arch",
                "arm64",
                "--osx-bundle-identifier",
                "it.st-line.dbvisual",
                "--hidden-import",
                "keyring.backends.macOS",
            ]
        )
    (ROOT / "build").mkdir(exist_ok=True)
    subprocess.run([*args, str(ROOT / "main.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
