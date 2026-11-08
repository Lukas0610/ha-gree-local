# Changelog

All notable changes are documented here. Versions follow [Semantic Versioning](https://semver.org/);
each `## [x.y.z]` section becomes the GitHub release notes.

## [0.3.0]

### Added
- Fast polling after a change: for a configurable time after you change a setting (default 10 s,
  0 turns it off), the unit is polled at a faster interval (default 250 ms, 100–1000 ms), so its
  reaction shows up almost immediately.

### Changed
- The polling interval is now set in milliseconds (500–60000 ms, default 5000 ms). Existing
  intervals are converted from seconds automatically.

## [0.2.1]

### Added
- The device page's firmware line also shows the control board version, module ID (MID) and
  control board firmware image (HID). Firmware details are refreshed on every start, so OTA
  updates show up.

### Fixed
- A MAC address edited in "Connection details" is no longer replaced by the one the unit reports.

## [0.2.0]

### Added
- Renaming the device also renames the integration entry. Clearing the custom name restores the
  original name. Existing entries are migrated automatically.
- Reconfigure shows the MAC address, device key and encryption in a "Connection details" section
  and lets you change them. Changes are verified against the unit before they are saved.

### Changed
- Default polling interval is now 5 s (was 30 s); the minimum is 1 s (was 10 s). Units with a
  custom interval keep it.
- The panel light switch is now a regular control instead of a configuration entity, so it shows up
  in dashboards and under "Controls" on the device page.

### Fixed
- Added the integration category required by the Marketplace validation.

## [0.1.0]

### Added
- Unicast communication with Gree units by IP address (works across VLANs/subnets, no broadcast).
- Automatic discovery via DHCP; IP changes of known units are picked up automatically.
- Support for both ECB (older) and GCM (newer) firmware encryption.
- Climate entity: HVAC modes, target temperature, fan speed, vertical/horizontal swing, presets
  (eco, boost, sleep, away/8 °C heating).
- Switches: panel light, X-Fan, health, fresh air, quiet.
- Room temperature and (optional) outdoor temperature sensors.
- Options flow for the polling interval, reconfigure flow for a new address, diagnostics download.
- English and German translations.
