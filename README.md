# Gree Local for Home Assistant

Control Gree air conditioners and heat pumps (and rebrands using the same Wi-Fi module:
Cooper&Hunter, Sinclair, Tosot, Daitsu, Ekokai, ...) **directly by IP address**, fully local.

## Why not the built-in Gree integration?

The built-in integration finds units by **UDP broadcast**. Broadcasts do not cross VLANs or
subnets and are filtered by many routers and mesh systems, so units on an IoT VLAN are never found.

Gree Local talks to each unit **unicast at its IP address**:

- Works across VLANs/subnets: only UDP port 7000 to the unit has to be allowed.
- Units are still **discovered automatically** through Home Assistant's DHCP watcher
  (Gree Wi-Fi modules use the MAC prefix `F4:91:1E`), and an IP change is picked up without
  touching the configuration.
- The device key is stored, so restarts do not re-pair. If the unit is reset, the integration
  re-pairs on its own.
- Retries lost UDP packets instead of marking the unit unavailable.

## Installation

### Home Assistant Marketplace (2026.11+)

1. **Settings → Marketplace → ⋮ → Custom repositories**, add
   `https://github.com/Lukas0610/ha-gree-local`, type **Integration**.
2. Search for **Gree Local**, select **Download**, then restart Home Assistant.

Updates appear under **Settings → Updates** like any other update.

### Manual

Copy `custom_components/gree_local` into your `config/custom_components/` folder and restart.

## Setup

1. Pair the unit with your Wi-Fi once using the Gree+ or EWPE Smart app.
2. Give it a DHCP reservation in your router (recommended).
3. Either accept the **Discovered** card under **Settings → Devices & services**, or
   select **Add integration → Gree Local** and enter the IP address.

To change the polling interval, open the integration and select **Configure**.
To move a unit to a new address manually, select **⋮ → Reconfigure**.

## Entities

| Entity | Notes |
|---|---|
| Climate | Off / auto / cool / dry / fan / heat, 16–30 °C, 5 fan speeds + auto, vertical and horizontal swing, presets eco / boost (turbo) / sleep / away (8 °C frost protection, heat mode only) |
| Temperature | Room temperature from the indoor unit |
| Outdoor temperature | Disabled by default; enable it if your unit reports it |
| Panel light, X-Fan, Health, Fresh air, Quiet | Switches; features your unit lacks have no effect |

## Troubleshooting

- **No answer from the unit:** check that UDP port 7000 from Home Assistant to the unit is allowed
  by your firewall/VLAN rules.
- **Report a bug:** attach the file from **⋮ → Download diagnostics** on the integration page.
  The key, MAC and IP are removed automatically.

## Development

`custom_components/gree_local/api.py` has no Home Assistant imports. Its tests run against a
simulated unit:

```sh
pip install -r requirements_test.txt
pytest tests
```

See [RELEASING.md](RELEASING.md) for the release process.
