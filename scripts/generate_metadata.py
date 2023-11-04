#!/usr/bin/env python3
"""Generate the metadata files."""
import subprocess
from typing import Any
import yaml

import requests

OUTPUT_DIRECTORY = "/workspaces/oref_alert/custom_components/oref_alert/metadata/"
AREAS_OUTPUT = OUTPUT_DIRECTORY + "areas.py"
AREAS_AND_GROUPS_OUTPUT = OUTPUT_DIRECTORY + "areas_and_groups.py"
CITY_ALL_AREAS_OUTPUT = OUTPUT_DIRECTORY + "city_all_areas.py"
AREA_TO_MIGUN_TIME_OUTPUT = OUTPUT_DIRECTORY + "area_to_migun_time.py"
DISTRICT_TO_AREAS_OUTPUT = OUTPUT_DIRECTORY + "district_to_areas.py"
SERVICES_YAML = "/workspaces/oref_alert/custom_components/oref_alert/services.yaml"
CITIES_MIX_URL = "https://www.oref.org.il/Shared/Ajax/GetCitiesMix.aspx"
DISTRICTS_URL = "https://www.oref.org.il/Shared/Ajax/GetDistricts.aspx"
CITY_ALL_ARES_SUFFIX = " - כל האזורים"
# "Hadera all areas" is listed with this typo:
CITY_ALL_ARES_SUFFIX_TYPO = " כל - האזורים"
DISTRICT_PREFIX = "מחוז "


class OrefMetadata:
    """Copy Oref metadata."""

    def __init__(self) -> None:
        """Initialize the object."""
        self._cities_mix: list[Any] = requests.get(CITIES_MIX_URL, timeout=5).json()
        self._backend_areas: list[str] = self._get_areas()
        self._areas_no_group = list(
            filter(
                lambda area: not area.endswith(CITY_ALL_ARES_SUFFIX),
                self._backend_areas,
            )
        )
        self._city_to_areas: dict[str, list[str]] = self._city_to_areas_map()
        self._area_to_migun_time: dict[str, int] = self._area_to_migun_time_map()
        self._district_to_areas = self._district_to_areas_map()
        self._areas_and_groups = (
            self._areas_no_group
            + list(self._city_to_areas.keys())
            + list(self._district_to_areas.keys())
        )
        self._areas_and_groups.sort()
        assert len(self._areas_and_groups) == len(set(self._areas_and_groups))

    def _get_areas(self) -> list[str]:
        """Return the list of areas."""
        areas = list(
            {
                area["label_he"].replace(
                    CITY_ALL_ARES_SUFFIX_TYPO, CITY_ALL_ARES_SUFFIX
                )
                for area in self._cities_mix
            }
        )
        areas.sort()
        return areas

    def _get_cities_with_all_areas(self) -> list[str]:
        """Return the list of cities with 'all area'."""
        cities = [
            area.replace(CITY_ALL_ARES_SUFFIX, "")
            for area in filter(
                lambda area: area.endswith(CITY_ALL_ARES_SUFFIX), self._backend_areas
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
            city_to_areas[city + CITY_ALL_ARES_SUFFIX] = city_areas
        return city_to_areas

    def _area_to_migun_time_map(self) -> dict[str, int]:
        """Build a mpa between a city and the migun time."""
        migun_time = {
            area["label_he"].replace(
                CITY_ALL_ARES_SUFFIX_TYPO, CITY_ALL_ARES_SUFFIX
            ): int(area["migun_time"])
            for area in self._cities_mix
        }
        return {area: migun_time[area] for area in sorted(migun_time.keys())}

    def _get_districts(self) -> list:
        """Return the list of districts."""
        districts = requests.get(DISTRICTS_URL, timeout=5).json()
        return list(filter(lambda area: area["value"] is not None, districts))

    def _district_to_areas_map(self) -> dict[str, list[str]]:
        """Build the map between districts and their areas."""
        districts = self._get_districts()
        district_to_areas = {}
        district_names = list({district["areaname"] for district in districts})
        district_names.sort()
        for district in district_names:
            district_areas = []
            for area in districts:
                if area["areaname"] == district:
                    assert area["label_he"] in self._areas_no_group
                    assert area["label_he"] not in self._city_to_areas
                    district_areas.append(area["label_he"])
            district_areas = list(set(district_areas))
            district_areas.sort()
            district_to_areas[DISTRICT_PREFIX + district] = district_areas
        return district_to_areas

    def generate(self) -> None:
        """Generate the output files."""
        for file_name, variable_name, variable_data in (
            (AREAS_AND_GROUPS_OUTPUT, "AREAS_AND_GROUPS", self._areas_and_groups),
            (CITY_ALL_AREAS_OUTPUT, "CITY_ALL_AREAS", self._city_to_areas),
            (AREA_TO_MIGUN_TIME_OUTPUT, "AREA_TO_MIGUN_TIME", self._area_to_migun_time),
            (DISTRICT_TO_AREAS_OUTPUT, "DISTRICT_AREAS", self._district_to_areas),
            (
                AREAS_OUTPUT,
                "AREAS",
                str(self._areas_no_group).replace("[", "{").replace("]", "}"),
            ),
        ):
            with open(
                file_name,
                "w",
                encoding="utf-8",
            ) as output:
                output.write('"""GENERATED FILE. DO NOT EDIT MANUALLY."""\n\n')
                output.write(f"{variable_name} = {variable_data}")

        with open(
            SERVICES_YAML,
            encoding="utf-8",
        ) as services_yaml:
            services = yaml.load(services_yaml, Loader=yaml.SafeLoader)
        services["add_sensor"]["fields"]["areas"]["selector"]["select"][
            "options"
        ] = self._areas_and_groups
        services["synthetic_alert"]["fields"]["area"]["selector"]["select"][
            "options"
        ] = self._areas_no_group
        with open(
            SERVICES_YAML,
            "w",
            encoding="utf-8",
        ) as output:
            yaml.dump(services, output, sort_keys=False, indent=2, allow_unicode=True)

        subprocess.run(["/usr/local/py-utils/bin/black", OUTPUT_DIRECTORY], check=False)


if __name__ == "__main__":
    OrefMetadata().generate()
