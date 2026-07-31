"""DataUpdateCoordinators for Skylight resources."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SkylightAPI, SkylightAPIError, SkylightAuthError
from .const import (
    CALENDAR_SCAN_INTERVAL,
    DOMAIN,
    LISTS_SCAN_INTERVAL,
    SENSOR_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SkylightCalendarCoordinator(DataUpdateCoordinator):
    """Fetch calendar events for a rolling window centered on today."""

    def __init__(self, hass: HomeAssistant, api: SkylightAPI, frame_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} calendar {frame_id}",
            update_interval=timedelta(seconds=CALENDAR_SCAN_INTERVAL),
        )
        self.api = api
        self.frame_id = frame_id

    async def _async_update_data(self) -> dict:
        today = dt_util.now().date()
        date_min = (today - timedelta(days=14)).isoformat()
        date_max = (today + timedelta(days=60)).isoformat()
        tz = getattr(self.hass.config, "time_zone", "UTC") or "UTC"
        try:
            return await self.api.get_calendar_events(
                self.frame_id, date_min, date_max, timezone=tz
            )
        except SkylightAuthError as err:
            raise UpdateFailed(f"Auth failed: {err}") from err
        except SkylightAPIError as err:
            raise UpdateFailed(str(err)) from err


class SkylightListsCoordinator(DataUpdateCoordinator):
    """Fetch every list + its items."""

    def __init__(self, hass: HomeAssistant, api: SkylightAPI, frame_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} lists {frame_id}",
            update_interval=timedelta(seconds=LISTS_SCAN_INTERVAL),
        )
        self.api = api
        self.frame_id = frame_id

    async def _async_update_data(self) -> dict:
        try:
            lists_resp = await self.api.get_lists(self.frame_id)
        except SkylightAuthError as err:
            raise UpdateFailed(f"Auth failed: {err}") from err
        except SkylightAPIError as err:
            raise UpdateFailed(str(err)) from err

        out: dict[str, dict] = {}
        for entry in lists_resp.get("data", []):
            lid = str(entry.get("id"))
            attrs = entry.get("attributes", {})
            try:
                detail = await self.api.get_list_items(self.frame_id, lid)
            except (SkylightAuthError, SkylightAPIError) as err:
                _LOGGER.warning("Failed to fetch items for list %s: %s", lid, err)
                continue
            items = []
            # Skylight uses "label" for the item text and the include payload
            # may be the top-level `included` array OR embedded via relationships.
            for inc in detail.get("included", []) or []:
                if inc.get("type") != "list_item":
                    continue
                i_attrs = inc.get("attributes", {})
                items.append(
                    {
                        "id": str(inc.get("id")),
                        "name": i_attrs.get("label", ""),
                        "status": i_attrs.get("status", "pending"),
                        "position": i_attrs.get("position", 0) or 0,
                    }
                )
            items.sort(key=lambda x: x["position"])
            out[lid] = {
                "id": lid,
                "name": attrs.get("label", f"List {lid}"),
                "color": attrs.get("color"),
                "kind": attrs.get("kind"),
                "items": items,
            }
        return out


class SkylightSensorCoordinator(DataUpdateCoordinator):
    """Aggregate chores + meals + rewards + categories for sensors."""

    def __init__(self, hass: HomeAssistant, api: SkylightAPI, frame_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} sensors {frame_id}",
            update_interval=timedelta(seconds=SENSOR_SCAN_INTERVAL),
        )
        self.api = api
        self.frame_id = frame_id

    async def _async_update_data(self) -> dict:
        today = dt_util.now().date()
        week_end = (today + timedelta(days=7)).isoformat()
        result: dict = {
            "chores": None,
            "meals": None,
            "meals_included": [],
            "reward_points": None,
            "categories": None,
            "task_box": None,
        }
        try:
            result["chores"] = await self.api.get_chores(
                self.frame_id, today.isoformat(), week_end
            )
        except (SkylightAuthError, SkylightAPIError) as err:
            _LOGGER.debug("chores fetch failed: %s", err)
        try:
            meals = await self.api.get_meals(
                self.frame_id, today.isoformat(), week_end
            )
            result["meals"] = meals
            # Extract included meal_category + meal_recipe lookup tables
            if isinstance(meals, dict):
                result["meals_included"] = meals.get("included", []) or []
        except (SkylightAuthError, SkylightAPIError) as err:
            _LOGGER.debug("meals fetch failed: %s", err)
        try:
            result["reward_points"] = await self.api.get_reward_points(self.frame_id)
        except (SkylightAuthError, SkylightAPIError) as err:
            _LOGGER.debug("reward_points fetch failed: %s", err)
        try:
            result["categories"] = await self.api.get_categories(self.frame_id)
        except (SkylightAuthError, SkylightAPIError) as err:
            _LOGGER.debug("categories fetch failed: %s", err)
        try:
            result["task_box"] = await self.api.get_task_box(self.frame_id)
        except (SkylightAuthError, SkylightAPIError) as err:
            _LOGGER.debug("task_box fetch failed: %s", err)
        return result
