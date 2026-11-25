"""Versioned Home Assistant storage."""
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import Task


class TaskStorage:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, 1, DOMAIN)

    async def load(self) -> list[dict]:
        data = await self._store.async_load()
        return [] if data is None else data["tasks"]

    async def save(self, tasks: list[Task]) -> None:
        await self._store.async_save({"tasks": [task.serialize() for task in tasks]})
