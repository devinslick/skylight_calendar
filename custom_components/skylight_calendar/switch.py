"""Switch platform: Skylight frame sleep mode."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SkylightAPI
from .const import DOMAIN
from .coordinator import SkylightFrameCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SkylightSleepModeSwitch(
                data["frame_coordinator"], data["api"], data["frame_id"], data["frame_name"]
            )
        ]
    )


class SkylightSleepModeSwitch(
    CoordinatorEntity[SkylightFrameCoordinator], SwitchEntity
):
    _attr_has_entity_name = True
    _attr_name = "Sleep mode"
    _attr_icon = "mdi:sleep"

    def __init__(
        self,
        coordinator: SkylightFrameCoordinator,
        api: SkylightAPI,
        frame_id: str,
        frame_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._frame_id = frame_id
        self._attr_unique_id = f"skylight_{frame_id}_sleep_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, frame_id)},
            name=frame_name,
            manufacturer="Skylight",
            model="Calendar Frame",
        )

    @property
    def is_on(self) -> bool | None:
        return bool((self.coordinator.data or {}).get("sleep_mode_on"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._api.patch_frame(self._frame_id, {"sleep_mode_on": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._api.patch_frame(self._frame_id, {"sleep_mode_on": False})
        await self.coordinator.async_request_refresh()
