#!/usr/bin/env python3
"""Generate the metadata files."""

import argparse
import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import aiohttp
import yaml

sys.path.insert(
    0,
    str((Path(__file__).parent.parent / "custom_components" / "oref_alert").resolve()),
)

from metadata import (  # pyright: ignore[reportMissingImports]
    ALL_AREAS_ALIASES,
    DEPRECATION_SUFFIX,
    OREF_HEADERS,
    SEGMENTS_URL,
    SOME_PARTS_OF_THE_COUNTRY,
    TZEVAADOM_SPELLING_FIX,
    is_area_segment,
)

RELATIVE_OUTPUT_DIRECTORY = "custom_components/oref_alert/metadata/"
AREAS_OUTPUT = "areas.py"
AREAS_AND_GROUPS_OUTPUT = "areas_and_groups.py"
AREA_TO_MIGUN_TIME_OUTPUT = "area_to_migun_time.py"
DISTRICT_TO_AREAS_OUTPUT = "district_to_areas.py"
AREA_TO_DISTRICT_OUTPUT = "area_to_district.py"
AREA_TO_POLYGON_OUTPUT = "area_to_polygon.json"
AREA_INFO_OUTPUT = "area_info.py"
SEGMENT_TO_AREA_OUTPUT = "segment_to_area.py"
TZEVAADOM_ID_TO_AREA_OUTPUT = "tzevaadom_id_to_area.py"
SERVICES_YAML = "custom_components/oref_alert/services.yaml"
TRIGGERS_YAML = "custom_components/oref_alert/triggers.yaml"
CONDITIONS_YAML = "custom_components/oref_alert/conditions.yaml"
TEST_SEGMENTS_FIXTURE = "tests/fixtures/segments.json"
DISTRICTS_URL = "https://www.oref.org.il/districts/districts_heb.json"
POLYGON_URL = "https://services.meser-hadash.org.il/smart-dist/services/anonymous/polygon/id/android?instance=1544803905&id="
TZEVAADOM_CITIES_URL = "https://www.tzevaadom.co.il/static/cities.json"
CITY_ALL_AREAS_SUFFIX = " - כל האזורים"
DISTRICT_PREFIX = "מחוז "

ALL_AREAS = {
    "כל הארץ": {"lat": 31.7781, "lon": 35.2164, "segment": 0},
    "ברחבי הארץ": {"lat": 31.7781, "lon": 35.2164, "segment": 0},
}
assert set(ALL_AREAS.keys()) == ALL_AREAS_ALIASES

AREA_INFO_TYPE = '''
from typing import TypedDict
class AreaInfoType(TypedDict):
    """Type for area info."""
    lat: float
    lon: float
    segment: int
'''

SPELLING_FIX = {"חדרה כל - האזורים": "חדרה - כל האזורים"}
DISTRICT_FIX = {"סביון": "דן"}
ALL_AREAS_MIGUN_TIME = dict.fromkeys(ALL_AREAS, 0)

TZEVAADOM_ALL_AREAS = {10000000: next(iter(ALL_AREAS))}


