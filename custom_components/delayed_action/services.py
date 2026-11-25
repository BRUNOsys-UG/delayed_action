"""Legacy service and event interface."""
from datetime import timedelta
from uuid import uuid4

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ATTR_DOMAINS, CONF_DOMAINS
from .models import Task
from .scheduler import Scheduler

SERVICES = ("execute", "cancel", "list", "get_config")
EXECUTE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required("action"): cv.string,
    vol.Exclusive("delay", "schedule"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Exclusive("datetime", "schedule"): cv.datetime,
    vol.Exclusive("data", "payload"): dict,
    vol.Exclusive("additional_data", "payload"): dict,
})
CANCEL_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("task_id"): cv.string,
})


def register(hass: HomeAssistant, scheduler: Scheduler, entry) -> None:
    async def execute(call: ServiceCall) -> None:
        data = call.data
        entity_id = data["entity_id"]
        action = data["action"]
        domain = entity_id.split(".", 1)[0]
        if hass.states.get(entity_id) is None:
            raise HomeAssistantError(f"Unknown entity: {entity_id}")
        if not hass.services.has_service(domain, action):
            raise HomeAssistantError(f"Unknown service: {domain}.{action}")
        now = dt_util.utcnow()
        if "delay" in data:
            due = now + timedelta(seconds=data["delay"])
        elif "datetime" in data:
            due = dt_util.as_utc(data["datetime"])
            if due < now:
                raise HomeAssistantError("Scheduled time is in the past")
        else:
            raise HomeAssistantError("Either delay or datetime is required")
        payload = dict(data.get("data", data.get("additional_data", {})))
        if "entity_id" in payload:
            raise HomeAssistantError("Additional data must not override entity_id")
        await scheduler.add(Task(str(uuid4()), entity_id, action, due, payload), call.context)

    async def cancel(call: ServiceCall) -> None:
        await scheduler.cancel(call.data["entity_id"], call.data.get("task_id"))

    async def list_actions(call: ServiceCall) -> None:
        hass.bus.async_fire(f"{DOMAIN}_list_actions_response",
                            {"actions": scheduler.list(call.data.get("entity_id"))})

    async def get_config(call: ServiceCall) -> None:
        hass.bus.async_fire(f"{DOMAIN}_get_config_response", {
            CONF_DOMAINS: entry.options.get(CONF_DOMAINS,
                entry.data.get(CONF_DOMAINS, ATTR_DOMAINS))
        })

    hass.services.async_register(DOMAIN, "execute", execute, schema=EXECUTE_SCHEMA)
    hass.services.async_register(DOMAIN, "cancel", cancel, schema=CANCEL_SCHEMA)
    async_register_admin_service(hass, DOMAIN, "list", list_actions,
                                 schema=vol.Schema({vol.Optional("entity_id"): cv.entity_id}))
    async_register_admin_service(hass, DOMAIN, "get_config", get_config, schema=vol.Schema({}))


def unregister(hass: HomeAssistant) -> None:
    for service in SERVICES:
        hass.services.async_remove(DOMAIN, service)
