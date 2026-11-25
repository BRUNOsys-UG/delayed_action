"""Persistent one-shot scheduler."""
import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .models import Task
from .storage import TaskStorage

_LOGGER = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.storage = TaskStorage(hass)
        self.tasks: dict[str, Task] = {}
        self.timers: dict[str, Callable[[], None]] = {}
        self.contexts: dict[str, Context] = {}
        self.lock = asyncio.Lock()
        self.active = False

    async def start(self) -> None:
        async with self.lock:
            raw_tasks = await self.storage.load()
            for raw in raw_tasks:
                try:
                    task = Task.deserialize(raw)
                    if task.due <= dt_util.utcnow():
                        _LOGGER.info("Discarding expired task %s", task.task_id)
                        continue
                    self.tasks[task.task_id] = task
                except (ValueError, TypeError, KeyError, AttributeError):
                    _LOGGER.warning("Discarding invalid stored task", exc_info=True)
            await self.storage.save(list(self.tasks.values()))
            self.active = True
            for task in self.tasks.values():
                self._arm(task)

    @callback
    def _arm(self, task: Task) -> None:
        @callback
        def due(_now: Any) -> None:
            self.hass.async_create_task(self._execute(task.task_id))
        self.timers[task.task_id] = async_track_point_in_utc_time(
            self.hass, due, task.due
        )

    async def add(self, task: Task, context: Context) -> None:
        async with self.lock:
            if not self.active:
                raise HomeAssistantError("Delayed Action is not active")
            await self.storage.save([*self.tasks.values(), task])
            self.tasks[task.task_id] = task
            self.contexts[task.task_id] = context
            self._arm(task)

    async def cancel(self, entity_id: str, task_id: str | None) -> None:
        async with self.lock:
            if not self.active:
                raise HomeAssistantError("Delayed Action is not active")
            ids = {key for key, task in self.tasks.items()
                   if task.entity_id == entity_id and (task_id is None or key == task_id)}
            if not ids:
                raise HomeAssistantError("No matching scheduled action")
            await self.storage.save([task for key, task in self.tasks.items() if key not in ids])
            for key in ids:
                self.timers.pop(key)()
                self.tasks.pop(key)
                self.contexts.pop(key, None)

    async def _execute(self, task_id: str) -> None:
        async with self.lock:
            task = self.tasks.get(task_id)
            if not self.active or task is None:
                return
            self.timers.pop(task_id, None)
            try:
                # Consume durably before dispatch: never replay a possibly executed action.
                await self.storage.save([item for key, item in self.tasks.items()
                                         if key != task_id])
            except Exception:
                _LOGGER.exception("Cannot persist removal of task %s; action suppressed", task_id)
                self.tasks.pop(task_id, None)
                self.contexts.pop(task_id, None)
                return
            self.tasks.pop(task_id)
            context = self.contexts.pop(task_id, None)
        try:
            domain = task.entity_id.split(".", 1)[0]
            if self.hass.states.get(task.entity_id) is None:
                raise HomeAssistantError(f"Unknown entity: {task.entity_id}")
            await self.hass.services.async_call(
                domain, task.action, {**task.data, "entity_id": task.entity_id},
                blocking=True, context=context,
            )
        except Exception:
            _LOGGER.exception("Scheduled action %s failed", task_id)
        else:
            _LOGGER.info("Executed scheduled action %s", task_id)

    @callback
    def list(self, entity_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for task in self.tasks.values():
            if entity_id is not None and task.entity_id != entity_id:
                continue
            result.setdefault(task.entity_id, {})[task.task_id] = {
                "action": task.action, "task_id": task.task_id,
                "due": task.due.isoformat(),
            }
        return result

    async def stop(self) -> None:
        async with self.lock:
            self.active = False
            for cancel in self.timers.values():
                cancel()
            self.timers.clear()
            self.tasks.clear()
            self.contexts.clear()
