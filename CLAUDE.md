# CLAUDE.md

Home Assistant custom integration `gree_local`. It controls Gree HVAC units by unicast UDP to a known IP,
unlike the core `gree` integration, which uses broadcast. It's distributed through the HA Marketplace
(HACS built into core since 2026.11; same `hacs.json`, GitHub-only).
Owner: Lukas Berger <mail@lukasberger.at>. License: MIT (`LICENSE`, the GitHub template text).

## Layout

```
custom_components/gree_local/
  api.py           Protocol client. NO Home Assistant imports (tested standalone). Keep it that way.
  const.py         Domain, config keys, STATUS_COLUMNS polled every cycle.
  coordinator.py   DataUpdateCoordinator: polling, auto-rebind on failure, async_send() for commands.
  __init__.py      Entry setup; GreeConfigEntry = ConfigEntry[GreeCoordinator] via entry.runtime_data.
  config_flow.py   user (IP), dhcp (discovery + IP update), discovery_confirm, reconfigure, options.
  entity.py        GreeEntity base (device info, _value()), decode_temperature().
  climate.py / sensor.py / switch.py   Platforms.
  diagnostics.py   Redacted download (host, key, mac, unique_id).
  icons.json, translations/{en,de}.json, manifest.json
  brand/           Official Gree icon/logo, copied from home-assistant/brands core_brands/gree
                   (same images as the core integration). Re-download from there; don't redraw.
tests/             pytest against a fake UDP Gree unit (FakeGree) on localhost. Only exercises api.py.
hacs.json, CHANGELOG.md, .github/workflows/{validate,release}.yml
```

## Commands

```sh
pip install -r requirements_test.txt
pytest -q tests
```
On the dev machine a git-ignored venv exists at `.venv` (Windows: `.venv\Scripts\python -m pytest -q tests`).
CI runs hassfest, the Marketplace action (`hacs/action`) and pytest. Nothing tests the HA-side modules
locally. If you change them, at least run `python -m py_compile` on each file, and say that they
weren't exercised against a real HA instance.

## Protocol facts (api.py)

- UDP port 7000, JSON. Payloads are AES-encrypted and base64-encoded in `"pack"`.
- Flow: `scan` (generic key) → `bind` (`i: 1`, generic key; reply contains the device key) →
  `status` / `cmd` (`i: 0`, device key).
- Two firmware generations: ECB (key `a3K8Bx%2r8Y7#xDh`) and GCM (key `{yxAHAY_Lm6pbC/<`, fixed
  nonce, AAD `qualcomm-test`, extra `"tag"` field). `bind()` tries ECB, then GCM.
- Units **silently drop** packets they can't decrypt, so a stale key looks like a timeout. That's
  why the coordinator rebinds after any status failure and saves the new key to entry data.
- `SetTem` is always Celsius on the wire. `TemSen`/`OutEnvTem` are offset by +40 on most firmware
  (`decode_temperature`). A value of 0 means "no sensor".
- `SwUpDn`: 0 default, 1 full swing, 2–6 fixed positions, 7–11 partial swing.
- Requests are serialized with a lock, and each one retries `retries` times on timeout.

## Conventions and invariants

- **Use standard HA building blocks everywhere** (explicit user preference): selectors in flows,
  standard climate features/constants (presets, `SWING_ON/OFF`, `swing_horizontal_mode`), device
  classes, entity descriptions, `icons.json`, translated exceptions (`translation_key`), diagnostics.
  Custom strings only where HA has no standard (e.g. fan speeds `medium_low`/`medium_high`).
- **Every user-facing string goes in BOTH `translations/en.json` and `translations/de.json`.**
  The key structure must match. German uses informal "du".
- unique_id = `format_mac(mac from scan reply)`. The device also gets a `CONNECTION_NETWORK_MAC`
  connection, which the manifest's DHCP `registered_devices` matcher relies on. Don't remove it.
- Commands go through `coordinator.async_send(params)`. It applies the change optimistically,
  so don't call `async_request_refresh()` after it.
- The update listener in `__init__.py` only changes the polling interval. It also fires when the
  coordinator saves a new key or the title changes, so it must **not** reload the entry.
- The entry title follows the device's user-given name (`name_by_user`, via a device registry
  listener in `__init__.py`). The device's own name comes from `entry.data[CONF_NAME]`, **never
  from `entry.title`**, so clearing the custom name can revert the title to the original.
- Config entry version is 1.2 (`MINOR_VERSION` in `config_flow.py`). Bump the minor version and
  extend `async_migrate_entry` whenever stored entry data changes shape.
- Minimum HA version is `2025.2.0` (`hacs.json`). APIs in use: `AddConfigEntryEntitiesCallback`,
  `helpers.service_info.dhcp`, `entry.runtime_data`, `_get_reconfigure_entry`. Raise the minimum
  if you use newer APIs.
- Manifest keys: `domain`, `name` first, then alphabetical (hassfest enforces this).
  `categories` (1–3, dot notation for subcategories) is required by Marketplace validation; see
  https://contributors.home-assistant.io/core/integrations/categories/
  `requirements` is empty because HA already ships `cryptography`.

## Releasing

- The version lives only in `custom_components/gree_local/manifest.json` (SemVer, **no `v` prefix**).
  The Marketplace requires the tag to equal that version.
- Steps: bump the manifest version, add a `## [x.y.z]` section to `CHANGELOG.md`, merge to `main`,
  then run **Actions → Release**. The workflow validates, refuses existing tags or missing
  changelog sections, and marks `aN`/`bN`/`rcN`/`devN` versions as pre-releases.
- Never edit or move a published tag. Fix things in a new patch release.
