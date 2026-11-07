"""Shared entity helpers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
except ImportError:  # pragma: no cover - HA < 2022.8
    CONNECTION_BLUETOOTH = "bluetooth"

from .const import CONF_BLE_ADDRESS, CONF_CLIENT_UUID, DEFAULT_NAME, DOMAIN
from .coordinator import HisenseTvCoordinator


class HisenseTvEntity(CoordinatorEntity[HisenseTvCoordinator]):
    """Base entity bound to one E7N Pro."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HisenseTvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        uuid = entry.data.get(CONF_CLIENT_UUID, entry.entry_id)
        host = entry.data.get(CONF_HOST, "")
        mac = (entry.data.get(CONF_MAC) or entry.options.get(CONF_MAC) or "").strip()
        ble = (entry.data.get(CONF_BLE_ADDRESS) or entry.options.get(CONF_BLE_ADDRESS) or "").strip()
        connections = {(CONNECTION_NETWORK_MAC, mac.lower())} if mac else set()
        if ble:
            connections.add((CONNECTION_BLUETOOTH, ble.upper()))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uuid or host)},
            connections=connections,
            manufacturer="Hisense",
            model="E7N Pro",
            name=entry.data.get(CONF_NAME) or DEFAULT_NAME,
        )

    @property
    def available(self) -> bool:
        if self.coordinator.client.state.available:
            return True
        return self.coordinator.can_power_on
