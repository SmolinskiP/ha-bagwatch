"""Sensor platform for Bagwatch."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AS_OF,
    ATTR_BASE_CURRENCY,
    ATTR_COST_CURRENCY,
    ATTR_COST_TO_BASE_RATE,
    ATTR_DATA_SOURCE,
    ATTR_IS_FX_ESTIMATE,
    ATTR_POSITION_COUNT,
    ATTR_PRICE_TO_BASE_RATE,
    ATTR_QUOTE_CURRENCY,
    DOMAIN,
)
from .coordinator import BagwatchCoordinator
from .models import PositionSnapshot


@dataclass(slots=True, frozen=True)
class PortfolioMetric:
    """Definition of a portfolio-wide metric sensor."""

    key: str
    name: str
    icon: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None


@dataclass(slots=True, frozen=True)
class PositionMetric:
    """Definition of a per-position metric sensor."""

    key: str
    name: str
    icon: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    monetary_unit: str | None = None


PORTFOLIO_METRICS: tuple[PortfolioMetric, ...] = (
    PortfolioMetric(
        key="market_value",
        name="Current Value",
        icon="mdi:wallet",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PortfolioMetric(
        key="cost_basis",
        name="Cost Basis",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PortfolioMetric(
        key="unrealized_gain",
        name="Unrealized Gain",
        icon="mdi:finance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PortfolioMetric(
        key="unrealized_gain_pct",
        name="Unrealized Gain Percentage",
        icon="mdi:percent",
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
    ),
    PortfolioMetric(
        key="positions_count",
        name="Positions Count",
        icon="mdi:format-list-bulleted",
    ),
)

POSITION_METRICS: tuple[PositionMetric, ...] = (
    PositionMetric(
        key="price",
        name="Current Price",
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        monetary_unit="quote",
    ),
    PositionMetric(
        key="quantity",
        name="Quantity",
        icon="mdi:numeric",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PositionMetric(
        key="market_value",
        name="Current Value",
        icon="mdi:chart-line",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        monetary_unit="base",
    ),
    PositionMetric(
        key="cost_basis",
        name="Cost Basis",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        monetary_unit="base",
    ),
    PositionMetric(
        key="unrealized_gain",
        name="Unrealized Gain",
        icon="mdi:trending-up",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        monetary_unit="base",
    ),
    PositionMetric(
        key="unrealized_gain_pct",
        name="Unrealized Gain Percentage",
        icon="mdi:percent",
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for a config entry."""
    coordinator: BagwatchCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        PortfolioSensor(coordinator, entry, metric) for metric in PORTFOLIO_METRICS
    ]

    if coordinator.data is not None:
        for position in coordinator.data.positions:
            for metric in POSITION_METRICS:
                entities.append(
                    PositionSensor(
                        coordinator,
                        entry,
                        position.holding.key,
                        metric,
                    )
                )

    async_add_entities(entities)


class PortfolioBaseEntity(CoordinatorEntity[BagwatchCoordinator], SensorEntity):
    """Base entity for bagwatch sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BagwatchCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for the portfolio."""
        name = self.coordinator.data.name if self.coordinator.data else self._entry.title
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=name,
            manufacturer="Bagwatch",
            model="Portfolio",
        )

    @staticmethod
    def _round(value: Decimal | None, digits: int = 4) -> float | None:
        """Round Decimal values for Home Assistant state output."""
        if value is None:
            return None
        return round(float(value), digits)


