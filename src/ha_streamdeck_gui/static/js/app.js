const ICONS = [
  "lightbulb", "lightbulb-group", "lamp", "floor-lamp", "string-lights",
  "power", "power-sleep", "restart", "refresh", "home", "cog",
  "play", "pause", "play-pause", "play-circle", "volume-high", "volume-off",
  "skip-next", "skip-previous", "movie", "television", "speaker",
  "thermostat", "thermometer", "fan", "air-conditioner",
  "garage", "door", "lock", "lock-open", "window-closed",
  "robot-vacuum", "washing-machine", "stove",
  "weather-sunset-up", "weather-night", "white-balance-sunny",
  "palette", "brush", "lamp",
  "chevron-left", "chevron-right", "keyboard-return", "close",
  "timer", "clock", "bell", "shield-home",
  "account", "car", "bed", "sofa", "shower",
  "script-text", "playlist-play", "spotify",
];

const SPECIAL_ICONS = {
  "next-page": "chevron-right",
  "previous-page": "chevron-left",
  empty: "",
  "go-to-page": "page-next",
  "close-page": "close",
  "turn-off": "power",
  "light-control": "palette",
  reload: "refresh",
};

const state = {
  settings: null,
  models: [],
  schema: null,
  config: emptyConfig(),
  yamlText: "",
  hasIncludes: false,
  issues: [],
  entities: [],
  services: {},
  selected: null,
  pageKind: "pages",
  pageIndex: 0,
  dirty: false,
};

function emptyConfig() {
  return {
    brightness: 100,
    auto_reload: false,
    pages: [{ name: "Home", buttons: [], dials: [] }],
    anonymous_pages: [],
  };
}

function emptyButton() {
  return { special_type: "empty" };
}

function api(path, options = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.detail?.message || data.detail || response.statusText;
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return data;
  });
}

function currentModel() {
  return (
    state.models.find((model) => model.id === state.settings?.deck_model)
    || state.models.find((model) => model.id === "plus")
    || state.models[0]
  );
}

function currentPages() {
  return state.pageKind === "anonymous_pages" ? state.config.anonymous_pages : state.config.pages;
}

function currentPage() {
  const pages = currentPages() || [];
  return pages[state.pageIndex] || pages[0] || { name: "Home", buttons: [], dials: [] };
}

function allPageNames() {
  return [
    ...(state.config.pages || []).map((page) => page.name),
    ...(state.config.anonymous_pages || []).map((page) => page.name),
  ];
}

function pairDials(dials = []) {
  const paired = [];
  let skip = false;
  for (let i = 0; i < dials.length; i += 1) {
    if (skip) {
      skip = false;
      continue;
    }
    const next = dials[i + 1];
    if (next && dials[i].dial_event_type !== next.dial_event_type) {
      paired.push([dials[i], next]);
      skip = true;
    } else {
      paired.push([dials[i], null]);
    }
  }
  return paired;
}

function physicalDials(page, slots = 4) {
  const result = Array.from({ length: slots }, () => ({ turn: null, push: null }));
  pairDials(page.dials || []).forEach((pair, index) => {
    if (index >= slots) return;
    pair.forEach((dial) => {
      if (!dial) return;
      if ((dial.dial_event_type || "").toUpperCase() === "PUSH" && !result[index].push) {
        result[index].push = dial;
      } else {
        result[index].turn = dial;
      }
    });
  });
  return result;
}

function writePhysicalDials(page, slots) {
  const dials = [];
  slots.forEach((slot) => {
    if (slot.turn) {
      dials.push({ ...slot.turn, dial_event_type: slot.turn.dial_event_type || "TURN" });
    }
    if (slot.push) {
      dials.push({ ...slot.push, dial_event_type: slot.push.dial_event_type || "PUSH" });
    }
  });
  page.dials = dials;
}

function displayText(item) {
  if (!item) return "";
  const text = item.text || "";
  if (text.includes("{")) return text.split("\n")[0].slice(0, 18);
  return text;
}

function previewIcon(item) {
  if (!item) return "";
  if (item.icon_mdi) return item.icon_mdi;
  if (item.special_type && SPECIAL_ICONS[item.special_type]) return SPECIAL_ICONS[item.special_type];
  return "";
}

