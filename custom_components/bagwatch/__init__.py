"""Bagwatch integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, PLATFORMS
from .coordinator import BagwatchCoordinator
from .provider import TwelveDataClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bagwatch from a config entry."""
    session = async_get_clientsession(hass)
    api_key = entry.options.get(CONF_API_KEY, entry.data[CONF_API_KEY])
    client = TwelveDataClient(session=session, api_key=api_key)
    coordinator = BagwatchCoordinator(hass=hass, entry=entry, client=client)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


