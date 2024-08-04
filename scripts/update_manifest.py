#!/usr/bin/env python3

"""Update the manifest file."""

import json
from pathlib import Path

ROOT_DIRECTORY = Path(__file__).parent.parent
MANIFEST_FILE = ROOT_DIRECTORY / "custom_components" / "oref_alert" / "manifest.json"
REQUIREMENTS_FILE = ROOT_DIRECTORY / "requirements.txt"


class UpdateManifest:
    """Manifest updater."""

    def __init__(self) -> None:
        """Initialize the object."""
        with MANIFEST_FILE.open() as manifest:
            self._manifest = json.load(manifest)
        self._requirements = {}
        with REQUIREMENTS_FILE.open() as requirements:
            for line in requirements.readlines():
                tokens = line.strip().split("==")
                self._requirements[tokens[0]] = tokens[1] if len(tokens) > 1 else None

    def update(self) -> None:
        """Update the manifest file."""
        requirements = [
            requirement.split("==")[0] for requirement in self._manifest["requirements"]
        ]
        self._manifest["requirements"] = [
            f"{requirement}=={self._requirements[requirement]}"
            for requirement in requirements
        ]
        with MANIFEST_FILE.open("w") as manifest:
            json.dump(self._manifest, manifest, indent=2)


if __name__ == "__main__":
    UpdateManifest().update()
