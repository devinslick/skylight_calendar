"""Todo platform: one HA Todo entity per Skylight list."""

from __future__ import annotations

import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SkylightAPI
from .const import DOMAIN
from .coordinator import SkylightListsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: SkylightListsCoordinator = data["lists_coordinator"]
    api: SkylightAPI = data["api"]
    frame_id: str = data["frame_id"]
    frame_name: str = data["frame_name"]

    entities: list[SkylightTodoList] = []
    for list_id, list_data in (coord.data or {}).items():
        entities.append(
            SkylightTodoList(coord, api, frame_id, frame_name, list_id, list_data["name"])
        )
    async_add_entities(entities)

    known: set[str] = {e.list_id for e in entities}

    def _handle_update() -> None:
        current = set((coord.data or {}).keys())
        new_ids = current - known
        if not new_ids:
            return
        new_entities = []
        for lid in new_ids:
            ldata = coord.data[lid]
            new_entities.append(
                SkylightTodoList(coord, api, frame_id, frame_name, lid, ldata["name"])
            )
            known.add(lid)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coord.async_add_listener(_handle_update))


class SkylightTodoList(CoordinatorEntity[SkylightListsCoordinator], TodoListEntity):
    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: SkylightListsCoordinator,
        api: SkylightAPI,
        frame_id: str,
        frame_name: str,
        list_id: str,
        list_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._frame_id = frame_id
        self.list_id = list_id
        self._attr_name = list_name
        self._attr_unique_id = f"skylight_{frame_id}_list_{list_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, frame_id)},
            name=frame_name,
            manufacturer="Skylight",
            model="Calendar Frame",
        )

    @property
    def todo_items(self) -> list[TodoItem] | None:
        list_data = (self.coordinator.data or {}).get(self.list_id)
        if list_data is None:
            return None
        items: list[TodoItem] = []
        for it in list_data["items"]:
            status = (
                TodoItemStatus.COMPLETED
                if it["status"] == "completed"
                else TodoItemStatus.NEEDS_ACTION
            )
            items.append(TodoItem(summary=it["name"], uid=it["id"], status=status))
        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self._api.add_list_item(self._frame_id, self.list_id, item.summary or "")
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        attrs: dict = {}
        if item.summary is not None:
            attrs["name"] = item.summary
        if item.status is not None:
            attrs["status"] = (
                "completed"
                if item.status == TodoItemStatus.COMPLETED
                else "pending"
            )
        if attrs and item.uid:
            await self._api.update_list_item(
                self._frame_id, self.list_id, item.uid, attrs
            )
            await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._api.delete_list_item(self._frame_id, self.list_id, uid)
        await self.coordinator.async_request_refresh()
