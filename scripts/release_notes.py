"""Validate the versioned changelog before any GitHub tag or release is created."""

import argparse
import re
import tomllib
from pathlib import Path


def release_notes(tag, version, changelog):
    if not re.fullmatch(r"v\d+\.\d+\.\d+\.\d+(?:-rc\.\d+)?", tag):
        raise ValueError("Use a four-part release tag, optionally followed by -rc.N.")
    if tag[1:].replace("-rc.", "rc") != version:
        raise ValueError("Package version and release tag disagree.")
    headings = list(re.finditer(r"^## (.+)$", changelog, re.MULTILINE))
    if any("unreleased" in h[1].lower() for h in headings):
        raise ValueError("Version every changelog entry before tagging.")
    if not headings or not re.fullmatch(
        rf"\[{re.escape(tag[1:])}\] [–-] \d{{4}}-\d{{2}}-\d{{2}}", headings[0][1]
    ):
        raise ValueError(
            "The first changelog entry must match the tag and include its date."
        )
    end = headings[1].start() if len(headings) > 1 else len(changelog)
    notes = changelog[headings[0].end() : end].strip()
    if not notes or not any(line.startswith("- ") for line in notes.splitlines()):
        raise ValueError("The release has no recorded changes.")
    return notes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    notes = release_notes(
        args.tag,
        project["project"]["version"],
        Path("CHANGELOG.md").read_text(encoding="utf-8"),
    )
    args.output.write_text(notes + "\n", encoding="utf-8")
