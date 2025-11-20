#!/usr/bin/env python3
"""Generate the metadata files."""

import argparse
import asyncio
import json
import sys
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import aiohttp
import requests
import yaml

sys.path.insert(0, str((Path(__file__).parent / "..").resolve()))

from custom_components.oref_alert.areas_checker import (
    CITIES_MIX_URL,
    DEPRECATION_SUFFIX,
)
from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES
from custom_components.oref_alert.pushy import TEST_SEGMENTS
from custom_components.oref_alert.tzevaadom import TZEVAADOM_SPELLING_FIX

RELATIVE_OUTPUT_DIRECTORY = "custom_components/oref_alert/metadata/"
AREAS_OUTPUT = "areas.py"
AREAS_AND_GROUPS_OUTPUT = "areas_and_groups.py"
CITY_ALL_AREAS_OUTPUT = "city_all_areas.py"
AREA_TO_MIGUN_TIME_OUTPUT = "area_to_migun_time.py"
DISTRICT_TO_AREAS_OUTPUT = "district_to_areas.py"
AREA_TO_DISTRICT_OUTPUT = "area_to_district.py"
AREA_TO_POLYGON_OUTPUT = "area_to_polygon.json"
AREA_INFO_OUTPUT = "area_info.py"
SEGMENT_TO_AREA_OUTPUT = "segment_to_area.py"
TZEVAADOM_ID_TO_AREA_OUTPUT = "tzevaadom_id_to_area.py"
SERVICES_YAML = "custom_components/oref_alert/services.yaml"
TEST_AREAS_FIXTURE = "tests/fixtures/GetCitiesMix.json"
DISTRICTS_URL = "https://alerts-history.oref.org.il/Shared/Ajax/GetDistricts.aspx"
SEGMENTS_URL = "https://dist-android.meser-hadash.org.il/smart-dist/services/anonymous/segments/android?instance=1544803905&locale=iw_IL"
POLYGON_URL = "https://services.meser-hadash.org.il/smart-dist/services/anonymous/polygon/id/android?instance=1544803905&id="
TZEVAADOM_CITIES_URL = "https://www.tzevaadom.co.il/static/cities.json"
CITY_ALL_AREAS_SUFFIX = " - כל האזורים"
DISTRICT_PREFIX = "מחוז "

