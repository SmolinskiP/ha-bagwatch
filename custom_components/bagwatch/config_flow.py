"""Config flow for Bagwatch."""

from __future__ import annotations

from datetime import datetime
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
    DateSelector,
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
    CONF_BASE_CURRENCY,
    CONF_CURRENCY,
    CONF_FEES_TOTAL,
    CONF_NAME,
    CONF_PORTFOLIO_NAME,
    CONF_PROVIDER,
    CONF_PROVIDER_SYMBOL,
    CONF_QUANTITY,
    CONF_SCAN_INTERVAL,
    CONF_SYMBOL,
    CONF_TRADE_DATE,
    CONF_TRANSACTION_TYPE,
    CONF_UNIT_PRICE,
    DEFAULT_ASSET_TYPE,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_NAME,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRANSACTION_TYPE,
    DOMAIN,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_PROVIDERS,
    SUPPORTED_TRANSACTION_TYPES,
)
from .models import (
    PortfolioValidationError,
    TransactionConfig,
    group_transactions,
    parse_transactions_data,
)

SUBENTRY_TYPE_TRANSACTION = "transaction"
LEGACY_SUBENTRY_TYPE_POSITION = "position"


def _subentry_sort_key(subentry: Any) -> tuple[str, str]:
    """Return a version-safe sorting key for config subentries."""
    created_at = getattr(subentry, "created_at", None)
    modified_at = getattr(subentry, "modified_at", None)
    timestamp = created_at or modified_at
    if isinstance(timestamp, datetime):
        return (timestamp.isoformat(), getattr(subentry, "subentry_id", ""))
    return ("", getattr(subentry, "subentry_id", ""))


def _basic_schema(defaults: dict[str, Any]) -> vol.Schema:
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
    return vol.Schema(schema)


def _transaction_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the transaction subentry schema."""
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
            vol.Required(
                CONF_TRANSACTION_TYPE,
                default=defaults.get(CONF_TRANSACTION_TYPE, DEFAULT_TRANSACTION_TYPE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SUPPORTED_TRANSACTION_TYPES,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_QUANTITY, default=defaults.get(CONF_QUANTITY, "")): text_selector,
            vol.Required(CONF_UNIT_PRICE, default=defaults.get(CONF_UNIT_PRICE, "")): text_selector,
            vol.Required(CONF_CURRENCY, default=defaults.get(CONF_CURRENCY, "")): str,
            vol.Required(CONF_TRADE_DATE, default=defaults.get(CONF_TRADE_DATE, "")): DateSelector(),
            vol.Optional(
                CONF_FEES_TOTAL,
                default=defaults.get(CONF_FEES_TOTAL, ""),
            ): text_selector,
            vol.Optional(
                CONF_PROVIDER_SYMBOL,
                default=defaults.get(CONF_PROVIDER_SYMBOL, ""),
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


def _normalize_transaction_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a single transaction."""
    transaction = {
        CONF_SYMBOL: str(user_input.get(CONF_SYMBOL, "")).strip(),
        CONF_NAME: _clean_optional_text(user_input.get(CONF_NAME)),
        CONF_ASSET_TYPE: str(user_input.get(CONF_ASSET_TYPE, DEFAULT_ASSET_TYPE)).strip(),
        CONF_TRANSACTION_TYPE: str(
            user_input.get(CONF_TRANSACTION_TYPE, DEFAULT_TRANSACTION_TYPE)
        ).strip(),
        CONF_QUANTITY: _clean_required_number(user_input.get(CONF_QUANTITY), CONF_QUANTITY),
        CONF_UNIT_PRICE: _clean_required_number(user_input.get(CONF_UNIT_PRICE), CONF_UNIT_PRICE),
        CONF_CURRENCY: str(user_input.get(CONF_CURRENCY, "")).strip().upper(),
        CONF_TRADE_DATE: str(user_input.get(CONF_TRADE_DATE, "")).strip(),
        CONF_FEES_TOTAL: _clean_optional_number(user_input.get(CONF_FEES_TOTAL)),
        CONF_PROVIDER_SYMBOL: _clean_optional_text(user_input.get(CONF_PROVIDER_SYMBOL)),
    }

    transaction = {key: value for key, value in transaction.items() if value is not None}
    normalized_transaction = TransactionConfig.from_dict(transaction)
    return transaction | {
        CONF_ASSET_TYPE: normalized_transaction.asset_type or DEFAULT_ASSET_TYPE,
        CONF_TRANSACTION_TYPE: normalized_transaction.transaction_type,
        CONF_TRADE_DATE: normalized_transaction.trade_date.isoformat(),
        CONF_CURRENCY: normalized_transaction.currency,
    }


