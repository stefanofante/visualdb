"""Download the public installer assets matching this checkout into installers/vTAG/."""

import hashlib
import json
import tempfile
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "stefanofante/visualdb"
ASSETS = ("DBVisual-Windows-x64-Setup.exe", "DBVisual-macOS-arm64.dmg")


def download_asset(asset: dict, destination: Path) -> None:
    expected = asset["digest"].removeprefix("sha256:")
    if destination.is_file():
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                return
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        with (
            urlopen(asset["browser_download_url"], timeout=90) as response,
            temporary.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
                digest.update(chunk)
        if temporary.stat().st_size != asset["size"] or digest.hexdigest() != expected:
            raise ValueError(f"Size or checksum mismatch for {destination.name}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    tag = "v" + version.replace("rc", "-rc.")
    api = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}"
    try:
        with urlopen(api, timeout=30) as response:
            release = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise SystemExit(
                f"No public release for {tag}. Check which revision is open."
            ) from error
        raise
    assets = {a["name"]: a for a in release["assets"]}
    if any(name not in assets for name in ASSETS):
        raise SystemExit(f"Both desktop installers are required in release {tag}.")
    folder = ROOT / "installers" / tag
    folder.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        print(f"Downloading or verifying {name} ...", flush=True)
        download_asset(assets[name], folder / name)
        print(folder / name)


if __name__ == "__main__":
    main()