function keyBackground(item) {
  if (!item || item.special_type === "empty") return "#050506";
  return item.icon_background_color || "#050506";
}

function ringPercent(item) {
  if (!item?.icon || typeof item.icon !== "string") return null;
  if (!item.icon.startsWith("ring:")) return null;
  const raw = item.icon.slice(5).trim();
  if (raw.includes("{")) return 40;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
}

function renderKeyFace(el, item) {
  el.innerHTML = "";
  if (!item || item.special_type === "empty") return;
  el.style.background = keyBackground(item);
  const pct = ringPercent(item);
  if (pct !== null) {
    el.style.background = `conic-gradient(#e23 0 ${pct}%, #222 ${pct}% 100%)`;
  }
  const iconName = previewIcon(item);
  if (item.icon && item.icon.startsWith("url:")) {
    const img = document.createElement("img");
    img.src = item.icon.slice(4);
    img.alt = "";
    el.append(img);
  } else if (item.icon && customIconPreview(item.icon)) {
    const img = document.createElement("img");
    img.src = customIconPreview(item.icon);
    img.alt = "";
    el.append(img);
  } else if (iconName) {
    const icon = document.createElement("span");
    icon.className = `mdi mdi-${iconName}`;
    icon.style.color = item.icon_mdi_color || item.text_color || "#fff";
    el.append(icon);
  }
  const label = displayText(item);
  if (label) {
    const text = document.createElement("div");
    text.className = "label";
    text.textContent = label;
    text.style.color = item.text_color || "#fff";
    if (item.text_size) text.style.fontSize = `${Math.max(9, Math.min(16, item.text_size))}px`;
    el.append(text);
  }
}

function renderPages() {
  const renderList = (el, pages, kind) => {
    el.innerHTML = "";
    (pages || []).forEach((page, index) => {
      const row = document.createElement("div");
      row.className = "page-item";
      if (state.pageKind === kind && state.pageIndex === index) row.classList.add("active");
      const name = document.createElement("input");
      name.value = page.name;
      name.addEventListener("click", (event) => event.stopPropagation());
      name.addEventListener("change", () => {
        page.name = name.value.trim() || page.name;
        markDirty();
        render();
      });
      const del = document.createElement("button");
      del.className = "ghost del";
      del.type = "button";
      del.textContent = "×";
      del.addEventListener("click", (event) => {
        event.stopPropagation();
        if (kind === "pages" && state.config.pages.length <= 1) return;
        pages.splice(index, 1);
        state.pageIndex = 0;
        markDirty();
        render();
      });
      row.append(name, del);
      row.addEventListener("click", () => {
        state.pageKind = kind;
        state.pageIndex = index;
        state.selected = null;
        render();
      });
      el.append(row);
    });
  };
  renderList(document.getElementById("page-list"), state.config.pages, "pages");
  renderList(document.getElementById("anon-list"), state.config.anonymous_pages, "anonymous_pages");
}

function isSelected(kind, index, event = null) {
  const sel = state.selected;
  return sel && sel.kind === kind && sel.index === index && (event ? sel.event === event : true);
}

