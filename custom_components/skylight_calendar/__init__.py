"""The Skylight Calendar integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkylightAPI
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_FINGERPRINT,
    CONF_FRAME_ID,
    CONF_FRAME_NAME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    PLATFORM_CALENDAR,
    PLATFORM_SENSOR,
    PLATFORM_TODO,
)
from .coordinator import (
    SkylightCalendarCoordinator,
    SkylightListsCoordinator,
    SkylightSensorCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [PLATFORM_CALENDAR, PLATFORM_TODO, PLATFORM_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Skylight frame from a config entry."""
    session = async_get_clientsession(hass)

    access_token = entry.data.get(CONF_ACCESS_TOKEN)
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    device_fp = entry.data.get(CONF_DEVICE_FINGERPRINT, "")
    frame_id = entry.data.get(CONF_FRAME_ID)
    frame_name = entry.data.get(CONF_FRAME_NAME) or f"Skylight Frame {frame_id}"

    if not access_token or not refresh_token or not frame_id:
        _LOGGER.error(
            "Skylight config entry incomplete (missing tokens or frame_id) — "
            "please remove and re-add the integration"
        )
        return False

    async def _persist_tokens(new_access: str, new_refresh: str, new_fp: str | None) -> None:
        new_data = {
            **entry.data,
            CONF_ACCESS_TOKEN: new_access,
            CONF_REFRESH_TOKEN: new_refresh,
        }
        if new_fp:
            new_data[CONF_DEVICE_FINGERPRINT] = new_fp
        hass.config_entries.async_update_entry(entry, data=new_data)

    api = SkylightAPI(
        session=session,
        access_token=access_token,
        refresh_token=refresh_token,
        device_fingerprint=device_fp,
        token_update_cb=_persist_tokens,
    )

    calendar_coord = SkylightCalendarCoordinator(hass, api, frame_id)
    lists_coord = SkylightListsCoordinator(hass, api, frame_id)
    sensor_coord = SkylightSensorCoordinator(hass, api, frame_id)

    await calendar_coord.async_config_entry_first_refresh()
    await lists_coord.async_config_entry_first_refresh()
    await sensor_coord.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "frame_id": frame_id,
        "frame_name": frame_name,
        "calendar_coordinator": calendar_coord,
        "lists_coordinator": lists_coord,
        "sensor_coordinator": sensor_coord,
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, frame_id)},
        manufacturer="Skylight",
        name=frame_name,
        model="Calendar Frame",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
