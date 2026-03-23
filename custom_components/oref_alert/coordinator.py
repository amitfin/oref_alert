"""DataUpdateCoordinator for oref_alert integration."""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from http import HTTPStatus
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import homeassistant.util.dt as dt_util
from homeassistant.const import (
    ATTR_DATE,
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from homeassistant.core import callback
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.location import vincenty

from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES
from custom_components.oref_alert.metadata.area_to_district import AREA_TO_DISTRICT

from .categories import (
    END_ALERT_CATEGORY,
    PRE_ALERT_CATEGORY,
    category_is_alert,
    category_is_update,
    category_to_emoji,
    category_to_icon,
    real_time_to_history_category,
)
from .const import (
    AREA_FIELD,
    ATTR_AREA,
    ATTR_DISTRICT,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    ATTR_TYPE,
    CATEGORY_FIELD,
    CHANNEL_FIELD,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DATE_FIELD,
    DOMAIN,
    IST,
    LOGGER,
    MANUAL_EVENT_END_TITLE,
    TITLE_FIELD,
    PublishedData,
    Record,
    RecordAndMetadata,
    RecordSource,
    RecordType,
)
from .metadata.area_info import AREA_INFO
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections import deque
    from collections.abc import AsyncIterator, Callable, Generator, Iterable, Mapping

    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry

CATEGORY_TO_RECORD_TYPE: Final[dict[int, RecordType]] = {
    PRE_ALERT_CATEGORY: RecordType.PRE_ALERT,
    END_ALERT_CATEGORY: RecordType.END,
}
RECORD_EXPIRATION_MINUTES: Final[dict[RecordType, int]] = {
    RecordType.PRE_ALERT: 20,
    RecordType.ALERT: 180,
}
OREF_ALERTS_URL: Final = "https://www.oref.org.il/warningMessages/alert/Alerts.json"
OREF_HISTORY_URL: Final = (
    "https://www.oref.org.il/warningMessages/alert/History/AlertsHistory.json"
)
OREF_HISTORY2_URL: Final = "https://alerts-history.oref.org.il/Shared/Ajax/GetAlarmsHistory.aspx?lang=he&mode=1"
OREF_HEADERS: Final = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
REQUEST_RETRIES: Final = 3
REQUEST_THROTTLING: Final = 0.8
DEDUP_WINDOW_SECONDS: Final = 180
STORAGE_VERSION: Final = 1


@dataclass(frozen=True)
class OrefAlertCoordinatorData:
    """Class for holding coordinator data."""

    areas: Mapping[str, RecordAndMetadata]


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertCoordinatorData]):
    """Class to manage fetching Oref Alert data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
        channels: list[deque[RecordAndMetadata]],
    ) -> None:
        """Initialize global data updater."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
        )
        self._config_entry = config_entry
        self._http_client = async_get_clientsession(hass)
        self._http_replies: dict[str, tuple[str, float]] = {}
        self._channels: list[deque[RecordAndMetadata]] = channels
        self._no_update = True
        self._areas: dict[str, RecordAndMetadata] = {}
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, DOMAIN)
        self.data = OrefAlertCoordinatorData(MappingProxyType({}))

    async def async_restore(self) -> None:
        """Restore cached areas from persistent storage."""
        stored = await self._store.async_load()
        if stored:
            for area, raw_record in stored.get(CONF_AREAS, {}).items():
                try:
                    self._areas[area] = self.add_metadata(Record(**raw_record))
                except Exception:  # noqa: BLE001
                    LOGGER.debug(
                        "Skipping invalid restored area '%s'",
                        area,
                        exc_info=True,
                    )

    async def async_save(self) -> None:
        """Persist current areas to storage as raw records."""
        if not self._no_update:
            cutoff = dt_util.now() - timedelta(days=1)
            await self._store.async_save(
                {
                    CONF_AREAS: {
                        area: record.raw_dict
                        for area, record in self._areas.items()
                        if record.time > cutoff
                    }
                }
            )

    def get_record_and_metadata(
        self,
        areas: Iterable[str] | None,
        record_types: Iterable[RecordType | None] | None,
        window: int | None,
        newer_first: bool,  # noqa: FBT001
    ) -> list[RecordAndMetadata]:
        """Return the records and metadata, sorted and filtered."""
        earliest = dt_util.now() - timedelta(minutes=window) if window else None
        return sorted(
            sorted(
                {
                    record
                    for area, record in self.data.areas.items()
                    if (areas is None or area in areas)
                    and (record_types is None or record.record_type in record_types)
                    and (earliest is None or record.time >= earliest)
                },
                key=lambda record: record.raw.data,
            ),
            key=lambda record: record.time,
            reverse=newer_first,
        )

    def get_records(
        self,
        areas: Iterable[str] | None,
        record_types: Iterable[RecordType | None] | None,
        window: int | None,
    ) -> list[dict[str, str | int]]:
        """Get raw records, sorted from newest, and filtered."""
        return [
            record.raw_dict
            for record in self.get_record_and_metadata(
                areas, record_types, window, newer_first=True
            )
        ]

    def get_record(
        self,
        area: str,
        record_types: Iterable[RecordType | None] | None = None,
    ) -> dict[str, str | int] | None:
        """Return area's record as dict if it matches the types."""
        if (record := self.data.areas.get(area)) is None or (
            record_types and record.record_type not in record_types
        ):
            return None
        return record.raw_dict

    def get_areas_status(
        self, record_types: Iterable[RecordType | None] | None = None
    ) -> dict[str, PublishedData]:
        """Return area's raw records keyed by area, filtered by record type."""
        return {
            area: record.published_data
            for area, record in self.data.areas.items()
            if record.published_data is not None
            and (record_types is None or record.record_type in record_types)
        }

    async def _records_to_process(self) -> AsyncIterator[RecordAndMetadata]:
        """Get records from push channels. Otherwise, from polling channels."""
        if any(channel for channel in self._channels):
            for channel in self._channels:
                while channel:
                    yield channel.popleft()

            # Polling channels are postponed to a follow up refresh.
            self.hass.async_create_task(self.async_refresh())
        else:
            current, history, history2 = await asyncio.gather(
                *[
                    self._async_fetch_url(url)
                    for url in (OREF_ALERTS_URL, OREF_HISTORY_URL, OREF_HISTORY2_URL)
                ]
            )
            for record in itertools.chain(
                self._process_history_alerts(history, self._history_to_record),
                self._process_history_alerts(history2, self._history2_to_record),
                self._current_to_history_format(current),
            ):
                yield record

    def _area_records(
        self, record: RecordAndMetadata
    ) -> Generator[tuple[str, RecordAndMetadata]]:
        """Yield area-specific records for the areas affected by a record."""
        if record.raw.data not in ALL_AREAS_ALIASES:
            yield record.raw.data, record

        else:
            for area in AREAS:
                yield (
                    area,
                    replace(
                        record,
                        published_data=self._build_published_data(
                            area, record.raw, record.time, record.record_type
                        ),
                    ),
                )

    async def _async_update_data(self) -> OrefAlertCoordinatorData:
        """Request the data from Oref channels."""
        # Remove expired records.
        now = dt_util.now()
        self._areas = {
            area: record
            for area, record in self._areas.items()
            if not record.expire or record.expire > now
        }

        # Update the latest areas' records.
        async for record in self._records_to_process():
            # Check if a valid record.
            if (
                not category_is_alert(record.raw.category)
                and not category_is_update(record.raw.category)
            ) or (record.expire and record.expire <= now):
                continue

            # Handle "all areas" record.
            for area, area_record in self._area_records(record):
                # If we don't have anything else for this area.
                if (current := self._areas.get(area)) is None:
                    self._areas[area] = area_record
                    self._no_update = False
                    if area not in AREAS:
                        LOGGER.error("Alert has an unrecognized area: %s", area)
                # If this is not a newer record, or this is "pre" after "alert".
                elif area_record.time <= current.time or (
                    area_record.record_type == RecordType.PRE_ALERT
                    and current.record_type == RecordType.ALERT
                ):
                    continue
                # Same category records within the dedup window are ignored.
                elif (
                    area_record.raw.category != current.raw.category
                    or area_record.time - current.time
                    > timedelta(seconds=DEDUP_WINDOW_SECONDS)
                ):
                    self._areas[area] = area_record
                    self._no_update = False

        return OrefAlertCoordinatorData(MappingProxyType(self._areas))

    def _build_published_data(
        self,
        area: str,
        record: Record,
        record_time: datetime,
        record_type: RecordType | None,
    ) -> PublishedData | None:
        """Build area-specific published data."""
        if not (area_info := AREA_INFO.get(area)) or record_type is None:
            return None

        return {
            ATTR_AREA: area,
            ATTR_HOME_DISTANCE: round(
                vincenty(
                    (self.hass.config.latitude, self.hass.config.longitude),
                    (area_info["lat"], area_info["lon"]),
                )
                or 0,
                1,
            ),
            ATTR_LATITUDE: area_info["lat"],
            ATTR_LONGITUDE: area_info["lon"],
            CATEGORY_FIELD: record.category,
            TITLE_FIELD: record.title,
            ATTR_ICON: category_to_icon(record.category),
            ATTR_EMOJI: category_to_emoji(record.category),
            ATTR_DISTRICT: AREA_TO_DISTRICT.get(area, ""),
            CHANNEL_FIELD: record.channel,
            ATTR_TYPE: record_type.value,
            ATTR_DATE: record_time.isoformat(),
        }

    def add_metadata(
        self, record: Record, record_expire: datetime | None = None
    ) -> RecordAndMetadata:
        """Calculate record metadata."""
        record_time = dt_util.parse_datetime(
            record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST)

        record_type = CATEGORY_TO_RECORD_TYPE.get(record.category, RecordType.ALERT)

        if (
            record_expire is None
            and (expiration := RECORD_EXPIRATION_MINUTES.get(record_type)) is not None
        ):
            record_expire = record_time + timedelta(minutes=expiration)

        return RecordAndMetadata(
            raw=record,
            raw_dict=asdict(record),
            published_data=self._build_published_data(
                record.data, record, record_time, record_type
            ),
            record_type=record_type,
            time=record_time,
            expire=record_expire,
        )

    async def _async_fetch_url(self, url: str) -> Any:
        """Fetch data from Oref servers."""
        exc_info = Exception()
        now = dt_util.now().timestamp()
        last_modified, last_request = self._http_replies.get(url, ("", 0))
        if (now - last_request) < REQUEST_THROTTLING:
            return []
        headers = (
            OREF_HEADERS
            if not last_modified
            else {"If-Modified-Since": last_modified, **OREF_HEADERS}
        )
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.get(url, headers=headers) as response:
                    if response.status == HTTPStatus.NOT_MODIFIED:
                        self._http_replies[url] = (last_modified, now)
                        return []
                    raw = await response.read()
                    text = raw.decode("utf-8-sig").replace("\x00", "").strip()
                    try:
                        content = None if not text else json.loads(text)
                    except:
                        LOGGER.debug(
                            "JSON parsing failed for '%s': '%s' hex: '%s'",
                            url,
                            text,
                            text.encode("utf-8").hex(),
                        )
                        raise
                    self._http_replies[url] = (
                        response.headers.get("Last-Modified", ""),
                        now,
                    )
                    return content or []
            except Exception as ex:  # noqa: BLE001
                exc_info = ex

        LOGGER.info(
            "Failed to fetch '%s'",
            url,
            exc_info=exc_info,
        )
        return []

    def _current_to_history_format(self, current: Any) -> Generator[RecordAndMetadata]:
        """Yield current alerts payload converted to history format."""
        if (
            not isinstance(current, dict)
            or (
                category := real_time_to_history_category(
                    int(current.get("cat", 0)), current[TITLE_FIELD]
                )
            )
            is None
        ):
            # Unknown category. Wait for the history to include it.
            return
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        for area in current[AREA_FIELD]:
            yield self.add_metadata(
                Record(
                    alertDate=now,
                    title=current[TITLE_FIELD],
                    data=self._fix_area_spelling(area),
                    category=category,
                    channel=RecordSource.WEBSITE,
                )
            )

    def add_synthetic_alert(self, details: dict[str, Any]) -> None:
        """Add a synthetic alert for testing purposes."""
        now = dt_util.now(IST)
        expire = now + timedelta(seconds=details[CONF_DURATION])
        for area in details[CONF_AREA]:
            self._areas[area] = self.add_metadata(
                Record(
                    alertDate=now.strftime("%Y-%m-%d %H:%M:%S"),
                    title=details.get(TITLE_FIELD, "התרעה סינטטית לצורכי בדיקות"),
                    data=area,
                    category=details[CATEGORY_FIELD],
                    channel=RecordSource.SYNTHETIC,
                ),
                expire,
            )
            self._no_update = False

    def add_manual_event_end(self, areas: list[str] | None = None) -> None:
        """Set selected active alerts as manual-end records."""
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        for area, current in self._areas.copy().items():
            if current.record_type != RecordType.ALERT:
                continue
            if areas is not None and area not in areas:
                continue
            self._areas[area] = self.add_metadata(
                Record(
                    alertDate=now,
                    title=MANUAL_EVENT_END_TITLE,
                    data=area,
                    category=END_ALERT_CATEGORY,
                    channel=RecordSource.SYNTHETIC,
                )
            )
            self._no_update = False

    @classmethod
    def _history_to_record(cls, record: dict[str, Any]) -> Record:
        """Convert history raw record to to Record."""
        return Record(
            alertDate=record[DATE_FIELD],
            title=record[TITLE_FIELD],
            data=cls._fix_area_spelling(record[AREA_FIELD]),
            category=record[CATEGORY_FIELD],
            channel=RecordSource.HISTORY,
        )

    @classmethod
    def _history2_to_record(cls, record: dict[str, Any]) -> Record:
        """Convert history2 raw record to to Record."""
        return Record(
            alertDate=record[DATE_FIELD].replace("T", " "),
            title=record["category_desc"],
            data=cls._fix_area_spelling(record[AREA_FIELD]),
            category=record[CATEGORY_FIELD],
            channel=RecordSource.HISTORY,
        )

    def _process_history_alerts(
        self,
        records: list[dict[str, Any]],
        payload_to_record: Callable[[dict[str, Any]], Record],
    ) -> Generator[RecordAndMetadata]:
        """Yield latest history record per area with metadata."""
        now = dt_util.now()
        areas = set()
        for record in records:
            if record[AREA_FIELD] in areas:
                continue
            areas.add(record[AREA_FIELD])
            record_meta = self.add_metadata(payload_to_record(record))
            yield record_meta

            # Post initial fetch, take only recent records.
            if not self._no_update and (now - record_meta.time) > timedelta(minutes=5):
                break

    @staticmethod
    def _fix_area_spelling(area: str) -> str:
        """Fix spelling error in area name."""
        if area[0] == "'":
            area = f"{area[1:]}'"
        return area


