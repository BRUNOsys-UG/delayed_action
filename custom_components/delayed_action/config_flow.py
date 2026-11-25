"""Configuration and options flows."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_DOMAINS, ATTR_DOMAINS


def schema(domains: list[str]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_DOMAINS, default=domains): cv.multi_select({
            domain: domain.replace("_", " ").title() for domain in ATTR_DOMAINS
        })
    })


class DelayedActionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Delayed Action", data=user_input)
        return self.async_show_form(step_id="user", data_schema=schema(ATTR_DOMAINS))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DelayedActionOptionsFlowHandler()


class DelayedActionOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        domains = self.config_entry.options.get(
            CONF_DOMAINS, self.config_entry.data.get(CONF_DOMAINS, ATTR_DOMAINS)
        )
        return self.async_show_form(step_id="init", data_schema=schema(domains))
