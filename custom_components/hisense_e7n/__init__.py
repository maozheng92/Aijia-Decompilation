"""Hisense E7N Pro local VIDAA MQTT integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .certs_util import resolve_cert_candidates
from .const import (
    CONF_AUTH_MODE,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CLIENT_UUID,
    CONF_POWER_ON_BUTTON,
    CONF_USE_SSL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DEFAULT_AUTH_MODE,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import HisenseTvCoordinator
from .credentials import stable_client_uuid
from .power import normalize_power_on_entity
from .tv_client import HisenseTvClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one E7N Pro from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]
    port = int(data.get(CONF_PORT, DEFAULT_PORT))
    uuid = stable_client_uuid(data.get(CONF_CLIENT_UUID), data.get(CONF_MAC))
    if uuid != data.get(CONF_CLIENT_UUID):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CLIENT_UUID: uuid}
        )
    certfile = data.get(CONF_CLIENT_CERT)
    keyfile = data.get(CONF_CLIENT_KEY)
    cert_dir = Path(hass.config.config_dir) / "hisense_e7n" / entry.entry_id
    search_roots = [Path(hass.config.config_dir), Path(__file__).resolve().parents[2]]
    cert_pairs = await hass.async_add_executor_job(
        resolve_cert_candidates,
        cert_dir,
        certfile,
        keyfile,
        search_roots,
    )
    if cert_pairs:
        certfile, keyfile = cert_pairs[0]
    use_ssl = data.get(CONF_USE_SSL)
    if isinstance(use_ssl, str):
        use_ssl = use_ssl.lower() in {"1", "true", "yes"}

    power_on_button = normalize_power_on_entity(data.get(CONF_POWER_ON_BUTTON))
    client = HisenseTvClient(
        host,
        port=port,
        uuid=uuid,
        tv_mac=data.get(CONF_MAC),
        auth_mode=data.get(CONF_AUTH_MODE, DEFAULT_AUTH_MODE),
        certfile=certfile,
        keyfile=keyfile,
        cert_pairs=cert_pairs,
        use_ssl=use_ssl,
        loop=hass.loop,
    )

    try:
        await client.async_connect()
    except ConnectionError as err:
        # Broker is down when the TV is fully off; still load if we can press
        # a power-on button or fall back to Wake-on-LAN.
        if not power_on_button and not data.get(CONF_MAC):
            raise ConfigEntryNotReady(f"Cannot reach Hisense TV at {host}:{port}") from err
        _LOGGER.warning(
            "TV at %s:%s is offline; turn-on will call %s (%s)",
            host,
            port,
            power_on_button or data.get(CONF_MAC),
            err,
        )

    coordinator = HisenseTvCoordinator(
        hass,
        client,
        data.get(CONF_NAME, host),
        power_on_button=power_on_button,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    stored = hass.data[DOMAIN].pop(entry.entry_id, None)
    if stored and DATA_CLIENT in stored:
        await stored[DATA_CLIENT].async_disconnect()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
