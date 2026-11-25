"""Scheduler regression tests."""
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.delayed_action.models import Task
from custom_components.delayed_action.scheduler import Scheduler


def make_task(offset=60):
    return Task("id", "switch.test", "turn_off",
                dt_util.utcnow() + timedelta(seconds=offset), {})


@pytest.fixture
def scheduler():
    hass = Mock()
    hass.services.async_call = AsyncMock()
    scheduler = Scheduler(hass)
    scheduler.storage = AsyncMock()
    scheduler.storage.load.return_value = []
    return scheduler


@pytest.mark.asyncio
async def test_restore_future_only(scheduler):
    future = make_task()
    expired = Task("expired", future.entity_id, future.action,
                   dt_util.utcnow() - timedelta(seconds=1), {})
    scheduler.storage.load.return_value = [future.serialize(), expired.serialize()]
    with patch("custom_components.delayed_action.scheduler.async_track_point_in_utc_time") as arm:
        await scheduler.start()
        assert list(scheduler.tasks) == ["id"]
        scheduler.storage.save.assert_awaited_once_with([future])
        arm.assert_called_once()
        await scheduler.stop()
        arm.return_value.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_prevents_queued_callback(scheduler):
    task = make_task()
    with patch("custom_components.delayed_action.scheduler.async_track_point_in_utc_time"):
        await scheduler.start()
        await scheduler.add(task, Mock())
        await scheduler.cancel(task.entity_id, task.task_id)
        await scheduler._execute(task.task_id)
        scheduler.hass.services.async_call.assert_not_awaited()
        assert scheduler.list() == {}
        scheduler.storage.save.assert_awaited_with([])


@pytest.mark.asyncio
async def test_failure_is_consumed(scheduler):
    task = make_task()
    scheduler.hass.services.async_call.side_effect = RuntimeError("failure")
    with patch("custom_components.delayed_action.scheduler.async_track_point_in_utc_time"):
        await scheduler.start()
        await scheduler.add(task, Mock())
        await scheduler._execute(task.task_id)
        await scheduler._execute(task.task_id)
        scheduler.hass.services.async_call.assert_awaited_once()
        assert scheduler.list() == {}
        scheduler.storage.save.assert_awaited_with([])


@pytest.mark.asyncio
async def test_storage_failure_suppresses_dispatch(scheduler):
    with patch("custom_components.delayed_action.scheduler.async_track_point_in_utc_time"):
        await scheduler.start()
        await scheduler.add(make_task(), Mock())
        scheduler.storage.save.side_effect = OSError("disk failure")
        await scheduler._execute("id")
        scheduler.hass.services.async_call.assert_not_awaited()


def test_round_trip():
    task = make_task()
    assert Task.deserialize(task.serialize()) == task
