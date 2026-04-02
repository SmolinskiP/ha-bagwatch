"""Bagwatch integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_COINGECKO_API_KEY, PLATFORMS
from .coordinator import BagwatchCoordinator
from .provider import CoinGeckoClient, TwelveDataClient, YahooFinanceClient


async def _async_reload_updated_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry after settings or positions change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bagwatch from a config entry."""
    session = async_get_clientsession(hass)
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY, ""))
    coingecko_api_key = entry.options.get(
        CONF_COINGECKO_API_KEY,
        entry.data.get(CONF_COINGECKO_API_KEY, ""),
    )
    twelve_data_client = TwelveDataClient(session=session, api_key=api_key)
    coingecko_client = CoinGeckoClient(session=session, api_key=coingecko_api_key)
    yahoo_finance_client = YahooFinanceClient()
    coordinator = BagwatchCoordinator(
        hass=hass,
        entry=entry,
        twelve_data_client=twelve_data_client,
        coingecko_client=coingecko_client,
        yahoo_finance_client=yahoo_finance_client,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_updated_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