function renderDevice() {
  const model = currentModel();
  const page = currentPage();
  const device = document.getElementById("device");
  device.className = `device ${model.id}`;
  device.innerHTML = "";

  if (model.has_info_screen) {
    const screen = document.createElement("div");
    screen.className = "neo-screen";
    screen.textContent = page?.name || "Neo";
    device.append(screen);
  }

  const keys = document.createElement("div");
  keys.className = "keys";
  for (let i = 0; i < model.key_count; i += 1) {
    const button = (page.buttons || [])[i];
    const key = document.createElement("div");
    key.className = "key";
    if (!button || button.special_type === "empty") key.classList.add("empty");
    if (isSelected("button", i)) key.classList.add("selected");
    key.draggable = true;
    key.dataset.index = String(i);
    renderKeyFace(key, button);
    key.addEventListener("click", () => {
      state.selected = { kind: "button", index: i };
      render();
    });
    key.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", String(i));
    });
    key.addEventListener("dragover", (event) => {
      event.preventDefault();
      key.classList.add("drag-over");
    });
    key.addEventListener("dragleave", () => key.classList.remove("drag-over"));
    key.addEventListener("drop", (event) => {
      event.preventDefault();
      key.classList.remove("drag-over");
      const from = Number(event.dataTransfer.getData("text/plain"));
      moveButton(from, i);
    });
    keys.append(key);
  }
  device.append(keys);

  if (model.has_touchscreen) {
    const slots = physicalDials(page, model.dial_count);
    const strip = document.createElement("div");
    strip.className = "touch-strip";
    slots.forEach((slot, index) => {
      const visual = slot.turn || slot.push;
      const cell = document.createElement("div");
      cell.className = "strip-cell";
      if (isSelected("strip", index)) cell.classList.add("selected");
      const iconName = previewIcon(visual);
      if (iconName) {
        const icon = document.createElement("span");
        icon.className = `mdi mdi-${iconName}`;
        cell.append(icon);
      }
      const label = document.createElement("span");
      label.className = "strip-label";
      label.textContent = displayText(visual) || `Dial ${index + 1}`;
      cell.append(label);
      cell.addEventListener("click", () => {
        state.selected = { kind: "strip", index, event: slot.turn ? "TURN" : "PUSH" };
        render();
      });
      strip.append(cell);
    });
    device.append(strip);

    const dials = document.createElement("div");
    dials.className = "dials";
    slots.forEach((slot, index) => {
      const knob = document.createElement("div");
      knob.className = "dial";
      if (isSelected("dial", index)) knob.classList.add("selected");
      const cap = document.createElement("div");
      cap.className = "dial-cap";
      knob.append(cap);
      knob.title = slot.turn || slot.push ? "Dial" : "Empty dial";
      knob.addEventListener("click", () => {
        state.selected = { kind: "dial", index, event: slot.turn ? "TURN" : "PUSH" };
        render();
      });
      dials.append(knob);
    });
    device.append(dials);
  }

  if (model.touch_key_count) {
    const row = document.createElement("div");
    row.className = "neo-touches";
    for (let i = 0; i < model.touch_key_count; i += 1) {
      const touch = document.createElement("div");
      touch.className = "neo-touch";
      touch.title = "Neo touch key — not in streamdeck.yaml";
      row.append(touch);
    }
    device.append(row);
  }

  document.getElementById("device-caption").textContent = model.notes || model.name;
}

function field(label, control) {
  const wrap = document.createElement("label");
  wrap.append(label, control);
  return wrap;
}

function textInput(value, onChange, placeholder = "") {
  const input = document.createElement("input");
  input.type = "text";
  input.value = value ?? "";
  input.placeholder = placeholder;
  input.addEventListener("change", () => onChange(input.value));
  return input;
}

function colorInput(value, onChange) {
  const wrap = document.createElement("div");
  wrap.className = "color-row";
  const text = textInput(value || "", onChange, "#000000 or amber");
  const picker = document.createElement("input");
  picker.type = "color";
  picker.value = /^#[0-9a-fA-F]{6}$/.test(value || "") ? value : "#ffffff";
  picker.addEventListener("input", () => {
    text.value = picker.value;
    onChange(picker.value);
  });
  wrap.append(text, picker);
  return wrap;
}

