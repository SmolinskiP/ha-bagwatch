"""Config flow for Bagwatch."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_API_KEY,
    CONF_BASE_CURRENCY,
    CONF_PORTFOLIO,
    CONF_PORTFOLIO_NAME,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_NAME,
    DEFAULT_PORTFOLIO_TEXT,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SUPPORTED_PROVIDERS,
)
from .models import PortfolioValidationError, parse_holdings_text


def _build_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the UI schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_PORTFOLIO_NAME,
                default=defaults.get(CONF_PORTFOLIO_NAME, DEFAULT_PORTFOLIO_NAME),
            ): str,
            vol.Required(
                CONF_PROVIDER,
                default=defaults.get(CONF_PROVIDER, DEFAULT_PROVIDER),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SUPPORTED_PROVIDERS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_API_KEY,
                default=defaults.get(CONF_API_KEY, ""),
            ): str,
            vol.Required(
                CONF_BASE_CURRENCY,
                default=defaults.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY),
            ): str,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=60,
                    max=86400,
                    step=60,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Required(
                CONF_PORTFOLIO,
                default=defaults.get(CONF_PORTFOLIO, DEFAULT_PORTFOLIO_TEXT),
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
    )


def _normalize_and_validate(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate user-provided settings."""
    api_key = str(user_input[CONF_API_KEY]).strip()
    if not api_key:
        raise PortfolioValidationError("API key is required")

    provider = str(user_input[CONF_PROVIDER]).strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise PortfolioValidationError(f"Unsupported provider: {provider}")

    portfolio_text = str(user_input[CONF_PORTFOLIO]).strip()
    parse_holdings_text(portfolio_text)

    return {
        CONF_PORTFOLIO_NAME: str(user_input[CONF_PORTFOLIO_NAME]).strip(),
        CONF_PROVIDER: provider,
        CONF_API_KEY: api_key,
        CONF_BASE_CURRENCY: str(user_input[CONF_BASE_CURRENCY]).strip().upper(),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
        CONF_PORTFOLIO: portfolio_text,
    }


class BagwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bagwatch."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_and_validate(user_input)
            except PortfolioValidationError:
                errors["base"] = "invalid_configuration"
            else:
                await self.async_set_unique_id(
                    normalized[CONF_PORTFOLIO_NAME].strip().lower()
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=normalized[CONF_PORTFOLIO_NAME],
                    data=normalized,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return BagwatchOptionsFlow(config_entry)


class BagwatchOptionsFlow(OptionsFlowWithReload):
    """Handle Bagwatch options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_and_validate(user_input)
            except PortfolioValidationError:
                errors["base"] = "invalid_configuration"
            else:
                return self.async_create_entry(title="", data=normalized)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults),
            errors=errors,
        )


