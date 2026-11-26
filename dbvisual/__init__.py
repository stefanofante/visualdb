"""dbvisual — local visual builder for forms, sheets and reports over existing DBs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dbvisual")
except PackageNotFoundError:  # Running from an uninstalled source checkout.
    import tomllib
    from pathlib import Path

    with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as source:
        __version__ = tomllib.load(source)["project"]["version"]
