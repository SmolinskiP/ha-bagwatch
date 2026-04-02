"""Button platform for Bagwatch."""

from __future__ import annotations

import inspect

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import BagwatchCoordinator
from .models import PositionSnapshot
from .sensor import PortfolioBaseEntity

LEGACY_SUBENTRY_TYPE_POSITION = "position"
SUBENTRY_TYPE_TRANSACTION = "transaction"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities for a config entry."""
    coordinator: BagwatchCoordinator = entry.runtime_data
    entities = [
        DeletePositionButton(coordinator, entry, asset.key)
        for asset in coordinator.get_configured_assets()
    ]

    async_add_entities(entities)


class DeletePositionButton(PortfolioBaseEntity, ButtonEntity):
    """Button that removes all transactions for one tracked asset."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_icon = "mdi:trash-can-outline"
    _attr_name = "Delete Position"

    def __init__(
        self,
        coordinator: BagwatchCoordinator,
        entry: ConfigEntry,
        asset_key: str,
    ) -> None:
        """Initialize the delete button."""
        super().__init__(coordinator, entry)
        self._asset_key = asset_key
        self._attr_unique_id = f"{entry.entry_id}_{asset_key}_delete_position"

    @property
    def _position(self) -> PositionSnapshot | None:
        """Return the current position snapshot."""
        if self.coordinator.data is None:
            return None

        for position in self.coordinator.data.positions:
            if position.asset.key == self._asset_key:
                return position
        return None

    @property
    def available(self) -> bool:
        """Return availability."""
        return super().available and self._is_configured

    @property
    def _is_configured(self) -> bool:
        """Return True when the asset still exists in the stored config."""
        return any(
            str(subentry.data.get("symbol", "")).strip().upper() == self._asset_key
            for subentry in self._entry.subentries.values()
            if subentry.subentry_type in (SUBENTRY_TYPE_TRANSACTION, LEGACY_SUBENTRY_TYPE_POSITION)
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for the position."""
        position = self._position
        display_name = position.asset.display_name if position else self._asset_key
        model = position.asset.asset_type if position else "Position"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._asset_key}")},
            name=display_name,
            manufacturer="Bagwatch",
            model=model,
            via_device=(DOMAIN, self._entry.entry_id),
        )

    async def async_press(self) -> None:
        """Delete all stored config subentries for this asset."""
        subentry_ids = [
            subentry.subentry_id
            for subentry in self._entry.subentries.values()
            if subentry.subentry_type in (SUBENTRY_TYPE_TRANSACTION, LEGACY_SUBENTRY_TYPE_POSITION)
            and str(subentry.data.get("symbol", "")).strip().upper() == self._asset_key
        ]

        for subentry_id in subentry_ids:
            result = self.hass.config_entries.async_remove_subentry(self._entry, subentry_id)
            if inspect.isawaitable(result):
                await result