def _build_transaction_title(transaction: dict[str, Any]) -> str:
    """Return a compact subentry title."""
    tx_type = str(transaction[CONF_TRANSACTION_TYPE]).capitalize()
    return f"{tx_type} {transaction[CONF_SYMBOL]} {transaction[CONF_TRADE_DATE]}"


class BagwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bagwatch."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported subentry types."""
        return {SUBENTRY_TYPE_TRANSACTION: BagwatchTransactionSubentryFlow}

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


class BagwatchTransactionSubentryFlow(ConfigSubentryFlow):
    """Handle Bagwatch transaction subentries."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Create a new transaction."""
        return await self._async_handle_transaction_step("init", user_input)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Backward-compatible alias for creating a new transaction."""
        return await self.async_step_init(user_input)

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Reconfigure an existing transaction."""
        return await self._async_handle_transaction_step("reconfigure", user_input)

    async def _async_handle_transaction_step(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
    ):
        """Handle create and reconfigure steps for transactions."""
        errors: dict[str, str] = {}
        defaults = user_input or self._transaction_defaults(step_id)

        if user_input is not None:
            try:
                transaction = _normalize_transaction_input(user_input)
                self._validate_transaction_ledger(transaction, step_id)
            except PortfolioValidationError as err:
                if "legacy positions" in str(err).lower():
                    errors["base"] = "legacy_positions_present"
                else:
                    errors["base"] = "invalid_transaction"
            else:
                title = _build_transaction_title(transaction)
                if step_id == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        data=transaction,
                        title=title,
                    )
                return self.async_create_entry(
                    title=title,
                    data=transaction,
                )

        return self.async_show_form(
            step_id=step_id,
            data_schema=_transaction_schema(defaults),
            errors=errors,
        )

    def _transaction_defaults(self, step_id: str) -> dict[str, Any]:
        """Return defaults for the transaction form."""
        if step_id != "reconfigure":
            return {}
        return dict(self._get_reconfigure_subentry().data)

    def _validate_transaction_ledger(
        self,
        candidate_transaction: dict[str, Any],
        step_id: str,
    ) -> None:
        """Ensure the full transaction ledger remains valid."""
        entry = self._get_entry()
        if any(
            subentry.subentry_type == LEGACY_SUBENTRY_TYPE_POSITION
            for subentry in entry.subentries.values()
        ):
            raise PortfolioValidationError(
                "Delete existing legacy positions before adding transactions"
            )

        current_subentry_id = (
            self._get_reconfigure_subentry().subentry_id
            if step_id == "reconfigure"
            else None
        )
        records: list[dict[str, Any]] = []
        order_index = 0
        appended_candidate = False

        sorted_subentries = sorted(
            entry.subentries.values(),
            key=_subentry_sort_key,
        )
        for subentry in sorted_subentries:
            if subentry.subentry_type != SUBENTRY_TYPE_TRANSACTION:
                continue

            data = dict(subentry.data)
            if subentry.subentry_id == current_subentry_id:
                data = candidate_transaction
                appended_candidate = True

            records.append(data | {"_order_index": order_index})
            order_index += 1

        if not appended_candidate:
            records.append(candidate_transaction | {"_order_index": order_index})

        transactions = parse_transactions_data(records)
        group_transactions(transactions)
