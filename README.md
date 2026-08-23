# HA Stream Deck GUI

A self-hosted LAN web editor for the [`streamdeck.yaml`](https://github.com/basnijholt/home-assistant-streamdeck-yaml) file used by [`basnijholt/home-assistant-streamdeck-yaml`](https://github.com/basnijholt/home-assistant-streamdeck-yaml).

That upstream project paints an Elgato Stream Deck from YAML and talks to Home Assistant. This GUI replaces the SSH-and-indent workflow: pages on the left, a device mockup in the center, the selected key or dial on the right.

**Stream Deck +** is a first-class layout — 8 LCD keys, a 4-segment touch strip, and 4 encoder dials — not eight extra keys.

Nothing in this repository is tied to a specific home. You supply the Home Assistant URL, token, YAML path, and deck model.

If something fails after install, start at [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Two processes

This GUI does **not** open the Stream Deck USB device.

```
Laptop / phone browser
        │
        │  http://<pi>:8080
        ▼
Raspberry Pi (or any Linux box with the deck plugged in)
  ├─ ha-streamdeck-gui          ← this repo; edits YAML
  ├─ streamdeck.yaml            ← both processes use the same file
  └─ home-assistant-streamdeck-yaml  ← USB + Home Assistant
```

- **This GUI** authors and validates `streamdeck.yaml`. It calls Home Assistant only if you save a URL and token.
- **`home-assistant-streamdeck-yaml`** is what lights the keys. **Apply to Stream Deck** in Settings installs it as a user systemd service.
- **There is no login.** Anyone who can reach port 8080 can edit the YAML. Keep it on your LAN.

Plug the Stream Deck into the machine that runs the deck service. A laptop editor pointed at a sample file will not drive the physical deck.

## What you need

- Python 3.11 or newer
- `git`
- A Linux machine that can reach Home Assistant (Raspberry Pi 4 / arm64 on the same LAN is the usual setup)
- The Stream Deck USB-connected to **that** machine
- A Home Assistant long-lived access token (Profile → Security → Long-lived access tokens)
- Optional: Docker, if you only want the editor and will run the deck process on the host

## Fresh install (Raspberry Pi OS)

SSH into the Pi. These packages cover the GUI, Cairo key rendering, USB, and Apply (which clones upstream fonts if the pip wheel omitted them):

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip \
  libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
  libgdk-pixbuf-2.0-0 shared-mime-info \
  libusb-1.0-0 libhidapi-libusb0 libffi-dev \
  libudev-dev libusb-1.0-0-dev
```

### USB access

Upstream’s `TAG+="uaccess"` rule does **not** work over SSH (no local seat). Use an explicit mode:

```bash
echo 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", MODE="0666"' | sudo tee /etc/udev/rules.d/99-streamdeck.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug the Stream Deck, plug it back in, then check it is visible:

```bash
lsusb | grep -i 0fd9
```

### Install and start the editor

```bash
git clone https://github.com/Jkemp99/ha-streamdeck-gui.git
cd ha-streamdeck-gui
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

mkdir -p ~/streamdeck
# Either start empty and build in the UI, or write the example (placeholders — see below)
ha-streamdeck-gui generate-sample ~/streamdeck/streamdeck.yaml

export STREAMDECK_YAML_PATH=~/streamdeck/streamdeck.yaml
ha-streamdeck-gui serve --host 0.0.0.0 --port 8080
```

From a laptop or phone on the same network, open `http://<pi-hostname-or-ip>:8080`.

Keep the GUI running after logout with a user systemd unit. Copy [contrib/ha-streamdeck-gui.service](contrib/ha-streamdeck-gui.service) and enable linger so it starts at boot:

```bash
mkdir -p ~/.config/systemd/user
cp contrib/ha-streamdeck-gui.service ~/.config/systemd/user/
# Edit WorkingDirectory / ExecStart if the clone is not ~/ha-streamdeck-gui
systemctl --user daemon-reload
systemctl --user enable --now ha-streamdeck-gui
loginctl enable-linger "$USER"
```

### Settings (once)

1. Confirm **streamdeck.yaml path** is the file the deck should paint (`~/streamdeck/streamdeck.yaml`).
2. Set the Home Assistant URL **including the port**, for example `http://192.168.1.10:8123`. Local HTTP uses `ws`, not `wss`.
3. Paste the long-lived access token. It stays on the server (`~/.config/ha-streamdeck-gui/settings.yaml`, mode `0600`).
4. Pick your deck model (`mini`, `original`, `mk2`, `xl`, `plus`, `neo`).
5. **Test Home Assistant** (REST and websocket), then **Fetch devices**.
6. Replace every sample `entity_id` with a real device from the picker, **or** clear the sample keys, **before** Apply. A missing id crashes the deck process and can wedge USB.
7. **Apply to Stream Deck**. That writes `~/streamdeck/deck.env` from the stored token, installs `home-assistant-streamdeck-yaml` in `~/streamdeck/.venv-deck`, copies fonts/icons if the wheel omitted them, and starts the user unit `home-assistant-streamdeck-yaml`. The top bar should say **Deck: running**.

`loginctl enable-linger "$USER"` is required if you want the deck service to start at boot without an SSH session.

## Using the editor

- **Reload from deck** re-reads the configured YAML — the same file the USB process paints. The Stream Deck has no separate layout stored in hardware.
- Click a **page**, then a **key**, **dial**, or **touch-strip segment**. Drag keys to reorder.
- Assigning a device to a blank key turns it into a normal button. Save. Unused keys stay `special_type: empty` and look blank on purpose.
- Brightness **rotate** on a dial must call `light.turn_on` (with `brightness`). `light.toggle` on a dimmer turns the light off. Press on that dial can stay `light.toggle`.
- **Save** validates, writes a timestamped backup next to the YAML, and (with `auto_reload: true`) the deck reloads the file. You usually do not restart the deck service.
- **Load sample** is an example layout with fake ids (`light.kitchen`, …). Do **not** Save that onto a live deck until every entity is real. The GUI blocks Save/Apply of unknown ids when a token is set.
- **YAML** shows the text and a diff against the file on disk.

```bash
ha-streamdeck-gui validate ~/streamdeck/streamdeck.yaml
```

### Deck layouts

| Model | What the canvas shows |
|---|---|
| Mini / Original / MK.2 / XL | Key grid only |
| Stream Deck + | 2×4 keys, LCD strip, four knobs |
| Neo | 2×4 keys plus a non-editable info screen and two touch keys (those extras are not in `streamdeck.yaml`) |

## Updating

Pull new editor code, then restart **only the GUI**. Do not restart `home-assistant-streamdeck-yaml` unless Apply or USB recovery says to.

```bash
cd ~/ha-streamdeck-gui
git pull
systemctl --user restart ha-streamdeck-gui
# If you started it with nohup instead of systemd:
# pkill -f 'ha-streamdeck-gui serve'
# nohup "$HOME/ha-streamdeck-gui/.venv/bin/ha-streamdeck-gui" serve --host 0.0.0.0 --port 8080 >/tmp/ha-streamdeck-gui.log 2>&1 &
```

Hard-refresh the browser (`http://<pi>:8080`) so it drops cached JS.

## Docker

Docker here is the **editor only**. It cannot talk to the Stream Deck USB device or install the host systemd unit. Use it on a laptop to edit a copy of the YAML, or mount the live file and still run the deck process on the host.

Copy `.env.example` to `.env`. Never commit `.env`.

```bash
mkdir -p data
cp samples/streamdeck.yaml data/streamdeck.yaml
docker compose up --build
```

Open `http://<this-machine>:8080`. The container binds `0.0.0.0:$PORT` (default 8080). The YAML is `/data/streamdeck.yaml`.

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ha-streamdeck-gui .
```

## Security

**There is no authentication.** Do not publish this port. Do not put it on the public internet unless you add your own auth in front.

The Home Assistant token is stored only on the server, never sent to the browser, never written to `localStorage`, and never logged.

Do not commit `.env`, a live `streamdeck.yaml`, `settings.yaml`, `deck.env`, or personal icon folders.

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

Every write makes a timestamped backup under `.ha-streamdeck-gui-backups/` next to the YAML. That folder is gitignored.

With `auto_reload: true` in `streamdeck.yaml`, the deck process reloads the file itself.

Apply writes `deck.env` next to the YAML (`HASS_HOST` includes the port, `WEBSOCKET_PROTOCOL` is `ws` or `wss` from your URL). Mode `0600`.

### `!include`

Upstream configs often split pages with `!include`. This editor can open a flattened view, but it will not overwrite a file that still contains `!include`. Save as a new single file if you want the GUI to take over writes.

## Schema notes (from upstream source)

Derived from `home_assistant_streamdeck_yaml.py` in `basnijholt/home-assistant-streamdeck-yaml`. If this section drifts, the upstream source wins.

**Config:** `yaml_encoding`, `pages`, `anonymous_pages`, `state_entity_id`, `brightness`, `brightness_entity_id`, `auto_reload`, `long_press_duration`, `inactivity_time`.

**Button `special_type` values:** `next-page`, `previous-page`, `empty`, `go-to-page`, `close-page`, `turn-off`, `light-control`, `reload`.

`color_temp_kelvin` and `colormap` are **not** special types. They are optional keys on `special_type_data` when `special_type` is `light-control`, along with `colors` and `brightnesses`.

**Dials (Stream Deck +):** each page has a `dials` list. A physical encoder is often **two** consecutive entries — `dial_event_type: TURN` and `PUSH`. Upstream pairs consecutive dials whose event types differ. The touch strip is the LCD those dials render onto; there is no separate strip object in YAML. Swipe left/right changes pages. `allow_touchscreen_events` lets a tap/hold set min/max.

**Neo:** `python-elgato-streamdeck` supports it (8 LCD keys, 2 color touch keys, 248×58 info screen). Upstream YAML only maps buttons to the 8 LCD keys.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Laptop-only editor (does **not** drive a physical deck):

```bash
export STREAMDECK_YAML_PATH="$PWD/samples/streamdeck.yaml"
export DECK_MODEL=plus
ha-streamdeck-gui serve --host 127.0.0.1 --port 8765
```

## License

MIT. See [LICENSE](LICENSE).
