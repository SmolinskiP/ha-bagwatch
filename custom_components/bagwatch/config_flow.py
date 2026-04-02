"""Config flow for Bagwatch."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
)
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
    CONF_ASSET_TYPE,
    CONF_AVERAGE_BUY_PRICE,
    CONF_BASE_CURRENCY,
    CONF_BUY_CURRENCY,
    CONF_COST_BASIS,
    CONF_COST_BASIS_BASE,
    CONF_COST_CURRENCY,
    CONF_COUNTRY,
    CONF_EXCHANGE,
    CONF_FEES_TOTAL,
    CONF_NAME,
    CONF_PORTFOLIO_NAME,
    CONF_PROVIDER,
    CONF_PROVIDER_SYMBOL,
    CONF_QUANTITY,
    CONF_SCAN_INTERVAL,
    CONF_SYMBOL,
    DEFAULT_ASSET_TYPE,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_NAME,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_PROVIDERS,
)
from .models import HoldingConfig, PortfolioValidationError

SUBENTRY_TYPE_POSITION = "position"
CONF_EDIT_POSITIONS = "edit_positions"


def _basic_schema(defaults: dict[str, Any], *, include_edit_positions: bool = False) -> vol.Schema:
    """Build the main integration config schema."""
    schema: dict[Any, Any] = {
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
    }
    if include_edit_positions:
        schema[vol.Required(CONF_EDIT_POSITIONS, default=False)] = bool
    return vol.Schema(schema)



def _position_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the position subentry schema."""
    defaults = defaults or {}
    text_selector = TextSelector(TextSelectorConfig())
    return vol.Schema(
        {
            vol.Required(CONF_SYMBOL, default=defaults.get(CONF_SYMBOL, "")): str,
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
            vol.Required(
                CONF_ASSET_TYPE,
                default=defaults.get(CONF_ASSET_TYPE, DEFAULT_ASSET_TYPE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SUPPORTED_ASSET_TYPES,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_QUANTITY, default=defaults.get(CONF_QUANTITY, "")): text_selector,
            vol.Optional(
                CONF_AVERAGE_BUY_PRICE,
                default=defaults.get(CONF_AVERAGE_BUY_PRICE, ""),
            ): text_selector,
            vol.Optional(
                CONF_BUY_CURRENCY,
                default=defaults.get(CONF_BUY_CURRENCY, ""),
            ): str,
            vol.Optional(
                CONF_COST_BASIS,
                default=defaults.get(CONF_COST_BASIS, ""),
            ): text_selector,
            vol.Optional(
                CONF_COST_CURRENCY,
                default=defaults.get(CONF_COST_CURRENCY, ""),
            ): str,
            vol.Optional(
                CONF_COST_BASIS_BASE,
                default=defaults.get(CONF_COST_BASIS_BASE, ""),
            ): text_selector,
            vol.Optional(
                CONF_FEES_TOTAL,
                default=defaults.get(CONF_FEES_TOTAL, ""),
            ): text_selector,
            vol.Optional(
                CONF_PROVIDER_SYMBOL,
                default=defaults.get(CONF_PROVIDER_SYMBOL, ""),
            ): str,
            vol.Optional(
                CONF_EXCHANGE,
                default=defaults.get(CONF_EXCHANGE, ""),
            ): str,
            vol.Optional(
                CONF_COUNTRY,
                default=defaults.get(CONF_COUNTRY, ""),
            ): str,
        }
    )



def _clean_optional_text(value: Any) -> str | None:
    """Normalize optional text values."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None



def _clean_required_number(value: Any, field_name: str) -> str:
    """Normalize a required numeric field to a canonical string."""
    cleaned = _clean_optional_number(value)
    if cleaned is None:
        raise PortfolioValidationError(f"'{field_name}' is required")
    return cleaned



def _clean_optional_number(value: Any) -> str | None:
    """Normalize an optional numeric field to a canonical string."""
    if value in (None, ""):
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return format(Decimal(text), "f")
    except (InvalidOperation, TypeError) as err:
        raise PortfolioValidationError(f"Invalid numeric value: {value!r}") from err



def _normalize_basic_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate the main integration settings."""
    api_key = str(user_input[CONF_API_KEY]).strip()
    if not api_key:
        raise PortfolioValidationError("API key is required")

    provider = str(user_input[CONF_PROVIDER]).strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise PortfolioValidationError(f"Unsupported provider: {provider}")

    portfolio_name = str(user_input[CONF_PORTFOLIO_NAME]).strip()
    if not portfolio_name:
        raise PortfolioValidationError("Portfolio name is required")

    return {
        CONF_PORTFOLIO_NAME: portfolio_name,
        CONF_PROVIDER: provider,
        CONF_API_KEY: api_key,
        CONF_BASE_CURRENCY: str(user_input[CONF_BASE_CURRENCY]).strip().upper(),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
    }



def _normalize_position_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a single position."""
    position = {
        CONF_SYMBOL: str(user_input.get(CONF_SYMBOL, "")).strip(),
        CONF_NAME: _clean_optional_text(user_input.get(CONF_NAME)),
        CONF_ASSET_TYPE: str(user_input.get(CONF_ASSET_TYPE, DEFAULT_ASSET_TYPE)).strip(),
        CONF_QUANTITY: _clean_required_number(user_input.get(CONF_QUANTITY), CONF_QUANTITY),
        CONF_AVERAGE_BUY_PRICE: _clean_optional_number(user_input.get(CONF_AVERAGE_BUY_PRICE)),
        CONF_BUY_CURRENCY: _clean_optional_text(user_input.get(CONF_BUY_CURRENCY)),
        CONF_COST_BASIS: _clean_optional_number(user_input.get(CONF_COST_BASIS)),
        CONF_COST_CURRENCY: _clean_optional_text(user_input.get(CONF_COST_CURRENCY)),
        CONF_COST_BASIS_BASE: _clean_optional_number(user_input.get(CONF_COST_BASIS_BASE)),
        CONF_FEES_TOTAL: _clean_optional_number(user_input.get(CONF_FEES_TOTAL)),
        CONF_PROVIDER_SYMBOL: _clean_optional_text(user_input.get(CONF_PROVIDER_SYMBOL)),
        CONF_EXCHANGE: _clean_optional_text(user_input.get(CONF_EXCHANGE)),
        CONF_COUNTRY: _clean_optional_text(user_input.get(CONF_COUNTRY)),
    }

    if position[CONF_AVERAGE_BUY_PRICE] is not None and position[CONF_BUY_CURRENCY] is None:
        raise PortfolioValidationError("Purchase currency is required when average buy price is set")

    if position[CONF_COST_BASIS] is not None and position[CONF_COST_CURRENCY] is None:
        raise PortfolioValidationError("Cost currency is required when total cost basis is set")

    position = {key: value for key, value in position.items() if value is not None}
    holding = HoldingConfig.from_dict(position)
    return position | {CONF_ASSET_TYPE: holding.asset_type}


class BagwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bagwatch."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported subentry types."""
        return {SUBENTRY_TYPE_POSITION: BagwatchPositionSubentryFlow}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_basic_input(user_input)
            except PortfolioValidationError:
                errors["base"] = "invalid_configuration"
            else:
                await self.async_set_unique_id(normalized[CONF_PORTFOLIO_NAME].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=normalized[CONF_PORTFOLIO_NAME],
                    data=normalized,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_basic_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return the options flow handler."""
        return BagwatchOptionsFlow(config_entry)


class BagwatchOptionsFlow(OptionsFlow):
    """Handle Bagwatch options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_basic_input(user_input)
            except PortfolioValidationError:
                errors["base"] = "invalid_configuration"
            else:
                return self.async_create_entry(title="", data=normalized)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_basic_schema(defaults),
            errors=errors,
        )


class BagwatchPositionSubentryFlow(ConfigSubentryFlow):
    """Handle Bagwatch position subentries."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Create a new position."""
        return await self._async_handle_position_step("init", user_input)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Backward-compatible alias for creating a new position."""
        return await self.async_step_init(user_input)

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Reconfigure an existing position."""
        return await self._async_handle_position_step("reconfigure", user_input)

    async def _async_handle_position_step(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
    ):
        """Handle create and reconfigure steps for positions."""
        errors: dict[str, str] = {}
        defaults = user_input or self._position_defaults(step_id)

        if user_input is not None:
            try:
                position = _normalize_position_input(user_input)
                self._validate_position_uniqueness(position[CONF_SYMBOL], step_id)
            except PortfolioValidationError:
                errors["base"] = "invalid_position"
            else:
                title = position.get(CONF_NAME) or position[CONF_SYMBOL]
                unique_id = position[CONF_SYMBOL].upper()
                if step_id == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        data=position,
                        title=title,
                        unique_id=unique_id,
                    )
                return self.async_create_entry(
                    title=title,
                    data=position,
                    unique_id=unique_id,
                )

        return self.async_show_form(
            step_id=step_id,
            data_schema=_position_schema(defaults),
            errors=errors,
        )

    def _position_defaults(self, step_id: str) -> dict[str, Any]:
        """Return defaults for the position form."""
        if step_id != "reconfigure":
            return {}
        return dict(self._get_reconfigure_subentry().data)

    def _validate_position_uniqueness(self, symbol: str, step_id: str) -> None:
        """Ensure the symbol is unique within this config entry."""
        symbol_key = symbol.upper()
        entry = self._get_entry()
        current_subentry_id = (
            self._get_reconfigure_subentry().subentry_id
            if step_id == "reconfigure"
            else None
        )
        for subentry in entry.subentries.values():
            if subentry.subentry_id == current_subentry_id:
                continue
            if subentry.unique_id == symbol_key:
                raise PortfolioValidationError(f"Position '{symbol}' already exists")



