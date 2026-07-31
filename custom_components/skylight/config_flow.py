"""Config flow for Skylight (manual OAuth2 token capture)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkylightAPI, SkylightAuthError, exchange_refresh_token
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_FINGERPRINT,
    CONF_FRAME_ID,
    CONF_FRAME_NAME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Optional(CONF_DEVICE_FINGERPRINT, default=""): str,
    }
)


class SkylightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the manual-token OAuth2 config flow."""

    VERSION = 2

    def __init__(self) -> None:
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._device_fingerprint: str = ""
        self._frames: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            refresh = user_input[CONF_REFRESH_TOKEN].strip()
            fingerprint = user_input.get(CONF_DEVICE_FINGERPRINT, "").strip()

            try:
                new_pair = await exchange_refresh_token(session, refresh, fingerprint)
            except SkylightAuthError as err:
                _LOGGER.warning("Refresh token exchange failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error verifying Skylight tokens")
                errors["base"] = "cannot_connect"

            if not errors:
                self._access_token = new_pair["access_token"]
                self._refresh_token = new_pair["refresh_token"]
                self._device_fingerprint = fingerprint

                api = SkylightAPI(
                    session=session,
                    access_token=self._access_token,
                    refresh_token=self._refresh_token,
                    device_fingerprint=fingerprint,
                )
                try:
                    self._frames = await api.get_frames()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Failed to list frames")
                    errors["base"] = "cannot_connect"

                if not errors:
                    if not self._frames:
                        errors["base"] = "no_frames"
                    elif len(self._frames) == 1:
                        return await self._create_entry(self._frames[0])
                    else:
                        return await self.async_step_select_frame()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_select_frame(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            frame_id = user_input[CONF_FRAME_ID]
            frame = next((f for f in self._frames if f["id"] == frame_id), None)
            if frame:
                return await self._create_entry(frame)

        options = {f["id"]: f["name"] for f in self._frames}
        return self.async_show_form(
            step_id="select_frame",
            data_schema=vol.Schema({vol.Required(CONF_FRAME_ID): vol.In(options)}),
        )

    async def _create_entry(self, frame: dict) -> FlowResult:
        await self.async_set_unique_id(f"skylight_frame_{frame['id']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=frame["name"],
            data={
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
                CONF_DEVICE_FINGERPRINT: self._device_fingerprint,
                CONF_FRAME_ID: frame["id"],
                CONF_FRAME_NAME: frame["name"],
            },
        )