class OrefMetadata:
    """Copy Oref metadata."""

    def __init__(self) -> None:
        """Initialize the object."""
        self.proxy = None
        self._read_args()

    async def _fetch_data(self) -> None:
        """Fetch all required data."""
        self._http_client = aiohttp.ClientSession()
        self._root_directory = Path(__file__).parent.parent
        self._output_directory = self._root_directory / RELATIVE_OUTPUT_DIRECTORY
        segments = (await self._fetch_url_json(SEGMENTS_URL))["segments"]
        self._segments_snapshot = self._get_segments_snapshot(segments)
        self._segment_areas: list[Any] = self._fix_areas(
            self._get_segment_areas(segments)
        )
        self._backend_areas: list[str] = self._get_areas()
        self._areas_no_group = list(
            filter(
                lambda area: not area.endswith(CITY_ALL_AREAS_SUFFIX),
                self._backend_areas,
            )
        )
        self._area_to_migun_time: dict[str, int] = self._area_to_migun_time_map()
        self._districts = await self._get_districts()
        self._district_to_areas = self._district_to_areas_map()
        self._area_to_district = self._area_to_district_map()
        self._areas_and_groups = self._areas_no_group + list(
            self._district_to_areas.keys()
        )
        self._areas_and_groups.sort()
        assert len(self._areas_and_groups) == len(set(self._areas_and_groups))
        self._segments_data = self._get_segments_data(segments)
        self._segments = self._get_segments_to_area()
        self._area_info = self._get_area_info()
        self._area_to_polygon = await self._get_area_to_polygon()
        self._tzeva_cities = await self._get_tzevaadom_data()
        self._tzevaadom_id_to_area = self._get_tzevaadom_id_to_area()

    def _read_args(self) -> None:
        """Read program arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--proxy")
        parser.parse_args(namespace=self)

    async def _fetch_url_json(self, url: str) -> Any:
        """Fetch URL and return JSON reply."""
        async with self._http_client.get(
            url,
            headers=OREF_HEADERS if "oref.org.il" in url else None,
            proxy=self.proxy or None,
        ) as response:
            response.raise_for_status()
            return await response.json()

    def _get_segments_snapshot(self, segments: dict[str, Any]) -> dict[str, Any]:
        """Return the segments fields used by AreasChecker, for its tests."""
        return {
            "segments": {
                segment: {"name": data["name"], "isParent": bool(data.get("isParent"))}
                for segment, data in segments.items()
            }
        }

    def _get_segment_areas(self, segments: dict[str, Any]) -> list[dict[str, Any]]:
        """Return areas and their migun time, based on the segments data."""
        areas = [
            {
                "label": data["name"],
                "migun_time": data["szSeconds"],
            }
            for data in segments.values()
            if is_area_segment(data)
        ]
        return areas + [
            {"label": area, "migun_time": migun_time}
            for area, migun_time in ALL_AREAS_MIGUN_TIME.items()
        ]

    def _fix_areas(self, data: list[dict[str, Any]]) -> Any:
        """Fix spelling error and remove irrelevant and duplicated items."""
        fix_areas = set(SPELLING_FIX.keys())
        data.sort(key=lambda area: area["label"], reverse=True)
        areas = set()
        result = []
        for area in data:
            if area["label"] in fix_areas:
                area["label"] = area["label"] = SPELLING_FIX[area["label"]]
            if (
                area["label"] in areas
                or area["label"].endswith(DEPRECATION_SUFFIX)
                or area["label"] == SOME_PARTS_OF_THE_COUNTRY
            ):
                continue
            areas.add(area["label"])
            result.append(area)
        return result

    def _get_areas(self) -> list[str]:
        """Return the list of areas."""
        areas = list({area["label"] for area in self._segment_areas})
        areas.sort()
        return areas

    def _area_to_migun_time_map(self) -> dict[str, int]:
        """Build a mpa between a city and the migun time."""
        migun_time = {
            area["label"]: int(area["migun_time"])
            for area in self._segment_areas
            if area["label"] in self._areas_no_group
        }
        return {area: migun_time[area] for area in sorted(migun_time.keys())}

    async def _get_districts(self) -> list:
        """Return the list of districts."""
        districts = await self._fetch_url_json(DISTRICTS_URL)
        districts.sort(key=lambda area: int(area["id"]), reverse=True)
        areas = set()
        result = []
        for area in districts:
            if (
                area["value"] is not None
                and area["label"] not in areas
                and area["label"] not in ALL_AREAS_ALIASES
                and area["label"] != SOME_PARTS_OF_THE_COUNTRY
                and not area["label"].endswith(DEPRECATION_SUFFIX)
            ):
                areas.add(area["label"])
                area["areaname"] = DISTRICT_FIX.get(area["label"], area["areaname"])
                result.append(area)

        # The web source and the mobile source (segments) must have the same areas.
        segments_areas = set(self._areas_no_group) - ALL_AREAS_ALIASES
        assert areas == segments_areas, (
            sorted(areas - segments_areas),
            sorted(segments_areas - areas),
        )
        return result

    def _district_to_areas_map(self) -> dict[str, list[str]]:
        """Build the map between districts and their areas."""
        district_to_areas = {}
        district_names = list({district["areaname"] for district in self._districts})
        district_names.sort()
        for district in district_names:
            district_to_areas[DISTRICT_PREFIX + district] = sorted(
                {
                    area["label"]
                    for area in self._districts
                    if area["areaname"] == district
                    and area["label"] in self._areas_no_group
                }
            )
        return district_to_areas

    def _area_to_district_map(self) -> dict[str, str]:
        """Build the map between areas and their districts."""
        return dict(
            sorted(
                {area["label"]: area["areaname"] for area in self._districts}.items()
            )
        )

    def _get_segments_data(self, segments: dict[str, Any]) -> dict[int, dict[str, Any]]:
        """Get segments data as a sorted dict of segment to its data."""
        return dict(
            sorted(
                {
                    data["id"]: data
                    for data in segments.values()
                    if data["name"] in self._areas_no_group and not data.get("isParent")
                }.items()
            )
        )

    def _get_segments_to_area(self) -> dict[int, str]:
        """Get segments to area dict."""
        return {segment: data["name"] for segment, data in self._segments_data.items()}

    async def _get_tzevaadom_data(self) -> dict[str, dict[str, Any]]:
        """Get tzevaadom metadata content."""
        return self._tzevaadom_spelling_fix(
            (await self._fetch_url_json(TZEVAADOM_CITIES_URL))["cities"]
        )

    def _tzevaadom_spelling_fix(self, data: Any) -> Any:
        """Fix spelling error of tzevaadom."""
        for old, new in TZEVAADOM_SPELLING_FIX.items():
            data[new] = data.pop(old)

        # The lists should be identical with the exception of "all areas" aliases.
        assert set(data.keys()) == set(self._areas_no_group) - set(ALL_AREAS.keys())

        return data

    def _get_area_info(self) -> dict[str, dict[str, Any]]:
        """Get area additional information of an area."""
        area_to_data = {area["name"]: area for area in self._segments_data.values()}
        areas = {}
        for area in self._areas_no_group:
            if area in area_to_data:
                areas[area] = {
                    "lat": float(area_to_data[area]["centerY"]),
                    "lon": float(area_to_data[area]["centerX"]),
                    "segment": area_to_data[area]["id"],
                }
            else:
                areas[area] = ALL_AREAS[area]
        return areas

    async def _get_area_to_polygon(self) -> dict[str, list[list[float]]]:
        """Get area polygons."""
        return dict(
            await asyncio.gather(
                *[
                    self._get_polygon(area)
                    for area in self._areas_no_group
                    if area not in ALL_AREAS_ALIASES
                ]
            )
        )

    async def _get_polygon(self, area: str) -> tuple[str, list[list[float]]]:
        """Get area's polygon."""
        for _ in range(10):
            with suppress(Exception):
                data = await self._fetch_url_json(
                    f"{POLYGON_URL}{self._area_info[area]['segment']}"
                )
                if (
                    data["segmentId"]
                    and int(data["segmentId"]) == self._area_info[area]["segment"]
                ):
                    return area, [
                        [round(lat, 8), round(lon, 8)]
                        for lat, lon in data["polygonPointList"][0]
                    ]
        msg = f"Failed to fetch polygon for area {area}"
        raise RuntimeError(msg)

    def _get_tzevaadom_id_to_area(self) -> dict[int, str]:
        """Get tzevaadom area id to its name."""
        areas = {}
        for area, data in self._tzeva_cities.items():
            assert area in self._areas_no_group
            areas[data["id"]] = area
        areas.update(TZEVAADOM_ALL_AREAS)
        return dict(sorted(areas.items()))

    async def generate(self) -> None:
        """Generate the output files."""
        await self._fetch_data()
        for file_name, variable_name, variable_data in (
            (
                AREAS_AND_GROUPS_OUTPUT,
                "AREAS_AND_GROUPS: list[str]",
                self._areas_and_groups,
            ),
            (
                AREA_TO_MIGUN_TIME_OUTPUT,
                "AREA_TO_MIGUN_TIME: dict[str, int]",
                self._area_to_migun_time,
            ),
            (
                DISTRICT_TO_AREAS_OUTPUT,
                "DISTRICT_AREAS: dict[str, list[str]]",
                self._district_to_areas,
            ),
            (
                AREA_TO_DISTRICT_OUTPUT,
                "AREA_TO_DISTRICT: dict[str, str]",
                self._area_to_district,
            ),
            (
                AREAS_OUTPUT,
                "AREAS: set[str]",
                str(self._areas_no_group).replace("[", "{").replace("]", "}"),
            ),
            (
                AREA_INFO_OUTPUT,
                AREA_INFO_TYPE + "AREA_INFO: dict[str, AreaInfoType]",
                self._area_info,
            ),
            (SEGMENT_TO_AREA_OUTPUT, "SEGMENT_TO_AREA: dict[int, str]", self._segments),
            (
                TZEVAADOM_ID_TO_AREA_OUTPUT,
                "TZEVAADOM_ID_TO_AREA: dict[int, str]",
                self._tzevaadom_id_to_area,
            ),
        ):
            with (self._output_directory / file_name).open(
                "w",
                encoding="utf-8",
            ) as output:
                output.write('"""GENERATED FILE. DO NOT EDIT MANUALLY."""\n\n')
                output.write(f"{variable_name} = {variable_data}")

        areas_and_groups = [
            area for area in self._areas_and_groups if area not in ALL_AREAS_ALIASES
        ]

        with (self._root_directory / SERVICES_YAML).open(
            encoding="utf-8",
        ) as services_yaml:
            services = yaml.load(services_yaml, Loader=yaml.SafeLoader)
        services["add_sensor"]["fields"]["areas"]["selector"]["select"]["options"] = (
            areas_and_groups
        )
        services["synthetic_alert"]["fields"]["area"]["selector"]["select"][
            "options"
        ] = services["manual_event_end"]["fields"]["area"]["selector"]["select"][
            "options"
        ] = self._areas_no_group
        with (self._root_directory / SERVICES_YAML).open(
            "w",
            encoding="utf-8",
        ) as output:
            yaml.dump(services, output, sort_keys=False, indent=2, allow_unicode=True)

        with (self._root_directory / TRIGGERS_YAML).open(
            encoding="utf-8",
        ) as triggers_yaml:
            triggers = yaml.load(triggers_yaml, Loader=yaml.SafeLoader)
        triggers["area"]["fields"]["areas"]["selector"]["select"]["options"] = (
            areas_and_groups
        )
        with (self._root_directory / TRIGGERS_YAML).open(
            "w",
            encoding="utf-8",
        ) as output:
            yaml.dump(triggers, output, sort_keys=False, indent=2, allow_unicode=True)

        with (self._root_directory / CONDITIONS_YAML).open(
            encoding="utf-8",
        ) as conditions_yaml:
            conditions = yaml.load(conditions_yaml, Loader=yaml.SafeLoader)
        conditions["area"]["fields"]["areas"]["selector"]["select"]["options"] = (
            areas_and_groups
        )
        with (self._root_directory / CONDITIONS_YAML).open(
            "w",
            encoding="utf-8",
        ) as output:
            yaml.dump(conditions, output, sort_keys=False, indent=2, allow_unicode=True)

        # One area per line, so diffs show which areas changed.
        # The release workflow replaces this file with a gzip-compressed version.
        with (self._output_directory / AREA_TO_POLYGON_OUTPUT).open(
            "w", encoding="utf-8"
        ) as output:
            output.write(
                "{\n"
                + ",\n".join(
                    f"{json.dumps(area, ensure_ascii=False)}:"
                    f"{json.dumps(polygon, separators=(',', ':'))}"
                    for area, polygon in self._area_to_polygon.items()
                )
                + "\n}\n"
            )

        with (self._root_directory / TEST_SEGMENTS_FIXTURE).open(
            "w", encoding="utf-8"
        ) as fixture:
            json.dump(self._segments_snapshot, fixture, ensure_ascii=False)

        await (
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "ruff",
                "format",
                str(self._output_directory),
            )
        ).wait()

        await self._http_client.close()


if __name__ == "__main__":
    asyncio.run(OrefMetadata().generate())
