"""Test utils."""
import json
import os


def fixture_path(file_name: str) -> str:
    """Return absolute path of a fixture file."""
    return os.path.join(
        f"{os.path.dirname(os.path.abspath(__file__))}/fixtures",
        file_name,
    )


def load_json_fixture(file_name: str) -> any:
    """Return a json object from a local fixture file."""
    with open(
        fixture_path(file_name),
        encoding="utf-8",
    ) as file:
        return json.load(file)
