"""Constants for the Hisense E7N Pro integration."""

from __future__ import annotations

DOMAIN = "hisense_e7n"
DEFAULT_NAME = "Hisense E7N Pro"
DEFAULT_PORT = 36669
DEFAULT_AUTH_MODE = "auto"

CONF_AUTH_MODE = "auth_mode"
CONF_CLIENT_UUID = "client_uuid"
CONF_CLIENT_CERT = "client_cert"
CONF_CLIENT_KEY = "client_key"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_CONTROL_USERNAME = "control_username"
CONF_POWER_ON_BUTTON = "power_on_button"
CONF_POWER_ON_MODE = "power_on_mode"
CONF_POWER_ON_REMOTE = "power_on_remote"
CONF_POWER_ON_COMMAND = "power_on_command"
CONF_POWER_ON_DEVICE = "power_on_device"
POWER_ON_MODE_BUTTON = "button"
POWER_ON_MODE_REMOTE = "remote"
POWER_ON_MODE_WOL = "wol"
DEFAULT_POWER_ON_COMMAND = "power"
CONF_USE_SSL = "use_ssl"
CONF_BLE_ADDRESS = "ble_address"
CONF_CUSTOM_SOURCES = "custom_sources"
CONF_CUSTOM_SOURCES_TEXT = "custom_sources_text"
CONF_SOURCE_KEY_DELAY = "source_key_delay"
DEFAULT_SOURCE_KEY_DELAY = 0.5
CONF_CUSTOM_SOURCE_NAME = "custom_source_name"
CONF_SEQUENCE_BUTTON = "sequence_button"
CONF_SEQUENCE_ACTION = "sequence_action"
CONF_MANAGE_ACTION = "manage_action"
CONF_MANAGE_SOURCE = "manage_source"
SEQUENCE_ACTION_ADD = "add"
SEQUENCE_ACTION_UNDO = "undo"
SEQUENCE_ACTION_CLEAR = "clear"
SEQUENCE_ACTION_DONE = "done"
MANAGE_ACTION_ADD = "add"
MANAGE_ACTION_EDIT = "edit"
MANAGE_ACTION_REMOVE = "remove"
MANAGE_ACTION_FINISH = "finish"

AUTH_MODE_AUTO = "auto"
AUTH_MODE_DYNAMIC = "dynamic"
AUTH_MODE_STATIC = "static"
AUTH_MODES = [AUTH_MODE_AUTO, AUTH_MODE_DYNAMIC, AUTH_MODE_STATIC]

# VIDAA / RemoteNOW broker on the TV (same KEY_* vocabulary as 海信爱家).
MQTT_KEEPALIVE = 30
MQTT_PROTOCOL_NAME = "VIDAA MQTT"
MQTT_CONNECT_TIMEOUT = 8.0
MQTT_CONNACK_WAIT = 8.0

# Internal connect results (not MQTT CONNACK codes).
RC_TCP_FAILED = 98
RC_TLS_FAILED = 99

STATIC_MQTT_USERNAME = "hisenseservice"
STATIC_MQTT_PASSWORD = "multimqttservice"
# Same client id sehaas/ha_hisense_tv publishes with. The TV authorizes
# remote keys for this name, not for an 爱家 dynamic client id.
REMOTE_CLIENT_ID = "HomeAssistant"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
