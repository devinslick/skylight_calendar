"""Sensor entities: chores today, meals today, per-profile reward stars."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SkylightSensorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: SkylightSensorCoordinator = data["sensor_coordinator"]
    frame_id: str = data["frame_id"]
    frame_name: str = data["frame_name"]

    entities: list[SensorEntity] = [
        SkylightChoresTodaySensor(coord, frame_id, frame_name),
        SkylightMealsTodaySensor(coord, frame_id, frame_name),
    ]

    for cat_id, label in _profile_categories(coord.data or {}):
        entities.append(
            SkylightRewardPointsSensor(coord, frame_id, frame_name, cat_id, label)
        )

    async_add_entities(entities)


def _profile_categories(data: dict) -> list[tuple[str, str]]:
    """Extract (category_id, label) for family-member profiles only."""
    cats = (data.get("categories") or {}).get("data", [])
    out: list[tuple[str, str]] = []
    for c in cats:
        attrs = c.get("attributes", {})
        if not attrs.get("linked_to_profile"):
            continue
        label = attrs.get("label", "")
        if "@" in label:  # skip Google-calendar sub-category entries
            continue
        out.append((str(c.get("id")), label))
    return out


class _SkylightBaseSensor(CoordinatorEntity[SkylightSensorCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SkylightSensorCoordinator,
        frame_id: str,
        frame_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._frame_id = frame_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, frame_id)},
            name=frame_name,
            manufacturer="Skylight",
            model="Calendar Frame",
        )


class SkylightChoresTodaySensor(_SkylightBaseSensor):
    _attr_name = "Chores today"
    _attr_icon = "mdi:broom"

    def __init__(self, coordinator, frame_id, frame_name):
        super().__init__(coordinator, frame_id, frame_name)
        self._attr_unique_id = f"skylight_{frame_id}_chores_today"

    def _today_chores(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        raw = (self.coordinator.data or {}).get("chores")
        if raw is None:
            return []
        # Chores endpoint returns either a flat list OR a JSON:API {"data": [...]}
        entries = raw if isinstance(raw, list) else raw.get("data", [])
        out = []
        for c in entries:
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            due = attrs.get("start") or attrs.get("date") or attrs.get("due_date") or ""
            if isinstance(due, str) and due.startswith(today):
                out.append(c)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_chores())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = []
        for c in self._today_chores():
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            rel = (c.get("relationships", {}) or {}).get("category", {}) or {}
            data = rel.get("data") or {}
            result.append(
                {
                    "id": c.get("id"),
                    "summary": attrs.get("summary") or attrs.get("name"),
                    "status": attrs.get("status"),
                    "reward_points": attrs.get("reward_points"),
                    "start": attrs.get("start") or attrs.get("date"),
                    "assignee_id": data.get("id") or attrs.get("category_id"),
                }
            )
        return {"chores": result}


class SkylightMealsTodaySensor(_SkylightBaseSensor):
    _attr_name = "Meals today"
    _attr_icon = "mdi:silverware-fork-knife"

    def __init__(self, coordinator, frame_id, frame_name):
        super().__init__(coordinator, frame_id, frame_name)
        self._attr_unique_id = f"skylight_{frame_id}_meals_today"

    def _today_meals(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        raw = (self.coordinator.data or {}).get("meals")
        if raw is None:
            return []
        entries = raw if isinstance(raw, list) else raw.get("data", [])
        out = []
        for m in entries:
            attrs = m.get("attributes", {}) if isinstance(m, dict) else {}
            when = attrs.get("date") or attrs.get("starts_at") or ""
            if isinstance(when, str) and when.startswith(today):
                out.append(m)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_meals())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "meals": [
                {
                    "id": m.get("id"),
                    "summary": m.get("attributes", {}).get("summary"),
                    "date": m.get("attributes", {}).get("date"),
                }
                for m in self._today_meals()
            ]
        }


class SkylightRewardPointsSensor(_SkylightBaseSensor):
    _attr_icon = "mdi:star-circle"
    _attr_native_unit_of_measurement = "★"

    def __init__(
        self,
        coordinator: SkylightSensorCoordinator,
        frame_id: str,
        frame_name: str,
        category_id: str,
        label: str,
    ) -> None:
        super().__init__(coordinator, frame_id, frame_name)
        self._category_id = category_id
        self._attr_name = f"{label} stars"
        self._attr_unique_id = f"skylight_{frame_id}_stars_{category_id}"

    @property
    def native_value(self) -> int | None:
        """Skylight /reward_points returns a flat list of dicts:
        [{"category_id": 20939825, "current_point_balance": 149, ...}, ...]
        """
        rp = (self.coordinator.data or {}).get("reward_points")
        if rp is None:
            return None
        entries = rp if isinstance(rp, list) else rp.get("data", [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Flat list shape
            if str(entry.get("category_id")) == str(self._category_id):
                return entry.get("current_point_balance") or entry.get("balance")
            # JSON:API shape (fallback)
            attrs = entry.get("attributes", {})
            rel = (entry.get("relationships", {}) or {}).get("category", {}) or {}
            data = rel.get("data") or {}
            if str(data.get("id")) == str(self._category_id):
                return attrs.get("current_point_balance") or attrs.get("balance") or attrs.get("points")
        return None
