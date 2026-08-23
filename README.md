# HA Stream Deck GUI

A self-hosted web editor for the [`streamdeck.yaml`](https://github.com/basnijholt/home-assistant-streamdeck-yaml) file used by [`basnijholt/home-assistant-streamdeck-yaml`](https://github.com/basnijholt/home-assistant-streamdeck-yaml).

That project turns an Elgato Stream Deck into a Home Assistant control surface. Its config is hand-written YAML. This GUI replaces the SSH-and-indent workflow with a visual editor: pages on the left, a device mockup in the center, and the selected key or dial on the right.

**Stream Deck +** is a first-class layout — 8 LCD keys, a 4-segment touch strip, and 4 encoder dials — not eight extra keys.

This software is generic. Home Assistant URL, token, YAML path, deck model, backup count, and systemd unit name are all supplied by you. Nothing in this repository is tied to a specific home.

## What this is (and is not)

- **This GUI** authors and validates `streamdeck.yaml`. It talks to Home Assistant over HTTP only if you enter a URL and token.
- **It does not** open the Stream Deck USB device. The upstream `home-assistant-streamdeck-yaml` process still does that.
- **There is no login.** Anyone who can reach the port can edit the YAML and, if a token is saved, call Home Assistant through the server. Keep it on your LAN.

## Requirements

- Python 3.11 or newer
- A machine that can reach your Home Assistant instance (typically a Raspberry Pi 4 / arm64 on the same LAN)
- An existing or empty `streamdeck.yaml` path you choose
- Optional: Docker, if you prefer a container

## Native install

```bash
git clone https://github.com/Jkemp99/ha-streamdeck-gui.git
cd ha-streamdeck-gui
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Debian / Raspberry Pi OS you may need:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
```

Create a starting config (or point at one you already have), then serve:

```bash
mkdir -p ~/streamdeck
ha-streamdeck-gui generate-sample ~/streamdeck/streamdeck.yaml
export STREAMDECK_YAML_PATH=~/streamdeck/streamdeck.yaml
ha-streamdeck-gui serve --host 0.0.0.0 --port 8080
```

From a laptop or phone on the same network, open `http://<this-machine>:8080`.

In **Settings**:

1. Confirm the YAML path.
2. Set the Home Assistant URL **including the port**, for example `http://192.168.1.10:8123`.
3. Paste a Home Assistant long-lived access token. It stays on the server.
4. Pick your deck model (`mini`, `original`, `mk2`, `xl`, `plus`, `neo`).
5. Use **Test Home Assistant** (REST and websocket), then **Fetch devices**.
6. Click **Apply to Stream Deck**. That writes `deck.env` next to the YAML from the
   token already stored on the server, installs `home-assistant-streamdeck-yaml`
   if needed, and starts it as a user systemd service. The top bar should say
   **Deck: running**.

Edit keys and dials, then **Save**. Each save writes a timestamped backup next to the YAML file.

```bash
ha-streamdeck-gui validate ~/streamdeck/streamdeck.yaml
```

## Docker

Copy `.env.example` to `.env` and fill in only what you want. Never commit `.env`.

```bash
mkdir -p data
cp samples/streamdeck.yaml data/streamdeck.yaml
docker compose up --build
```

Open `http://<this-machine>:8080`. The container binds `0.0.0.0:$PORT` (default 8080). Your live YAML is mounted at `/data/streamdeck.yaml`.

Multi-arch image (amd64 and arm64):

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ha-streamdeck-gui .
```

## How to use the editor

1. **Open** loads the configured `streamdeck.yaml`.
2. Click a **page** in the sidebar. Anonymous pages are hidden pages reached only by `go-to-page`.
3. Click a **key**, **dial**, or **touch-strip segment** to edit it.
4. Drag keys to reorder them.
5. **YAML** shows the text and a diff against the file on disk.
6. **Save** validates, then writes. Trailing empty keys are trimmed. Files that still contain `!include` are refused unless you explicitly allow inlining.

A generated example lives in [`samples/streamdeck.yaml`](samples/streamdeck.yaml). It uses placeholder entities (`light.kitchen`, `media_player.living_room`, …). Replace them with your own.

### Deck layouts

| Model | What the canvas shows |
|---|---|
| Mini / Original / MK.2 / XL | Key grid only |
| Stream Deck + | 2×4 keys, LCD strip, four knobs |
| Neo | 2×4 keys plus a non-editable info screen and two touch keys (those extras are not in `streamdeck.yaml`) |

## Security

**There is no authentication.** Do not publish this port. Do not put it behind a reverse proxy on the public internet unless you add your own auth in front.

The Home Assistant token is stored only on the server, in `$XDG_CONFIG_HOME/ha-streamdeck-gui/settings.yaml` (or `~/.config/ha-streamdeck-gui/settings.yaml`), mode `0600`. It is never sent to the browser, never written to `localStorage`, and never logged.

Do not commit:

- `.env`
- your live `streamdeck.yaml`
- `settings.yaml`
- custom icon folders that contain personal photos

This repository’s sample YAML and `.env.example` use empty or placeholder values only.

## Configuration reference

Environment variables and the Settings page write the same fields:

| Setting | Environment variable | Notes |
|---|---|---|
| YAML path | `STREAMDECK_YAML_PATH` | Absolute path to `streamdeck.yaml` |
| Home Assistant URL | `HA_URL` | Scheme + host + **port** |
| Home Assistant token | `HA_TOKEN` | Long-lived access token, server-side only |
| Deck model | `DECK_MODEL` | `mini`, `original`, `mk2`, `xl`, `plus`, `neo` |
| Backup count | `BACKUP_COUNT` | Last N timestamped copies (default 10) |
| systemd unit | `SYSTEMD_SERVICE_NAME` | Optional; a restart is usually unnecessary |
| Custom icons | `ASSETS_DIR` | Optional. Defaults to `<yaml-dir>/assets` |
| Bind | `HOST`, `PORT` | Defaults `0.0.0.0` and `8080` |
| Settings dir | `HA_STREAMDECK_GUI_CONFIG_DIR` | Optional override for the server settings file |

Every write makes a timestamped backup under `.ha-streamdeck-gui-backups/` next to the YAML file. That folder is gitignored.

With `auto_reload: true` in `streamdeck.yaml`, the upstream Stream Deck process reloads the file itself. You usually do not need a systemd restart.

### `!include`

Upstream configs often split pages with `!include`. This editor can open a flattened view, but it will not overwrite a file that still contains `!include`. That avoids silently destroying a modular layout. Save as a new single file if you want the GUI to take over writes.

## Schema notes (from upstream source)

Derived from `home_assistant_streamdeck_yaml.py` in `basnijholt/home-assistant-streamdeck-yaml`. If this section drifts, the upstream source wins.

**Config:** `yaml_encoding`, `pages`, `anonymous_pages`, `state_entity_id`, `brightness`, `brightness_entity_id`, `auto_reload`, `long_press_duration`, `inactivity_time`.

**Button `special_type` values:** `next-page`, `previous-page`, `empty`, `go-to-page`, `close-page`, `turn-off`, `light-control`, `reload`.

`color_temp_kelvin` and `colormap` are **not** special types. They are optional keys on `special_type_data` when `special_type` is `light-control`, along with `colors` and `brightnesses`.

**Dials (Stream Deck +):** each page has a `dials` list. A physical encoder is often **two** consecutive entries — `dial_event_type: TURN` and `PUSH`. Upstream pairs consecutive dials whose event types differ. The touch strip is the LCD those dials render onto; there is no separate strip object in YAML. Swipe left/right changes pages. `allow_touchscreen_events` lets a tap/hold set min/max.

**Neo:** `python-elgato-streamdeck` supports it (8 LCD keys, 2 color touch keys, 248×58 info screen). Upstream YAML only maps buttons to the 8 LCD keys.

## Upstream Stream Deck gotchas

These apply to `home-assistant-streamdeck-yaml` itself, not this GUI. They are easy to lose hours on:

1. Some builds ignore a separate `HASS_PORT` and connect to port 80. Put the port on the host: `HASS_HOST=192.168.1.10:8123`.
2. The installed wheel may omit `assets/` (font + MDI icons). That causes `FileNotFoundError` on icon save and PIL `cannot open resource` on font load. Copy `assets/` from the upstream repo into the venv `site-packages/` directory. `pipx upgrade` wipes it again.
3. udev rules for USB vendor `0fd9` are required for non-root access. `TAG+="uaccess"` does not work over SSH (no local seat); use an explicit `MODE`.
4. A crash can leave libusb mutex assertions and a wedged deck. Unplug and replug the USB cable.

This GUI talks to Home Assistant with the full URL you provide, so it does not inherit the `HASS_PORT` bug. It does not open the Stream Deck USB device.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT. See [LICENSE](LICENSE).
