# Changelog

All notable changes are documented here. Versions follow [Semantic Versioning](https://semver.org/);
each `## [x.y.z]` section becomes the GitHub release notes.

## [Unreleased]

### Added
- Renaming the device also renames the integration entry. Clearing the custom name restores the
  original name. Existing entries are migrated automatically.

### Changed
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
