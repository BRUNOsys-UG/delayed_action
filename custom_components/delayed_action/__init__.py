"""Delayed Action integration lifecycle."""
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, ATTR_DOMAINS, CONF_DOMAINS
from .scheduler import Scheduler
from .services import register, unregister

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Optional(CONF_DOMAINS, default=ATTR_DOMAINS): vol.All(cv.ensure_list, [cv.string])
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if DOMAIN in hass.data:
        return False
    scheduler = Scheduler(hass)
    await scheduler.start()
    hass.data[DOMAIN] = scheduler
    register(hass, scheduler, entry)

    async def options_updated(hass: HomeAssistant, updated: ConfigEntry) -> None:
        hass.bus.async_fire(f"{DOMAIN}_get_config_response", {
            CONF_DOMAINS: updated.options.get(CONF_DOMAINS,
                updated.data.get(CONF_DOMAINS, ATTR_DOMAINS))
        })

    entry.async_on_unload(entry.add_update_listener(options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    scheduler = hass.data[DOMAIN]
    await scheduler.stop()
    unregister(hass)
    hass.data.pop(DOMAIN)
    return True