class PortfolioSensor(PortfolioBaseEntity):
    """A portfolio-wide sensor."""

    def __init__(
        self,
        coordinator: BagwatchCoordinator,
        entry: ConfigEntry,
        metric: PortfolioMetric,
    ) -> None:
        """Initialize the portfolio sensor."""
        super().__init__(coordinator, entry)
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_portfolio_{metric.key}"
        self._attr_name = metric.name
        self._attr_icon = metric.icon

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit for the sensor."""
        if self._metric.device_class == SensorDeviceClass.MONETARY:
            return self.coordinator.data.base_currency if self.coordinator.data else None
        return self._metric.unit

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class."""
        return self._metric.device_class

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class."""
        return self._metric.state_class

    @property
    def native_value(self) -> float | int | None:
        """Return the current sensor state."""
        snapshot = self.coordinator.data
        if snapshot is None:
            return None

        if self._metric.key == "market_value":
            return self._round(snapshot.market_value_base)
        if self._metric.key == "cost_basis":
            return self._round(snapshot.cost_basis_base)
        if self._metric.key == "unrealized_gain":
            return self._round(snapshot.unrealized_gain_base)
        if self._metric.key == "unrealized_gain_pct":
            return self._round(snapshot.unrealized_gain_pct, 2)
        if self._metric.key == "positions_count":
            return len(snapshot.positions)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        snapshot = self.coordinator.data
        if snapshot is None:
            return {}

        return {
            ATTR_BASE_CURRENCY: snapshot.base_currency,
            ATTR_POSITION_COUNT: len(snapshot.positions),
            ATTR_AS_OF: snapshot.updated_at.isoformat(),
        }


class PositionSensor(PortfolioBaseEntity):
    """A sensor for a single portfolio position."""

    def __init__(
        self,
        coordinator: BagwatchCoordinator,
        entry: ConfigEntry,
        holding_key: str,
        metric: PositionMetric,
    ) -> None:
        """Initialize the position sensor."""
        super().__init__(coordinator, entry)
        self._holding_key = holding_key
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_{holding_key}_{metric.key}"
        self._attr_icon = metric.icon

    @property
    def _position(self) -> PositionSnapshot | None:
        """Return the current position snapshot."""
        if self.coordinator.data is None:
            return None

        for position in self.coordinator.data.positions:
            if position.holding.key == self._holding_key:
                return position
        return None

    @property
    def available(self) -> bool:
        """Return availability."""
        return super().available and self._position is not None

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return self._metric.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for the position."""
        position = self._position
        display_name = position.holding.display_name if position else self._holding_key
        model = position.holding.asset_type if position else "Position"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._holding_key}")},
            name=display_name,
            manufacturer="Bagwatch",
            model=model,
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit for the sensor."""
        position = self._position
        if position is None:
            return self._metric.unit

        if self._metric.monetary_unit == "base":
            return self.coordinator.data.base_currency if self.coordinator.data else None
        if self._metric.monetary_unit == "quote":
            return position.quote.currency
        return self._metric.unit

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class."""
        return self._metric.device_class

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class."""
        return self._metric.state_class

    @property
    def native_value(self) -> float | None:
        """Return the current sensor state."""
        position = self._position
        if position is None:
            return None

        if self._metric.key == "price":
            return self._round(position.quote.price, 6)
        if self._metric.key == "quantity":
            return self._round(position.holding.quantity, 8)
        if self._metric.key == "market_value":
            return self._round(position.market_value_base)
        if self._metric.key == "cost_basis":
            return self._round(position.cost_basis_base)
        if self._metric.key == "unrealized_gain":
            return self._round(position.unrealized_gain_base)
        if self._metric.key == "unrealized_gain_pct":
            return self._round(position.unrealized_gain_pct, 2)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        position = self._position
        if position is None:
            return {}

        return {
            ATTR_DATA_SOURCE: "twelve_data",
            ATTR_BASE_CURRENCY: self.coordinator.data.base_currency if self.coordinator.data else None,
            ATTR_QUOTE_CURRENCY: position.quote.currency,
            ATTR_COST_CURRENCY: position.holding.cost_currency
            or position.holding.buy_currency
            or position.quote.currency,
            ATTR_PRICE_TO_BASE_RATE: self._round(position.price_to_base_rate, 8),
            ATTR_COST_TO_BASE_RATE: self._round(position.cost_to_base_rate, 8),
            ATTR_IS_FX_ESTIMATE: position.is_fx_estimate,
            ATTR_AS_OF: position.quote.as_of,
            "symbol": position.holding.symbol,
            "provider_symbol": position.quote.symbol,
            "exchange": position.quote.exchange,
            "asset_type": position.holding.asset_type,
        }



