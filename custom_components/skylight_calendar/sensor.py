"""Sensor entities for a Skylight frame.

Entities:
- chores_today: count + rich per-chore details (description, emoji, RRULE,
  scheduled start time, reward points, assignee label).
- meals_today: count + per-meal details (category label, recipe title,
  description, note, RRULE) resolved from JSON:API `included` payload.
- task_box: reusable chore-template items ('Task Box' on the frame).
- <profile>_stars: reward-star balance per family-member profile.
"""

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
        SkylightTaskBoxSensor(coord, frame_id, frame_name),
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


def _category_label_map(data: dict) -> dict[str, str]:
    """id -> label lookup covering all categories (profiles + calendar buckets)."""
    cats = (data.get("categories") or {}).get("data", [])
    return {
        str(c.get("id")): c.get("attributes", {}).get("label", "")
        for c in cats
    }


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
            model="Skylight Frame",
        )


# ── Chores ──────────────────────────────────────────────────────────────

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
        cat_map = _category_label_map(self.coordinator.data or {})
        result = []
        for c in self._today_chores():
            attrs = c.get("attributes", {}) if isinstance(c, dict) else {}
            rel = (c.get("relationships", {}) or {}).get("category", {}) or {}
            cat_id = (rel.get("data") or {}).get("id") or attrs.get("category_id")
            rrules = attrs.get("recurrence_set") or []
            rrule = rrules[0] if rrules else None
            result.append(
                {
                    "id": c.get("id"),
                    "summary": attrs.get("summary") or attrs.get("name"),
                    "description": attrs.get("description"),
                    "emoji": attrs.get("emoji_icon"),
                    "status": attrs.get("status"),
                    "reward_points": attrs.get("reward_points"),
                    "start_date": attrs.get("start") or attrs.get("date"),
                    "start_time": attrs.get("start_time"),
                    "completed_on": attrs.get("completed_on"),
                    "recurring": attrs.get("recurring"),
                    "recurrence_rrule": rrule,
                    "routine": attrs.get("routine"),
                    "up_for_grabs": attrs.get("up_for_grabs"),
                    "timer_seconds": attrs.get("timer_seconds"),
                    "assignee_id": cat_id,
                    "assignee": cat_map.get(str(cat_id)) if cat_id else None,
                }
            )
        return {"chores": result}


# ── Meals ───────────────────────────────────────────────────────────────

class SkylightMealsTodaySensor(_SkylightBaseSensor):
    _attr_name = "Meals today"
    _attr_icon = "mdi:silverware-fork-knife"

    def __init__(self, coordinator, frame_id, frame_name):
        super().__init__(coordinator, frame_id, frame_name)
        self._attr_unique_id = f"skylight_{frame_id}_meals_today"

    def _included_map(self) -> tuple[dict[str, dict], dict[str, dict]]:
        """Return (meal_category_by_id, meal_recipe_by_id) from included."""
        inc = (self.coordinator.data or {}).get("meals_included") or []
        cats = {str(i["id"]): i for i in inc if i.get("type") == "meal_category"}
        recipes = {str(i["id"]): i for i in inc if i.get("type") == "meal_recipe"}
        return cats, recipes

    def _today_meals(self) -> list[dict]:
        """Meals with an 'instances' entry for today."""
        today = dt_util.now().date().isoformat()
        raw = (self.coordinator.data or {}).get("meals")
        if raw is None:
            return []
        entries = raw if isinstance(raw, list) else raw.get("data", [])
        out = []
        for m in entries:
            attrs = m.get("attributes", {}) if isinstance(m, dict) else {}
            # Skylight puts scheduled dates in `instances` (list of ISO dates)
            instances = attrs.get("instances") or []
            date_field = attrs.get("date") or attrs.get("starts_at") or ""
            if today in instances or (
                isinstance(date_field, str) and date_field.startswith(today)
            ):
                out.append(m)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_meals())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cats, recipes = self._included_map()
        result = []
        for m in self._today_meals():
            attrs = m.get("attributes", {}) if isinstance(m, dict) else {}
            rels = m.get("relationships", {}) or {}
            cat_id = ((rels.get("meal_category") or {}).get("data") or {}).get("id")
            recipe_id = ((rels.get("meal_recipe") or {}).get("data") or {}).get("id")
            cat_label = None
            recipe_title = None
            recipe_desc = None
            if cat_id and str(cat_id) in cats:
                cat_label = cats[str(cat_id)].get("attributes", {}).get("label")
            if recipe_id and str(recipe_id) in recipes:
                r_attrs = recipes[str(recipe_id)].get("attributes", {})
                recipe_title = r_attrs.get("summary")
                recipe_desc = r_attrs.get("description")
            result.append(
                {
                    "id": m.get("id"),
                    "summary": attrs.get("summary"),
                    "description": attrs.get("description"),
                    "note": attrs.get("note"),
                    "category_id": cat_id,
                    "category": cat_label,
                    "recipe_id": recipe_id,
                    "recipe_title": recipe_title,
                    "recipe_description": recipe_desc,
                    "recurring": attrs.get("recurring"),
                    "recurrence_rrule": attrs.get("rrule"),
                    "instances": attrs.get("instances"),
                }
            )
        return {"meals": result}


# ── Task Box ────────────────────────────────────────────────────────────

class SkylightTaskBoxSensor(_SkylightBaseSensor):
    """Reusable chore-template items — the frame's Task Box."""

    _attr_name = "Task box"
    _attr_icon = "mdi:clipboard-list-outline"

    def __init__(self, coordinator, frame_id, frame_name):
        super().__init__(coordinator, frame_id, frame_name)
        self._attr_unique_id = f"skylight_{frame_id}_task_box"

    def _items(self) -> list[dict]:
        raw = (self.coordinator.data or {}).get("task_box")
        if raw is None:
            return []
        entries = raw if isinstance(raw, list) else raw.get("data", [])
        return [e for e in entries if isinstance(e, dict)]

    @property
    def native_value(self) -> int:
        return len(self._items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": e.get("id"),
                    "summary": e.get("attributes", {}).get("summary"),
                    "emoji": e.get("attributes", {}).get("emoji_icon"),
                    "reward_points": e.get("attributes", {}).get("reward_points"),
                    "routine": e.get("attributes", {}).get("routine"),
                }
                for e in self._items()
            ]
        }


# ── Reward stars ────────────────────────────────────────────────────────

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
        """Flat-list response: [{'category_id': 20939825, 'current_point_balance': 149}, ...]."""
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rp = (self.coordinator.data or {}).get("reward_points")
        if rp is None:
            return {}
        entries = rp if isinstance(rp, list) else rp.get("data", [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("category_id")) == str(self._category_id):
                return {
                    "lifetime_points_earned": entry.get("lifetime_points_earned"),
                    "current_point_balance": entry.get("current_point_balance"),
                }
        return {}