function selectInput(value, options, onChange) {
  const select = document.createElement("select");
  options.forEach((option) => {
    const el = document.createElement("option");
    if (typeof option === "string") {
      el.value = option;
      el.textContent = option;
    } else {
      el.value = option.value;
      el.textContent = option.label;
    }
    select.append(el);
  });
  select.value = value ?? "";
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function writeButton(index, button) {
  const page = currentPage();
  page.buttons = page.buttons ? page.buttons.slice() : [];
  while (page.buttons.length <= index) page.buttons.push(emptyButton());
  page.buttons[index] = button;
}

function selectedButton() {
  if (!state.selected || state.selected.kind !== "button") return null;
  const buttons = currentPage().buttons || [];
  return buttons[state.selected.index] || emptyButton();
}

function selectedDialSlot() {
  if (!state.selected || !["dial", "strip"].includes(state.selected.kind)) return null;
  const page = currentPage();
  const slots = physicalDials(page, currentModel().dial_count || 4);
  return { page, slots, slot: slots[state.selected.index], index: state.selected.index };
}

function patchButton(patch) {
  const index = state.selected.index;
  const next = { ...selectedButton(), ...patch };
  if (patch.special_type && ["next-page", "previous-page", "empty", "turn-off"].includes(patch.special_type)) {
    delete next.special_type_data;
  }
  writeButton(index, next);
  markDirty();
  render();
}

function patchDial(patch) {
  const ctx = selectedDialSlot();
  if (!ctx) return;
  const event = state.selected.event || "TURN";
  const key = event === "PUSH" ? "push" : "turn";
  ctx.slot[key] = { ...(ctx.slot[key] || { dial_event_type: event }), ...patch, dial_event_type: event };
  writePhysicalDials(ctx.page, ctx.slots);
  markDirty();
  render();
}

function moveButton(from, to) {
  if (from === to) return;
  const page = currentPage();
  const count = Math.max(from, to, currentModel().key_count - 1) + 1;
  page.buttons = page.buttons ? page.buttons.slice() : [];
  while (page.buttons.length < count) page.buttons.push(emptyButton());
  const [moved] = page.buttons.splice(from, 1);
  page.buttons.splice(to, 0, moved);
  state.selected = { kind: "button", index: to };
  markDirty();
  render();
}

const COMMON_DOMAINS = [
  "light",
  "switch",
  "scene",
  "script",
  "media_player",
  "cover",
  "climate",
  "fan",
  "lock",
  "input_boolean",
  "input_number",
  "input_select",
  "automation",
  "button",
  "vacuum",
  "siren",
  "timer",
];

async function refreshEntities() {
  const result = await api("/api/ha/refresh", { method: "POST" });
  const listed = await api("/api/ha/entities");
  state.entities = listed.entities || [];
  return result;
}

function entityPicker(value, onPick) {
  const wrap = document.createElement("div");
  wrap.className = "entity-picker";
  const currentDomain = (value || "").split(".")[0] || "";
  const domain = document.createElement("select");
  const search = textInput("", () => {}, "Search by name, e.g. kitchen");
  search.placeholder = "Search by name, e.g. kitchen";
  const results = document.createElement("div");
  results.className = "entity-results";
  const meta = document.createElement("p");
  meta.className = "hint entity-meta";

  const domains = [...new Set([...COMMON_DOMAINS, ...state.entities.map((entity) => entity.domain)])]
    .filter(Boolean)
    .sort((a, b) => {
      const ai = COMMON_DOMAINS.indexOf(a);
      const bi = COMMON_DOMAINS.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  [["", `All domains (${state.entities.length})`], ...domains.map((name) => [name, name])].forEach(([id, label]) => {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = label;
    domain.append(option);
  });
  domain.value = domains.includes(currentDomain) ? currentDomain : "";

  const draw = () => {
    results.innerHTML = "";
    const query = search.value.trim().toLowerCase();
    const selectedDomain = domain.value;
    const matches = state.entities.filter((entity) => {
      if (selectedDomain && entity.domain !== selectedDomain) return false;
      if (!query) return true;
      return `${entity.friendly_name} ${entity.entity_id} ${entity.domain}`.toLowerCase().includes(query);
    });
    meta.textContent = state.entities.length
      ? `${matches.length} device${matches.length === 1 ? "" : "s"} — click one to assign it`
      : "";
    matches.slice(0, 120).forEach((entity) => {
      const btn = document.createElement("button");
      btn.type = "button";
      if (entity.entity_id === value) btn.classList.add("active");
      const title = document.createElement("strong");
      title.textContent = entity.friendly_name;
      const detail = document.createElement("small");
      detail.textContent = `${entity.entity_id} · ${entity.state}`;
      btn.append(title, detail);
      btn.addEventListener("click", async () => {
        onPick(entity.entity_id);
        const hint = await api(`/api/ha/suggest-service?entity_id=${encodeURIComponent(entity.entity_id)}`);
        if (hint.service && state.selected?.kind === "button") patchButton({ service: hint.service });
        if (hint.service && ["dial", "strip"].includes(state.selected?.kind)) patchDial({ service: hint.service });
      });
      results.append(btn);
    });
    if (!state.entities.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = state.settings?.ha_token_set
        ? "No devices loaded yet. Fetch them from Home Assistant."
        : "Add your Home Assistant URL and token in Settings, then fetch devices.";
      const fetchBtn = document.createElement("button");
      fetchBtn.type = "button";
      fetchBtn.className = "fetch-devices";
      fetchBtn.textContent = "Fetch devices";
      fetchBtn.addEventListener("click", async () => {
        try {
          const result = await refreshEntities();
          flash(`${result.entity_count} devices loaded`);
          render();
        } catch (error) {
          flash(error.message, true);
        }
      });
      results.append(empty, fetchBtn);
    }
  };

  domain.addEventListener("change", draw);
  search.addEventListener("input", draw);
  search.addEventListener("change", () => {
    const raw = search.value.trim();
    if (raw.includes(".") && !raw.includes(" ")) onPick(raw);
  });
  wrap.append(domain, search, meta, results);
  draw();
  return wrap;
}

function customIconPreview(icon) {
  if (!icon || icon.includes("{")) return "";
  if (icon.startsWith("url:") || icon.startsWith("ring:") || icon.startsWith("spotify:")) return "";
  const name = icon.split(/[/\\]/).pop();
  if (!name || !/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(name)) return "";
  return `/api/assets/${encodeURIComponent(name)}`;
}

function customIconPicker(value, onPick) {
  const wrap = document.createElement("div");
  const input = textInput(value || "", onPick, "filename.png, /absolute/path, url:, or ring:50");
  const row = document.createElement("div");
  row.className = "row";
  const upload = document.createElement("input");
  upload.type = "file";
  upload.accept = "image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.bmp";
  upload.addEventListener("change", async () => {
    if (!upload.files?.[0]) return;
    const body = new FormData();
    body.append("file", upload.files[0]);
    try {
      const response = await fetch("/api/assets", { method: "POST", body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        flash(data.detail || "Upload failed", true);
        return;
      }
      input.value = data.path;
      onPick(data.path);
      await drawLibrary();
    } catch (error) {
      flash(error.message, true);
    }
  });
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = state.settings?.resolved_assets_dir
    ? `Uploads go to ${state.settings.resolved_assets_dir}. The YAML stores an absolute path so the Stream Deck service can load the file.`
    : "Set the YAML path or an assets directory in Settings before uploading.";
  const library = document.createElement("div");
  library.className = "asset-thumbs";
  async function drawLibrary() {
    library.innerHTML = "";
    try {
      const listed = await api("/api/assets");
      listed.items.forEach((item) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.title = item.name;
        btn.innerHTML = `<img src="${item.preview}" alt=""><span>${item.name}</span>`;
        btn.addEventListener("click", () => {
          input.value = item.path;
          onPick(item.path);
        });
        library.append(btn);
      });
    } catch {
      library.innerHTML = "";
    }
  }
  row.append(upload);
  wrap.append(input, row, hint, library);
  drawLibrary();
  return wrap;
}

function iconPicker(value, onPick) {
  const wrap = document.createElement("div");
  const search = textInput(value || "", onPick, "lightbulb");
  const grid = document.createElement("div");
  grid.className = "picker";
  const draw = (query) => {
    grid.innerHTML = "";
    ICONS.filter((name) => !query || name.includes(query.toLowerCase())).forEach((name) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.title = name;
      btn.innerHTML = `<span class="mdi mdi-${name}"></span>`;
      btn.addEventListener("click", () => {
        search.value = name;
        onPick(name);
      });
      grid.append(btn);
    });
  };
  search.addEventListener("input", () => draw(search.value));
  wrap.append(search, grid);
  draw(value || "");
  return wrap;
}

function renderInspector() {
  const root = document.getElementById("inspector");
  root.innerHTML = "";
  if (!state.selected) {
    root.innerHTML = `<p class="empty-inspector">Select a key, dial, or touch-strip segment.</p>`;
    return;
  }

  if (state.selected.kind === "button") {
    const button = selectedButton() || emptyButton();
    const title = document.createElement("h3");
    title.textContent = `Key ${state.selected.index + 1}`;
    const type = selectInput(
      button.special_type || "",
      [{ value: "", label: "Normal button" }, ...((state.schema?.special_types || []).map((v) => ({ value: v, label: v })))],
      (value) => {
        const patch = { special_type: value || null };
        if (value === "go-to-page") patch.special_type_data = allPageNames()[0] || "Home";
        if (value === "light-control") patch.special_type_data = button.special_type_data || {};
        patchButton(patch);
      },
    );
    root.append(title, field("Type", type));

    if (button.special_type === "go-to-page") {
      const pages = allPageNames().map((name, index) => ({ value: name, label: `${name} (#${index})` }));
      root.append(
        field(
          "Go to page",
          selectInput(String(button.special_type_data ?? ""), pages, (value) => patchButton({ special_type_data: value })),
        ),
      );
    }
    if (button.special_type === "light-control") {
      const data = button.special_type_data || {};
      root.append(
        field(
          "Colormap",
          textInput(data.colormap || "", (value) => patchButton({ special_type_data: { ...data, colormap: value || undefined } }), "hsv"),
        ),
      );
    }

    root.append(
      field("Entity", entityPicker(button.entity_id, (value) => patchButton({ entity_id: value || null }))),
      field("Service", textInput(button.service || "", (value) => patchButton({ service: value || null }), "light.toggle")),
      field("Text", textInput(button.text || "", (value) => patchButton({ text: value || null }))),
      field("Text color", colorInput(button.text_color, (value) => patchButton({ text_color: value || null }))),
      field("MDI icon", iconPicker(button.icon_mdi, (value) => patchButton({ icon_mdi: value || null }))),
      field("Custom icon", customIconPicker(button.icon || "", (value) => patchButton({ icon: value || null }))),
      field("Icon color", colorInput(button.icon_mdi_color, (value) => patchButton({ icon_mdi_color: value || null }))),
      field("Background", colorInput(button.icon_background_color || "#000000", (value) => patchButton({ icon_background_color: value }))),
    );
    const clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Clear key";
    clear.addEventListener("click", () => {
      writeButton(state.selected.index, emptyButton());
      markDirty();
      render();
    });
    root.append(clear);
    return;
  }

  const ctx = selectedDialSlot();
  const event = state.selected.event || "TURN";
  const dial = (event === "PUSH" ? ctx?.slot.push : ctx?.slot.turn) || { dial_event_type: event };
  const title = document.createElement("h3");
  title.textContent = state.selected.kind === "strip" ? `Touch strip ${state.selected.index + 1}` : `Dial ${state.selected.index + 1}`;
  const tabs = document.createElement("div");
  tabs.className = "tabs";
  ["TURN", "PUSH"].forEach((kind) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = kind === "TURN" ? "Rotate" : "Press";
    if (event === kind) btn.classList.add("active");
    btn.addEventListener("click", () => {
      state.selected = { ...state.selected, event: kind };
      render();
    });
    tabs.append(btn);
  });
  root.append(title, tabs);
  if (state.selected.kind === "strip") {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "The strip is the LCD above the dials, not a separate YAML object. Each segment shows that dial.";
    root.append(note);
  }
  root.append(
    field("Entity", entityPicker(dial.entity_id, (value) => patchDial({ entity_id: value || null }))),
    field("Service", textInput(dial.service || "", (value) => patchDial({ service: value || null }))),
    field("State attribute", textInput(dial.state_attribute || "", (value) => patchDial({ state_attribute: value || null }), "brightness")),
    field("Text", textInput(dial.text || "", (value) => patchDial({ text: value || null }))),
    field("MDI icon", iconPicker(dial.icon_mdi, (value) => patchDial({ icon_mdi: value || null }))),
    field("Custom icon / ring:", customIconPicker(dial.icon || "", (value) => patchDial({ icon: value || null }))),
    field("Background", colorInput(dial.icon_background_color || "#000000", (value) => patchDial({ icon_background_color: value }))),
  );
  const allow = document.createElement("label");
  const check = document.createElement("input");
  check.type = "checkbox";
  check.checked = Boolean(dial.allow_touchscreen_events);
  check.addEventListener("change", () => patchDial({ allow_touchscreen_events: check.checked }));
  allow.append(check, " Allow touch-strip tap/hold (min/max)");
  root.append(allow);
}

function renderIssues() {
  const el = document.getElementById("issues");
  if (!state.issues.length) {
    el.hidden = true;
    return;
  }
  const hard = state.issues.some((issue) => issue.severity === "error");
  el.hidden = false;
  el.className = `issues${hard ? " error" : ""}`;
  el.textContent = state.issues.map((issue) => issue.message).join(" · ");
}

function render() {
  renderPages();
  renderDevice();
  renderInspector();
  renderIssues();
}

function markDirty() {
  state.dirty = true;
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  const select = document.getElementById("deck-model");
  select.innerHTML = "";
  state.models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.name} (${model.key_count} keys${model.dial_count ? ` + ${model.dial_count} dials` : ""})`;
    select.append(option);
  });
  select.value = state.settings.deck_model || "plus";
}

async function openFile() {
  const data = await api("/api/config");
  state.config = data.config;
  state.yamlText = data.yaml_text;
  state.hasIncludes = data.has_includes;
  state.issues = data.issues;
  state.pageKind = "pages";
  state.pageIndex = 0;
  state.selected = null;
  state.dirty = false;
  render();
}

async function saveFile() {
  try {
    const result = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({ config: state.config }),
    });
    state.issues = result.issues;
    state.dirty = false;
    render();
    const deck = await refreshDeckStatus();
    flash(deck.running ? "Saved. The Stream Deck will reload the file." : "Saved the YAML, but the Stream Deck service is not running. Open Settings and click Apply to Stream Deck.");
  } catch (error) {
    flash(error.message, true);
  }
}

function flash(message, err = false) {
  const el = document.getElementById("issues");
  el.hidden = false;
  el.className = `issues${err ? " error" : ""}`;
  el.textContent = message;
}

async function loadSample() {
  const data = await api("/api/sample");
  state.config = data.config;
  state.yamlText = data.yaml_text;
  state.pageKind = "pages";
  state.pageIndex = 0;
  state.selected = null;
  state.settings.deck_model = "plus";
  document.getElementById("deck-model").value = "plus";
  await api("/api/settings", { method: "PUT", body: JSON.stringify({ deck_model: "plus" }) });
  markDirty();
  render();
}

function fillSettingsForm() {
  const form = document.getElementById("settings-form");
  form.streamdeck_yaml_path.value = state.settings.streamdeck_yaml_path || "";
  form.ha_url.value = state.settings.ha_url || "";
  form.ha_token.value = "";
  form.ha_token.placeholder = state.settings.ha_token_set ? "Token is set — leave blank to keep" : "Long-lived access token";
  form.backup_count.value = state.settings.backup_count;
  form.assets_dir.value = state.settings.assets_dir || "";
}

async function refreshDeckStatus() {
  const el = document.getElementById("deck-status");
  try {
    const status = await api("/api/service/status");
    if (status.running) {
      el.className = "status ok";
      el.textContent = "Deck: running";
    } else {
      el.className = "status err";
      el.textContent = "Deck: not running";
    }
    return status;
  } catch {
    el.className = "status muted";
    el.textContent = "Deck: unknown";
    return { running: false };
  }
}

async function init() {
  state.models = await api("/api/deck-models");
  state.schema = await api("/api/schema");
  await loadSettings();
  try {
    const entities = await api("/api/ha/entities");
    state.entities = entities.entities || [];
    if (!state.entities.length && state.settings?.ha_token_set) {
      await refreshEntities();
    }
  } catch {
    state.entities = [];
  }
  await refreshDeckStatus();
  try {
    await openFile();
  } catch {
    state.config = (await api("/api/sample")).config;
    state.settings.deck_model = state.settings.deck_model || "plus";
    render();
  }

  document.getElementById("deck-model").addEventListener("change", async (event) => {
    state.settings.deck_model = event.target.value;
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ deck_model: event.target.value }) });
    state.selected = null;
    render();
  });
  document.getElementById("btn-add-page").addEventListener("click", () => {
    state.config.pages.push({ name: `Page ${state.config.pages.length + 1}`, buttons: [], dials: [] });
    state.pageKind = "pages";
    state.pageIndex = state.config.pages.length - 1;
    markDirty();
    render();
  });
  document.getElementById("btn-add-anon").addEventListener("click", () => {
    state.config.anonymous_pages = state.config.anonymous_pages || [];
    state.config.anonymous_pages.push({ name: `anon-${state.config.anonymous_pages.length + 1}`, buttons: [], dials: [] });
    state.pageKind = "anonymous_pages";
    state.pageIndex = state.config.anonymous_pages.length - 1;
    markDirty();
    render();
  });
  document.getElementById("btn-reload").addEventListener("click", () => openFile().catch((error) => flash(error.message, true)));
  document.getElementById("btn-save").addEventListener("click", saveFile);
  document.getElementById("btn-sample").addEventListener("click", loadSample);
  document.getElementById("btn-settings").addEventListener("click", () => {
    fillSettingsForm();
    document.getElementById("settings-dialog").showModal();
  });
  document.getElementById("btn-settings-cancel").addEventListener("click", () => document.getElementById("settings-dialog").close());
  document.getElementById("settings-form").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    const form = event.target;
    const payload = {
      streamdeck_yaml_path: form.streamdeck_yaml_path.value,
      ha_url: form.ha_url.value,
      backup_count: Number(form.backup_count.value),
      assets_dir: form.assets_dir.value,
    };
    if (form.ha_token.value) payload.ha_token = form.ha_token.value;
    state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    document.getElementById("settings-dialog").close();
  });
  document.getElementById("btn-ha-test").addEventListener("click", async () => {
    const status = document.getElementById("ha-status");
    try {
      const form = document.getElementById("settings-form");
      if (form.ha_url.value || form.ha_token.value) {
        await api("/api/settings", {
          method: "PUT",
          body: JSON.stringify({
            ha_url: form.ha_url.value,
            ha_token: form.ha_token.value || undefined,
          }),
        });
      }
      const result = await api("/api/ha/test", { method: "POST" });
      status.className = "status ok";
      const version = result.websocket?.ha_version ? ` HA ${result.websocket.ha_version}` : "";
      status.textContent = `REST and websocket OK${version}`;
    } catch (error) {
      status.className = "status err";
      status.textContent = error.message;
    }
  });
  document.getElementById("btn-deck-apply").addEventListener("click", async () => {
    const status = document.getElementById("ha-status");
    try {
      const form = document.getElementById("settings-form");
      const payload = {
        streamdeck_yaml_path: form.streamdeck_yaml_path.value,
        ha_url: form.ha_url.value,
        backup_count: Number(form.backup_count.value),
        assets_dir: form.assets_dir.value,
      };
      if (form.ha_token.value) payload.ha_token = form.ha_token.value;
      state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      status.className = "status";
      status.textContent = "Applying…";
      const result = await api("/api/service/apply", { method: "POST" });
      await refreshDeckStatus();
      status.className = result.running ? "status ok" : "status err";
      status.textContent = result.running
        ? "Stream Deck service is running. Save in the editor to update keys."
        : (result.note || "Service did not stay running. Check the Pi logs.");
    } catch (error) {
      status.className = "status err";
      status.textContent = error.message;
    }
  });
  document.getElementById("btn-ha-refresh").addEventListener("click", async () => {
    const status = document.getElementById("ha-status");
    try {
      const result = await refreshEntities();
      status.className = "status ok";
      status.textContent = `${result.entity_count} devices`;
      render();
    } catch (error) {
      status.className = "status err";
      status.textContent = error.message;
    }
  });
  document.getElementById("btn-yaml").addEventListener("click", async () => {
    document.getElementById("yaml-note").textContent = state.hasIncludes
      ? "This file uses !include. Saving from the editor writes a single file only if you choose a new path or allow inlining."
      : "Hand-edits here can be applied back to the visual editor.";
    document.getElementById("yaml-text").value = state.yamlText || JSON.stringify(state.config, null, 2);
    document.getElementById("yaml-diff").hidden = true;
    document.getElementById("yaml-dialog").showModal();
  });
  document.getElementById("btn-apply-yaml").addEventListener("click", async () => {
    const yamlText = document.getElementById("yaml-text").value;
    const result = await api("/api/config/validate", { method: "POST", body: JSON.stringify({ yaml_text: yamlText }) });
    if (!result.ok) {
      flash(JSON.stringify(result.errors || result.issues), true);
      return;
    }
    state.config = result.config;
    state.yamlText = yamlText;
    state.issues = result.issues;
    markDirty();
    render();
    document.getElementById("yaml-dialog").close();
  });
  document.getElementById("btn-diff").addEventListener("click", async () => {
    const diff = await api("/api/config/diff", { method: "POST", body: JSON.stringify({ config: state.config }) });
    const pre = document.getElementById("yaml-diff");
    pre.hidden = false;
    pre.textContent = diff.diff || "(no changes)";
  });
}

init().catch((error) => flash(error.message, true));
