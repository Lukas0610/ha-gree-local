"""Constants for the Gree Local integration."""

DOMAIN = "gree_local"

DEFAULT_PORT = 7000
# Polling options (options flow). Intervals are milliseconds, the duration is seconds.
DEFAULT_SCAN_INTERVAL = 2500  # CONF_SCAN_INTERVAL, 500-60000 ms (seconds before entry 1.3)
MIN_SCAN_INTERVAL = 500
MAX_SCAN_INTERVAL = 60000
# Hot path: poll faster for a while after a command, so follow-up changes
# (e.g. the unit adjusting itself) show up quickly.
CONF_FAST_POLL_INTERVAL = "fast_poll_interval"
DEFAULT_FAST_POLL_INTERVAL = 250  # ms, 100-1000
MIN_FAST_POLL_INTERVAL = 100
MAX_FAST_POLL_INTERVAL = 1000
CONF_FAST_POLL_DURATION = "fast_poll_duration"
DEFAULT_FAST_POLL_DURATION = 5  # s, 0-300; 0 disables the hot path
MAX_FAST_POLL_DURATION = 300

CONF_MAC = "mac"
CONF_KEY = "key"
CONF_CIPHER = "cipher"
CONF_FIRMWARE = "firmware"  # "ver" from scan: Wi-Fi module firmware
# Optional firmware details, refreshed from the unit on every setup.
CONF_MID = "mid"
CONF_HID = "hid"
CONF_BOARD_VERSION = "board_version"

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
