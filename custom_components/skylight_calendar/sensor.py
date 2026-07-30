"""Sensor entities: chores/meals + per-member breakdowns, per-slot meals, star totals."""

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

from .const import DOMAIN, MEAL_CATEGORY_NAMES
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

    # Per-member profile categories → chores + rewards sensors.
    for cat_id, label in _profile_categories(coord.data or {}):
        entities.append(
            SkylightRewardPointsSensor(coord, frame_id, frame_name, cat_id, label)
        )
        entities.append(
            SkylightMemberChoresSensor(coord, frame_id, frame_name, cat_id, label)
        )

    # Per-slot meal sensors (Breakfast/Lunch/Dinner/Snack) — always present so cards work
    # even when no meal is planned for a slot.
    for cat_id, label in MEAL_CATEGORY_NAMES.items():
        entities.append(
            SkylightMealSlotSensor(coord, frame_id, frame_name, cat_id, label)
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


def _chore_entries(data: dict) -> list[dict]:
    raw = (data or {}).get("chores")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else raw.get("data", []) or []


def _meal_entries(data: dict) -> list[dict]:
    raw = (data or {}).get("meals")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else raw.get("data", []) or []


def _chore_assignee_id(c: dict) -> str | None:
    attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
    rel = (c.get("relationships", {}) or {}).get("category", {}) or {}
    data = rel.get("data") or {}
    return str(data.get("id") or attrs.get("category_id") or "") or None


def _chore_when(attrs: dict) -> str:
    return (
        attrs.get("start")
        or attrs.get("date")
        or attrs.get("due_date")
        or ""
    )


def _meal_when(attrs: dict) -> str:
    return attrs.get("date") or attrs.get("starts_at") or ""


def _meal_category_id(m: dict) -> str | None:
    rel = (m.get("relationships", {}) or {}).get("meal_category", {}) or {}
    data = rel.get("data") or {}
    return str(data.get("id") or "") or None


def _status_breakdown(items: list[dict]) -> dict[str, int]:
    """Aggregate {status: count} across a chore/list."""
    out: dict[str, int] = {}
    for it in items:
        attrs = it.get("attributes", {}) if isinstance(it, dict) else {}
        s = attrs.get("status") or "unknown"
        out[s] = out.get(s, 0) + 1
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
        out = []
        for c in _chore_entries(self.coordinator.data or {}):
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            due = _chore_when(attrs)
            if isinstance(due, str) and due.startswith(today):
                out.append(c)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_chores())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        chores = self._today_chores()
        result = []
        for c in chores:
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            result.append(
                {
                    "id": c.get("id"),
                    "summary": attrs.get("summary") or attrs.get("name"),
                    "status": attrs.get("status"),
                    "reward_points": attrs.get("reward_points"),
                    "start": _chore_when(attrs),
                    "assignee_id": _chore_assignee_id(c),
                }
            )
        return {"chores": result, "by_status": _status_breakdown(chores)}


class SkylightMemberChoresSensor(_SkylightBaseSensor):
    """Chores today for a single family member."""

    _attr_icon = "mdi:broom"

    def __init__(self, coordinator, frame_id, frame_name, category_id: str, label: str):
        super().__init__(coordinator, frame_id, frame_name)
        self._category_id = str(category_id)
        self._attr_name = f"{label} chores today"
        self._attr_unique_id = f"skylight_{frame_id}_chores_today_{category_id}"

    def _member_chores(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        out = []
        for c in _chore_entries(self.coordinator.data or {}):
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            if not _chore_when(attrs).startswith(today):
                continue
            if _chore_assignee_id(c) != self._category_id:
                continue
            out.append(c)
        return out

    @property
    def native_value(self) -> int:
        return len(self._member_chores())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        chores = self._member_chores()
        return {
            "chores": [
                {
                    "id": c.get("id"),
                    "summary": (c.get("attributes") or {}).get("summary")
                    or (c.get("attributes") or {}).get("name"),
                    "status": (c.get("attributes") or {}).get("status"),
                    "reward_points": (c.get("attributes") or {}).get("reward_points"),
                    "start": _chore_when(c.get("attributes") or {}),
                }
                for c in chores
            ],
            "by_status": _status_breakdown(chores),
        }


class SkylightMealsTodaySensor(_SkylightBaseSensor):
    _attr_name = "Meals today"
    _attr_icon = "mdi:silverware-fork-knife"

    def __init__(self, coordinator, frame_id, frame_name):
        super().__init__(coordinator, frame_id, frame_name)
        self._attr_unique_id = f"skylight_{frame_id}_meals_today"

    def _today_meals(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        out = []
        for m in _meal_entries(self.coordinator.data or {}):
            attrs = m.get("attributes", {}) if isinstance(m, dict) else {}
            if _meal_when(attrs).startswith(today):
                out.append(m)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_meals())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        meals = self._today_meals()
        by_slot: dict[str, int] = {name: 0 for name in MEAL_CATEGORY_NAMES.values()}
        for m in meals:
            cat_id = _meal_category_id(m)
            slot = MEAL_CATEGORY_NAMES.get(cat_id or "", "Other")
            by_slot[slot] = by_slot.get(slot, 0) + 1
        return {
            "meals": [
                {
                    "id": m.get("id"),
                    "summary": (m.get("attributes") or {}).get("summary"),
                    "date": _meal_when(m.get("attributes") or {}),
                    "category": MEAL_CATEGORY_NAMES.get(
                        _meal_category_id(m) or "", "Other"
                    ),
                }
                for m in meals
            ],
            "by_slot": by_slot,
        }


class SkylightMealSlotSensor(_SkylightBaseSensor):
    """One entity per meal slot (Breakfast/Lunch/Dinner/Snack)."""

    _attr_icon = "mdi:silverware-fork-knife"

    def __init__(self, coordinator, frame_id, frame_name, category_id: str, label: str):
        super().__init__(coordinator, frame_id, frame_name)
        self._category_id = str(category_id)
        self._slot_label = label
        self._attr_name = f"{label} today"
        self._attr_unique_id = f"skylight_{frame_id}_meal_slot_{category_id}"

    def _slot_meals(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        out = []
        for m in _meal_entries(self.coordinator.data or {}):
            attrs = m.get("attributes", {}) if isinstance(m, dict) else {}
            if not _meal_when(attrs).startswith(today):
                continue
            if _meal_category_id(m) != self._category_id:
                continue
            out.append(m)
        return out

    @property
    def native_value(self) -> str:
        meals = self._slot_meals()
        if not meals:
            return "none"
        summaries = [
            (m.get("attributes") or {}).get("summary") or "?"
            for m in meals
        ]
        return ", ".join(summaries)[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "count": len(self._slot_meals()),
            "meals": [
                {
                    "id": m.get("id"),
                    "summary": (m.get("attributes") or {}).get("summary"),
                    "description": (m.get("attributes") or {}).get("description"),
                    "note": (m.get("attributes") or {}).get("note"),
                }
                for m in self._slot_meals()
            ],
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
        rp = (self.coordinator.data or {}).get("reward_points")
        if rp is None:
            return None
        entries = rp if isinstance(rp, list) else rp.get("data", [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("category_id")) == str(self._category_id):
                return entry.get("current_point_balance") or entry.get("balance")
            attrs = entry.get("attributes", {})
            rel = (entry.get("relationships", {}) or {}).get("category", {}) or {}
            data = rel.get("data") or {}
            if str(data.get("id")) == str(self._category_id):
                return (
                    attrs.get("current_point_balance")
                    or attrs.get("balance")
                    or attrs.get("points")
                )
        return None
