"""Constants for the Gree Local integration."""

DOMAIN = "gree_local"

DEFAULT_PORT = 7000
DEFAULT_SCAN_INTERVAL = 5  # seconds; user-adjustable in the options flow (1-300)

CONF_MAC = "mac"
CONF_KEY = "key"
CONF_CIPHER = "cipher"
CONF_FIRMWARE = "firmware"

# Columns requested on every poll. Units silently return 0 for unsupported ones.
STATUS_COLUMNS = [
    "Pow",
    "Mod",
    "SetTem",
    "TemUn",
    "TemRec",
    "TemSen",
    "WdSpd",
    "Tur",
    "Quiet",
    "SwUpDn",
    "SwingLfRt",
    "Air",
    "Blo",
    "Health",
    "SwhSlp",
    "SlpMod",
    "Lig",
    "StHt",
    "SvSt",
    "OutEnvTem",
]

# Most firmware reports the room temperature sensor shifted by +40.
TEMP_SENSOR_OFFSET = 40
