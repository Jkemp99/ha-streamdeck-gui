# Troubleshooting

This GUI only edits `streamdeck.yaml`. The USB Stream Deck is painted by `home-assistant-streamdeck-yaml`. Fix the process that is actually failing.

Useful status:

```bash
# Editor
systemctl --user status ha-streamdeck-gui --no-pager
curl -sS http://127.0.0.1:8080/api/health

# Deck (USB)
systemctl --user status home-assistant-streamdeck-yaml --no-pager
journalctl --user -u home-assistant-streamdeck-yaml -n 80 --no-pager
```

The editor API also exposes deck status at `http://<host>:8080/api/service/status`.

## Symptom → fix

| You see | Likely cause | What to do |
|---|---|---|
| Editor page will not load (`Connection refused` on `:8080`) | GUI process not running | Start or restart `ha-streamdeck-gui` only. Do not restart the deck unit. |
| Top bar **Deck: not running** | User unit not installed or crashed | Settings → **Apply to Stream Deck**. Then `journalctl --user -u home-assistant-streamdeck-yaml -n 80`. |
| Deck keys stay black after Apply | Cairo missing | `sudo apt-get install -y libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info`. Apply again. |
| Logs: `no library called "cairo-2"` / `Failed to render` | Same as above | Install Cairo/Pango. Apply refuses if Cairo is missing. |
| Logs: `FileNotFoundError` / PIL `cannot open resource` | Pip wheel omitted `assets/` (Roboto + MDI) | Apply copies them from the upstream git repo. Install `git`. |
| Logs: `KeyError` then `libusb` / `SIGABRT` | `entity_id` is not in Home Assistant | Fetch devices. Replace or clear the stale id. Save is refused while a token is set. Unplug/replug the deck. |
| Deck flashes every ~15s then blanks | systemd restart loop after ABRT | `systemctl --user reset-failed home-assistant-streamdeck-yaml`. Unplug USB. Fix the YAML. Apply or `restart` once. The unit stops after 3 failures in 60s. |
| `Permission denied` opening the Stream Deck | udev / SSH seat | Use `MODE="0666"` (see README). Reload udev. Unplug/replug. `lsusb \| grep 0fd9`. |
| HA test fails, deck never connects | URL missing port, or `wss` against local `http` | Use `http://<ha-host>:8123`. Apply writes `HASS_HOST=host:8123` and `WEBSOCKET_PROTOCOL=ws` for http. |
| **Load sample** then the deck dies | Sample placeholders (`light.kitchen`, …) | Confirm dialog is there for a reason. Reload from deck to discard unsaved sample. Restore a backup under `.ha-streamdeck-gui-backups/` if you already Saved. |
| Assigned a device; key still blank on the deck | `special_type: empty` left on | Current editor clears that when you assign a device. On an old checkout: set **Type** to **Normal button**, Save. |
| Turning a brightness knob turns the light off | Dial **Rotate** service is `light.toggle` | Use `light.turn_on` plus `brightness: '{{ dial_value() \| int }}'`. Keep `light.toggle` on **Press** if you want on/off. Lowest dim of `0` is also off in Home Assistant; min `1` is safer. |
| Device picker search stays open; click does nothing | Old editor JS (label wrapping the list) | `git pull` and restart the GUI. Hard-refresh the browser. |
| Clicking a search result does not stick | Same, or you never Saved | Assign, confirm the caption under the deck, **Save**. |
| **Reload from deck** looks empty | The YAML really has empty Home keys | Open **Media** / **Scenes** in the sidebar. The caption under the mockup shows the file path and how many keys that page has. |
| Laptop `:8765` / `:8770` does not change the physical deck | That process is editing `samples/streamdeck.yaml` | Only the Pi editor pointed at the live YAML drives the hardware. |
| After `git pull` the deck went blank | GUI restart also restarted or killed the deck | Restart **only** `ha-streamdeck-gui`. See [Updating](README.md#updating). |
| Service hits start limit | Three crashes in 60s | `systemctl --user reset-failed home-assistant-streamdeck-yaml` after you fix YAML/USB. |
| Apply: `git is not installed` | Fonts/icons download | `sudo apt-get install -y git` |
| Apply: unknown entity names | HA ids changed or sample leftovers | Fetch devices. The red outline is a stale id. |
| `!include` save refused | Modular upstream layout | Save as a new single file, or keep editing the split files by hand. |

## Recover a wedged Stream Deck

After a `KeyError` / `SIGABRT` the USB device often stays dead until power-cycled.

1. Stop the crash loop: `systemctl --user stop home-assistant-streamdeck-yaml`
2. Unplug the Stream Deck USB for a few seconds, plug it back in.
3. Confirm `lsusb` still shows vendor `0fd9`.
4. Fix unknown entities (Reload from deck, Fetch devices, replace ids, Save).
5. `systemctl --user reset-failed home-assistant-streamdeck-yaml`
6. `systemctl --user start home-assistant-streamdeck-yaml`
7. Wait ~10s. `systemctl --user status` should stay `active` on the same PID.

Do not leave `Restart=on-failure` hammering a wedged USB. The unit already limits that (`StartLimitBurst=3`).

## Restore YAML from a backup

Saves write timestamped copies next to the live file:

```text
~/streamdeck/.ha-streamdeck-gui-backups/streamdeck.yaml.<timestamp>.yaml
```

Copy one back over `~/streamdeck/streamdeck.yaml` (or Restore in the editor if you use that path). With `auto_reload: true` the deck picks it up.

## Logs to ignore vs act on

- `DialEventType.TURN` / `has been called` — normal while you twist a knob.
- `Failed to render` / `cairo-2` — install Cairo.
- `KeyError: 'light.…'` — that entity is gone; it will abort USB.
- `StartLimit` / `failed with result 'signal'` — already crashed; unplug and fix YAML before starting again.

## Editor vs deck

| Goal | Restart this |
|---|---|
| New GUI/JS from `git pull` | `ha-streamdeck-gui` |
| Token, HA URL, or first-time install | Settings → **Apply to Stream Deck** |
| YAML edit | **Save** only (`auto_reload: true`) |
| Blank keys after a crash | Unplug USB, then restart `home-assistant-streamdeck-yaml` once |