ALL_AREAS = {
    "כל הארץ": {"lat": 31.7781, "lon": 35.2164, "segment": 0},
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
        self._cities_mix: list[Any] = self._fix_areas(
            self._fetch_url_json(CITIES_MIX_URL)
        )
        self._backend_areas: list[str] = self._get_areas()
        self._areas_no_group = list(
            filter(
                lambda area: not area.endswith(CITY_ALL_AREAS_SUFFIX),
                self._backend_areas,
            )
        )
        self._city_to_areas: dict[str, list[str]] = self._city_to_areas_map()
        self._area_to_migun_time: dict[str, int] = self._area_to_migun_time_map()
        self._districts = self._get_districts()
        self._district_to_areas = self._district_to_areas_map()
        self._area_to_district = self._area_to_district_map()
        self._areas_and_groups = (
            self._areas_no_group
            + list(self._city_to_areas.keys())
            + list(self._district_to_areas.keys())
        )
        self._areas_and_groups.sort()
        assert len(self._areas_and_groups) == len(set(self._areas_and_groups))
        self._segments_data = self._get_segments_data()
        self._segments = self._get_segments_to_area()
        self._area_info = self._get_area_info()
        self._area_to_polygon = await self._get_area_to_polygon()
        self._tzeva_cities = self._get_tzevaadom_data()
        self._tzevaadom_id_to_area = self._get_tzevaadom_id_to_area()
        await self._http_client.close()

    def _read_args(self) -> None:
        """Read program arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--proxy")
        parser.parse_args(namespace=self)

    def _fetch_url_json(self, url: str) -> Any:
        """Fetch URL and return JSON reply."""
        result = requests.get(
            url,
            proxies={"https": self.proxy} if self.proxy else None,
            timeout=15,
        )
        result.raise_for_status()
        return result.json()

    async def _async_fetch_url_json(self, url: str) -> Any:
        """Fetch URL and return JSON reply."""
        async with self._http_client.get(
            url,
            proxy=self.proxy if self.proxy else None,
        ) as response:
            response.raise_for_status()
            return await response.json()

    def _fix_areas(self, data: Any) -> Any:
        """Fix spelling error and remove irrelevant items."""
        remove_areas = set(SPELLING_FIX.keys())
        return [
            area
            for area in data
            if area["label_he"] not in remove_areas
            and not area["label_he"].endswith(DEPRECATION_SUFFIX)
        ] + [
            {**area, "label_he": new}
            for area in data
            for old, new in SPELLING_FIX.items()
            if area["label_he"] == old
        ]

    def _get_areas(self) -> list[str]:
        """Return the list of areas."""
        areas = list({area["label_he"] for area in self._cities_mix})
        areas.sort()
        return areas

    def _get_cities_with_all_areas(self) -> list[str]:
        """Return the list of cities with 'all area'."""
        cities = [
            area.replace(CITY_ALL_AREAS_SUFFIX, "")
            for area in filter(
                lambda area: area.endswith(CITY_ALL_AREAS_SUFFIX), self._backend_areas
            )
        ]
        cities.sort()
        return cities

    def _city_to_areas_map(self) -> dict[str, list[str]]:
        """Build the map between cities and their sub areas."""
        city_to_areas = {}
        for city in self._get_cities_with_all_areas():
            city_areas = []
            for area in self._areas_no_group:
                if area.startswith(city):
                    assert area in self._areas_no_group
                    city_areas.append(area)
            city_areas = list(set(city_areas))
            city_areas.sort()
            city_to_areas[city + CITY_ALL_AREAS_SUFFIX] = city_areas
        return city_to_areas

    def _area_to_migun_time_map(self) -> dict[str, int]:
        """Build a mpa between a city and the migun time."""
        migun_time = {
            area["label_he"]: int(area["migun_time"]) for area in self._cities_mix
        }
        return {area: migun_time[area] for area in sorted(migun_time.keys())}

    def _get_districts(self) -> list:
        """Return the list of districts."""
        districts = self._fetch_url_json(DISTRICTS_URL)
        return list(
            filter(
                lambda area: area["value"] is not None
                and area["label"] not in ALL_AREAS_ALIASES
                and not area["label"].endswith(DEPRECATION_SUFFIX),
                districts,
            )
        )

    def _district_to_areas_map(self) -> dict[str, list[str]]:
        """Build the map between districts and their areas."""
        district_to_areas = {}
        district_names = list({district["areaname"] for district in self._districts})
        district_names.sort()
        for district in district_names:
            district_areas = []
            for area in self._districts:
                if (
                    area["areaname"] == district
                    and area["label_he"] in self._areas_no_group
                ):
                    assert area["label_he"] not in self._city_to_areas
                    district_areas.append(area["label_he"])
            district_areas = list(set(district_areas))
            district_areas.sort()
            district_to_areas[DISTRICT_PREFIX + district] = district_areas
        return district_to_areas

    def _area_to_district_map(self) -> dict[str, str]:
        """Build the map between areas and their districts."""
        return dict(
            sorted(
                {area["label_he"]: area["areaname"] for area in self._districts}.items()
            )
        )

    def _get_segments_data(self) -> dict[int, dict[str, Any]]:
        """Get segments data as a sorted dict of segment to its data."""
        segments = self._fetch_url_json(SEGMENTS_URL)["segments"]
        unknown_test_segments = TEST_SEGMENTS - segments.keys()
        assert not unknown_test_segments, (
            f"Unknown test segments: {unknown_test_segments}"
        )
        return dict(
            sorted(
                {
                    data["id"]: data
                    for data in segments.values()
                    if data["name"] in self._areas_no_group
                }.items()
            )
        )

    def _get_segments_to_area(self) -> dict[int, str]:
        """Get segments to area dict."""
        return {segment: data["name"] for segment, data in self._segments_data.items()}

    def _get_tzevaadom_data(self) -> dict[str, dict[str, Any]]:
        """Get tzevaadom metadata content."""
        return self._tzevaadom_spelling_fix(
            self._fetch_url_json(TZEVAADOM_CITIES_URL)["cities"]
        )

    def _tzevaadom_spelling_fix(self, data: Any) -> Any:
        """Fix spelling error of tzevaadom."""
        for old, new in TZEVAADOM_SPELLING_FIX.items():
            data[new] = data.pop(old)

        # The lists should be identical with the exception of "all areas" aliases.
        # This check is disabled until tzevaadom updates their data.
        # assert set(data.keys()).union(set(ALL_AREAS.keys())) == set(
        #     self._areas_no_group
        # )  # noqa: ERA001, RUF100
        # assert not set(data.keys()).intersection(set(ALL_AREAS.keys())) noqa: ERA001

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
                data = await self._async_fetch_url_json(
                    f"{POLYGON_URL}{self._area_info[area]['segment']}"
                )
                if (
                    data["segmentId"]
                    and int(data["segmentId"]) == self._area_info[area]["segment"]
                ):
                    return area, data["polygonPointList"][0]
        msg = f"Failed to fetch polygon for area {area}"
        raise RuntimeError(msg)

    def _get_tzevaadom_id_to_area(self) -> dict[int, str]:
        """Get tzevaadom area id to its name."""
        areas = {}
        for area, data in self._tzeva_cities.items():
            # assert area in self._areas_no_group
            # The assert is disabled until tzevaadom updates their data.
            if area in self._areas_no_group:
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
                CITY_ALL_AREAS_OUTPUT,
                "CITY_ALL_AREAS: dict[str, list[str]]",
                self._city_to_areas,
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

        with (self._root_directory / SERVICES_YAML).open(
            encoding="utf-8",
        ) as services_yaml:
            services = yaml.load(services_yaml, Loader=yaml.SafeLoader)
        services["add_sensor"]["fields"]["areas"]["selector"]["select"]["options"] = [
            area for area in self._areas_and_groups if area not in ALL_AREAS_ALIASES
        ]
        services["synthetic_alert"]["fields"]["area"]["selector"]["select"][
            "options"
        ] = self._areas_no_group
        with (self._root_directory / SERVICES_YAML).open(
            "w",
            encoding="utf-8",
        ) as output:
            yaml.dump(services, output, sort_keys=False, indent=2, allow_unicode=True)

        with (
            zipfile.ZipFile(
                f"{self._output_directory / AREA_TO_POLYGON_OUTPUT}.zip",
            ) as zip_file,
            zip_file.open(AREA_TO_POLYGON_OUTPUT) as json_file,
        ):
            previous_area_to_polygon = json.load(json_file)

        if self._area_to_polygon != previous_area_to_polygon:
            with zipfile.ZipFile(
                f"{self._output_directory / AREA_TO_POLYGON_OUTPUT}.zip",
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as zip_file:
                zip_file.writestr(
                    AREA_TO_POLYGON_OUTPUT,
                    json.dumps(self._area_to_polygon, ensure_ascii=False),
                )

        with (self._root_directory / TEST_AREAS_FIXTURE).open(
            "w", encoding="utf-8"
        ) as fixture:
            json.dump(
                [
                    {"label_he": label_he}
                    for label_he in sorted(
                        {
                            area["label_he"]
                            for area in self._fetch_url_json(CITIES_MIX_URL)
                        }
                    )
                ],
                fixture,
                ensure_ascii=False,
            )

        await (
            await asyncio.create_subprocess_exec(
                "ruff",
                "format",
                str(self._output_directory),
            )
        ).wait()


if __name__ == "__main__":
    asyncio.run(OrefMetadata().generate())
