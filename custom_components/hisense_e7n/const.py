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
CONF_POWER_ON_BUTTON = "power_on_button"

AUTH_MODE_AUTO = "auto"
AUTH_MODE_DYNAMIC = "dynamic"
AUTH_MODE_STATIC = "static"
AUTH_MODES = [AUTH_MODE_AUTO, AUTH_MODE_DYNAMIC, AUTH_MODE_STATIC]

# VIDAA / RemoteNOW broker on the TV (same KEY_* vocabulary as 海信爱家).
MQTT_KEEPALIVE = 30
MQTT_PROTOCOL_NAME = "VIDAA MQTT"

STATIC_MQTT_USERNAME = "hisenseservice"
STATIC_MQTT_PASSWORD = "multimqttservice"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