class OrefAlertCoordinatorUpdater:
    """Refresh coordinator if there are active alerts / updates."""

    def __init__(
        self, hass: HomeAssistant, coordinator: OrefAlertDataUpdateCoordinator
    ) -> None:
        """Initialize the updater."""
        self._hass: HomeAssistant = hass
        self._coordinator: OrefAlertDataUpdateCoordinator = coordinator
        self._active: datetime = dt_util.now() - timedelta(days=1)
        self._update: datetime = dt_util.now()
        self._stop: bool = False
        self._unsub_update: Callable[[], None] | None = None

    def _sub(self) -> None:
        """Subscribe an update."""
        if not self._stop:
            self._unsub_update = event_helper.async_track_point_in_time(
                self._hass,
                self._async_update,
                dt_util.now() + timedelta(seconds=2),
            )

    @callback
    async def _async_update(self, *_: Any) -> None:
        """Refresh coordinator if needed."""
        self._unsub_update = None
        now = dt_util.now()
        update = False
        if any(
            record.record_type in (RecordType.ALERT, RecordType.PRE_ALERT)
            for record in self._coordinator.data.areas.values()
        ):
            self._active = now
            update = True
        elif now - self._active < timedelta(
            minutes=10
        ) or now - self._update > timedelta(seconds=20):
            update = True
        if update:
            self._update = now
            await self._coordinator.async_refresh()
        self._sub()

    def start(self) -> None:
        """Start the updater."""
        self._sub()

    def stop(self) -> None:
        """Stop the updater."""
        self._stop = True
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None
