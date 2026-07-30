"""Async Skylight API client with OAuth2 Bearer + refresh_token cascade."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import json as _json
import logging
from typing import Any

import aiohttp
from yarl import URL

from .const import API_VERSION, BASE_URL, CLIENT_ID, OAUTH_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

TokenUpdateCallback = Callable[[str, str, str | None], Awaitable[None]]


class SkylightAuthError(Exception):
    """Raised when authentication fails and cannot be recovered."""


class SkylightAPIError(Exception):
    """Raised on non-401 HTTP failures."""


class SkylightAPI:
    """Async Skylight API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str,
        device_fingerprint: str | None = None,
        token_update_cb: TokenUpdateCallback | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._device_fingerprint = device_fingerprint or ""
        self._token_update_cb = token_update_cb

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        _retry: bool = True,
    ) -> Any:
        url = URL(f"{BASE_URL}{path}")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": USER_AGENT,
            "Skylight-Api-Version": API_VERSION,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        clean_params = None
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}

        async with self._session.request(
            method,
            url,
            headers=headers,
            params=clean_params,
            json=json_body,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 401 and _retry:
                _LOGGER.debug("Skylight 401 on %s — refreshing token", path)
                await self._refresh_access_token()
                return await self._request(
                    method, path, params=params, json_body=json_body, _retry=False
                )
            if resp.status == 401:
                raise SkylightAuthError("Skylight auth failed after refresh")
            if resp.status >= 400:
                text = await resp.text()
                raise SkylightAPIError(f"{method} {path} → {resp.status}: {text[:200]}")
            text = await resp.text()
            if not text:
                return {}
            return _json.loads(text)

    async def _refresh_access_token(self) -> None:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
            "scope": "everything",
            "skylight_api_client_device_fingerprint": self._device_fingerprint,
            "skylight_api_client_device_platform": "web",
            "skylight_api_client_device_name": "home-assistant",
            "skylight_api_client_device_os_version": "10",
            "skylight_api_client_device_app_version": "unknown",
            "skylight_api_client_device_hardware": "3",
            "source": "web",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        async with self._session.post(
            OAUTH_URL,
            data=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise SkylightAuthError(
                    f"OAuth refresh failed ({resp.status}): {body[:200]}"
                )
            data = _json.loads(body)

        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token", self._refresh_token)
        if not new_access:
            raise SkylightAuthError(f"OAuth refresh: no access_token in response: {data}")

        self._access_token = new_access
        self._refresh_token = new_refresh
        _LOGGER.debug("Skylight tokens refreshed")

        if self._token_update_cb is not None:
            try:
                await self._token_update_cb(
                    new_access, new_refresh, self._device_fingerprint
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Token persistence callback failed")

    # ── Endpoints ───────────────────────────────────────────────────────

    async def get_frames(self) -> list[dict]:
        data = await self._request("GET", "/api/frames")
        out = []
        for item in data.get("data", []):
            fid = item.get("id")
            name = item.get("attributes", {}).get("name")
            if fid:
                out.append({"id": str(fid), "name": name or f"Skylight Frame {fid}"})
        return out

    async def get_frame(self, frame_id: str) -> dict:
        return await self._request("GET", f"/api/frames/{frame_id}")

    async def patch_frame(self, frame_id: str, attributes: dict) -> dict:
        """PATCH frame attributes (brightness, sleep_mode_on, slideshow_speed, etc.)."""
        body = {"data": {"type": "frame", "id": frame_id, "attributes": attributes}}
        return await self._request("PATCH", f"/api/frames/{frame_id}", json_body=body)

    async def get_calendar_events(
        self, frame_id: str, date_min: str, date_max: str, timezone: str = "UTC"
    ) -> dict:
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/calendar_events",
            params={"date_min": date_min, "date_max": date_max, "timezone": timezone},
        )

    async def get_source_calendars(self, frame_id: str) -> dict:
        return await self._request("GET", f"/api/frames/{frame_id}/source_calendars")

    async def get_categories(self, frame_id: str, include_profiles: bool = True) -> dict:
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/categories",
            params={"include_profiles": "true" if include_profiles else None},
        )

    async def get_lists(self, frame_id: str) -> dict:
        return await self._request("GET", f"/api/frames/{frame_id}/lists")

    async def get_list_items(self, frame_id: str, list_id: str) -> dict:
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/lists/{list_id}",
            params={"include": "list_items"},
        )

    async def add_list_item(self, frame_id: str, list_id: str, label: str) -> dict:
        return await self._request(
            "POST",
            f"/api/frames/{frame_id}/lists/{list_id}/list_items",
            json_body={"label": label},
        )

    async def update_list_item(
        self, frame_id: str, list_id: str, item_id: str, attrs: dict
    ) -> dict:
        return await self._request(
            "PUT",
            f"/api/frames/{frame_id}/lists/{list_id}/list_items/{item_id}",
            json_body=attrs,
        )

    async def delete_list_item(self, frame_id: str, list_id: str, item_id: str) -> None:
        await self._request(
            "DELETE", f"/api/frames/{frame_id}/lists/{list_id}/list_items/{item_id}"
        )

    async def get_chores(self, frame_id: str, after: str, before: str) -> dict:
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/chores",
            params={"after": after, "before": before, "include_late": "true"},
        )

    async def complete_chore(self, frame_id: str, chore_id: str) -> dict:
        """Mark a chore complete (JSON:API PUT)."""
        body = {
            "data": {
                "type": "chore",
                "id": chore_id,
                "attributes": {"status": "completed"},
            }
        }
        return await self._request(
            "PUT", f"/api/frames/{frame_id}/chores/{chore_id}", json_body=body
        )

    async def update_chore_status(
        self, frame_id: str, chore_id: str, status: str
    ) -> dict:
        body = {
            "data": {"type": "chore", "id": chore_id, "attributes": {"status": status}}
        }
        return await self._request(
            "PUT", f"/api/frames/{frame_id}/chores/{chore_id}", json_body=body
        )

    async def get_meals(self, frame_id: str, date_min: str, date_max: str) -> dict:
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/meals/sittings",
            params={
                "date_min": date_min,
                "date_max": date_max,
                "include": "meal_category,meal_recipe",
            },
        )

    async def get_reward_points(self, frame_id: str) -> dict:
        return await self._request("GET", f"/api/frames/{frame_id}/reward_points")

    async def get_rewards(self, frame_id: str) -> dict:
        return await self._request("GET", f"/api/frames/{frame_id}/rewards")

    async def get_messages(self, frame_id: str, page_token: str = "__START__") -> dict:
        """Photo/message feed."""
        return await self._request(
            "GET",
            f"/api/frames/{frame_id}/messages",
            params={"page_token": page_token},
        )


async def exchange_refresh_token(
    session: aiohttp.ClientSession,
    refresh_token: str,
    device_fingerprint: str = "",
) -> dict:
    """One-shot refresh exchange used by the config flow to verify tokens."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "scope": "everything",
        "skylight_api_client_device_fingerprint": device_fingerprint,
        "skylight_api_client_device_platform": "web",
        "skylight_api_client_device_name": "home-assistant",
        "skylight_api_client_device_os_version": "10",
        "skylight_api_client_device_app_version": "unknown",
        "skylight_api_client_device_hardware": "3",
        "source": "web",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with session.post(
        OAUTH_URL,
        data=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise SkylightAuthError(f"Refresh exchange failed ({resp.status}): {text[:200]}")
        data = _json.loads(text)
    if not data.get("access_token"):
        raise SkylightAuthError(f"Refresh exchange: no access_token: {data}")
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
    }
