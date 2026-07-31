"""Calendar entity for a Skylight frame."""

from __future__ import annotations

from datetime import datetime
import logging

from dateutil.parser import parse as parse_datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SkylightCalendarCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: SkylightCalendarCoordinator = data["calendar_coordinator"]
    async_add_entities(
        [SkylightCalendar(coord, data["frame_id"], data["frame_name"])]
    )


class SkylightCalendar(CoordinatorEntity[SkylightCalendarCoordinator], CalendarEntity):
    _attr_has_entity_name = True
    _attr_name = "Calendar"

    def __init__(
        self,
        coordinator: SkylightCalendarCoordinator,
        frame_id: str,
        frame_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._frame_id = frame_id
        self._attr_unique_id = f"skylight_{frame_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, frame_id)},
            name=frame_name,
            manufacturer="Skylight",
            model="Calendar Frame",
        )

    def _all_events(self) -> list[CalendarEvent]:
        raw = self.coordinator.data or {}
        events: list[CalendarEvent] = []
        for ev in raw.get("data", []):
            attrs = ev.get("attributes", {})
            starts = attrs.get("starts_at")
            ends = attrs.get("ends_at")
            if not starts or not ends:
                continue
            try:
                start_dt = parse_datetime(starts)
                end_dt = parse_datetime(ends)
            except (ValueError, TypeError):
                continue
            events.append(
                CalendarEvent(
                    start=start_dt,
                    end=end_dt,
                    summary=attrs.get("summary") or "Skylight Event",
                    description=attrs.get("description") or "",
                    location=attrs.get("location") or "",
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        for ev in self._all_events():
            start = ev.start if isinstance(ev.start, datetime) else None
            end = ev.end if isinstance(ev.end, datetime) else None
            if start and end and start <= now <= end:
                return ev
        upcoming = [
            e for e in self._all_events()
            if isinstance(e.start, datetime) and e.start >= now
        ]
        upcoming.sort(key=lambda e: e.start)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        result = []
        for ev in self._all_events():
            ev_start = ev.start if isinstance(ev.start, datetime) else None
            ev_end = ev.end if isinstance(ev.end, datetime) else None
            if not ev_start or not ev_end:
                continue
            if ev_end < start_date or ev_start > end_date:
                continue
            result.append(ev)
        return result
