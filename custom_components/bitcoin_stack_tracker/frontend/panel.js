const FRONTEND_BUILD = "0.21.0.15";
const FRONTEND_CACHE_REVISION = "10";
const RPC_SOURCE = "bitcoin-stack-tracker-native";
const PANEL_BUILD_TOKEN = FRONTEND_BUILD.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const PANEL_CACHE_TOKEN = FRONTEND_CACHE_REVISION.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const PANEL_ELEMENT = `bitcoin-stack-tracker-panel-${PANEL_BUILD_TOKEN}-r${PANEL_CACHE_TOKEN}`;

const NATIVE_QR_BRIDGE_KEY = "__BITCOIN_STACK_TRACKER_NATIVE_QR_BRIDGE_RC19__";
let nativeQrMessageSeq = 0;

function nextNativeQrMessageId() {
  nativeQrMessageSeq = (nativeQrMessageSeq + 1) % 100000000;
  return 1900000000 + nativeQrMessageSeq;
}

function nativeExternalBusSend(message) {
  const serialized = JSON.stringify(message);
  try {
    if (window.externalAppV2 && typeof window.externalAppV2.postMessage === "function") {
      window.externalAppV2.postMessage(serialized);
      return true;
    }
  } catch (_error) {}
  try {
    if (window.externalApp && typeof window.externalApp.externalBus === "function") {
      window.externalApp.externalBus(serialized);
      return true;
    }
  } catch (_error) {}
  try {
    if (window.webkit?.messageHandlers?.externalBus?.postMessage) {
      window.webkit.messageHandlers.externalBus.postMessage(serialized);
      return true;
    }
  } catch (_error) {}
  return false;
}

function ensureNativeQrBusBridge() {
  const existing = window[NATIVE_QR_BRIDGE_KEY];
  if (existing?.wrapper && window.externalBus === existing.wrapper) {
    if (!(existing.typeListeners instanceof Set)) existing.typeListeners = new Set();
    return existing;
  }

  const current = window.externalBus;
  if (typeof current !== "function") return null;
  const bridge = existing || { listeners: new Map(), typeListeners: new Set(), original: null, wrapper: null };
  // If another BST panel build left its wrapper behind, delegate through it.
  // Otherwise preserve Home Assistant's original external-bus handler.
  if (!(bridge.typeListeners instanceof Set)) bridge.typeListeners = new Set();
  bridge.original = current;
  bridge.wrapper = function bitcoinStackTrackerExternalBusBridge(message) {
    let parsed = null;
    try { parsed = typeof message === "string" ? JSON.parse(message) : message; } catch (_error) {}
    let originalResult;
    try { originalResult = bridge.original.apply(this, arguments); } catch (_error) {}
    if (parsed && Number.isInteger(parsed.id)) {
      const listener = bridge.listeners.get(parsed.id);
      if (listener) {
        try { listener(parsed); } catch (_error) {}
      }
    }
    if (parsed && bridge.typeListeners instanceof Set) {
      for (const listener of [...bridge.typeListeners]) {
        try { listener(parsed); } catch (_error) {}
      }
    }
    return originalResult;
  };
  try {
    window.externalBus = bridge.wrapper;
  } catch (_error) {
    return null;
  }
  window[NATIVE_QR_BRIDGE_KEY] = bridge;
  return bridge;
}

function panelErrorText(error) {
  const candidate = error?.message ?? error?.body?.message ?? error?.body ?? error;
  if (typeof candidate === "string") return candidate;
  if (candidate && typeof candidate === "object") {
    for (const key of ["message", "error", "detail", "text"]) {
      if (typeof candidate[key] === "string" && candidate[key]) return candidate[key];
    }
    try { return JSON.stringify(candidate); } catch (_error) {}
  }
  return String(candidate ?? "Unknown Home Assistant Core error");
}

class BitcoinStackTrackerPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._panel = null;
    this._frame = null;
    this._qrOverlay = null;
    this._onMessage = this._onMessage.bind(this);
    this._openHomeAssistantMenu = this._openHomeAssistantMenu.bind(this);
    this.attachShadow({ mode: "open" });
  }

  set hass(value) {
    this._hass = value;
    this._render();
  }
  get hass() { return this._hass; }

  set panel(value) {
    this._panel = value;
    this._render();
  }
  get panel() { return this._panel; }

  set narrow(_value) {}

  connectedCallback() {
    window.addEventListener("message", this._onMessage);
    this._render();
  }

  disconnectedCallback() {
    window.removeEventListener("message", this._onMessage);
  }

  _openHomeAssistantMenu() {
    // Home Assistant's custom-panel host listens for this exact event on the
    // panel element and forwards it to the main frontend. Keep the menu action
    // inside the supported panel event path instead of reaching through HA's
    // private shadow DOM or Companion internals.
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", {
      bubbles: true,
      composed: true,
    }));
  }

  _render() {
    if (this._frame || !this.shadowRoot) return;
    const src = this._panel?.config?.frontend_url || "/api/bitcoin_stack_tracker/frontend/index.html?native=1";
    const style = document.createElement("style");
    style.textContent = `
      :host{display:block;width:100%;height:100vh;min-height:100vh;background:#090a0d;color:var(--primary-text-color,#fff)}
      .panel-shell{display:grid;grid-template-rows:minmax(0,1fr);width:100%;height:100vh;min-height:0;background:#090a0d}
      .ha-mobile-bar{display:none;box-sizing:border-box;align-items:center;gap:8px;height:calc(56px + var(--safe-area-inset-top,0px));padding:var(--safe-area-inset-top,0px) 10px 0;background:var(--app-header-background-color,var(--primary-background-color,#111318));color:var(--app-header-text-color,var(--primary-text-color,#fff));border-bottom:1px solid var(--divider-color,rgba(255,255,255,.12));z-index:2}
      .ha-menu-button{display:grid;place-items:center;width:48px;height:48px;flex:0 0 48px;margin:0;padding:0;border:0;border-radius:50%;background:transparent;color:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}
      .ha-menu-button:active{background:color-mix(in srgb,currentColor 12%,transparent)}
      .ha-menu-button:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:-4px}
      .ha-menu-button svg{width:24px;height:24px;fill:currentColor}
      .ha-bar-logo{width:34px;height:34px;object-fit:contain;border-radius:7px;flex:0 0 34px}
      .ha-bar-title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:500 20px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      iframe{display:block;border:0;width:100%;height:100%;min-height:0;background:#090a0d}
      @media(max-width:870px){
        :host{overflow:hidden}
        .panel-shell{grid-template-rows:auto minmax(0,1fr);width:100vw;max-width:100vw;overflow:hidden}
        .ha-mobile-bar{display:flex}
        .ha-mobile-bar{contain:layout paint}
        iframe{width:100vw;max-width:100vw;contain:paint;transform:translateZ(0);backface-visibility:hidden}
      }
    `;

    const shell = document.createElement("div");
    shell.className = "panel-shell";

    const toolbar = document.createElement("div");
    toolbar.className = "ha-mobile-bar";
    toolbar.setAttribute("role", "banner");

    const menu = document.createElement("button");
    menu.className = "ha-menu-button";
    menu.type = "button";
    menu.title = "Home-Assistant-Menü öffnen";
    menu.setAttribute("aria-label", "Home-Assistant-Menü öffnen");
    menu.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18v2H3V6zm0 5h18v2H3v-2zm0 5h18v2H3v-2z"/></svg>';
    menu.addEventListener("click", this._openHomeAssistantMenu);

    const logo = document.createElement("img");
    logo.className = "ha-bar-logo";
    logo.src = "/api/bitcoin_stack_tracker/frontend/static/assets/bitcoin-stack-tracker-logo.png";
    logo.alt = "";
    logo.setAttribute("aria-hidden", "true");

    const title = document.createElement("div");
    title.className = "ha-bar-title";
    title.textContent = "Bitcoin Stack Tracker";

    toolbar.append(menu, logo, title);

    const frame = document.createElement("iframe");
    frame.title = "Bitcoin Stack Tracker";
    let frameSrc = src;
    try {
      const frameUrl = new URL(src, window.location.origin);
      // Never trust a panel config object that may have survived an in-place
      // Home Assistant frontend update. Force the iframe to this module build.
      frameUrl.searchParams.set("v", FRONTEND_BUILD);
      frameUrl.searchParams.set("r", FRONTEND_CACHE_REVISION);
      frameUrl.searchParams.set("panel_build", `${FRONTEND_BUILD}-r${FRONTEND_CACHE_REVISION}`);
      frameSrc = frameUrl.toString();
    } catch (_error) {}
    frame.src = frameSrc;
    frame.dataset.frontendBuild = FRONTEND_BUILD;
    frame.referrerPolicy = "no-referrer";
    frame.setAttribute("allow", "camera; clipboard-write");

    shell.append(toolbar, frame);
    this.shadowRoot.append(style, shell);
    this._frame = frame;
  }

  _postUiEvent(id, action, payload = {}) {
    if (!this._frame?.contentWindow) return;
    this._frame.contentWindow.postMessage({
      source: RPC_SOURCE,
      type: "ui-event",
      id,
      action,
      ...payload,
    }, window.location.origin);
  }

  _closeHaQrScanner() {
    if (this._qrOverlay) {
      this._qrOverlay.remove();
      this._qrOverlay = null;
    }
  }

  _nativeExternalBusRequest(message, timeoutMs = 1200) {
    const bridge = ensureNativeQrBusBridge();
    if (!bridge) return Promise.resolve(null);
    return new Promise((resolve) => {
      let done = false;
      const finish = (value) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        bridge.listeners.delete(message.id);
        resolve(value);
      };
      bridge.listeners.set(message.id, finish);
      const timer = setTimeout(() => finish(null), timeoutMs);
      if (!nativeExternalBusSend(message)) finish(null);
    });
  }

  async _nativeBarcodeScannerAvailable() {
    if (!ensureNativeQrBusBridge()) return false;
    const id = nextNativeQrMessageId();
    const response = await this._nativeExternalBusRequest({ id, type: "config/get" }, 1400);
    return Boolean(
      response?.type === "result" &&
      response?.success === true &&
      Number(response?.result?.hasBarCodeScanner || 0) > 0
    );
  }

  async _openNativeQrScanner(requestId) {
    if (!(await this._nativeBarcodeScannerAvailable())) return false;
    const bridge = ensureNativeQrBusBridge();
    if (!bridge) return false;
    const id = nextNativeQrMessageId();
    let finished = false;
    let timer = null;
    let onBusMessage = null;
    const cleanup = () => {
      if (onBusMessage) bridge.typeListeners.delete(onBusMessage);
      if (timer !== null) clearTimeout(timer);
    };
    const finish = (state, value = "") => {
      if (finished) return;
      finished = true;
      cleanup();
      if (state === "result") {
        nativeExternalBusSend({ id: nextNativeQrMessageId(), type: "bar_code/close" });
      }
      this._postUiEvent(requestId, "qr-scan-state", { state, value });
    };
    // bar_code/scan itself does not have a result response. The Companion app
    // later emits a new app->frontend bar_code/scan_result (or aborted) action
    // with its own message id, so matching the original scan id loses valid QR
    // results. Listen by message type and let HA's original externalBus handler
    // still process/acknowledge the action.
    onBusMessage = (message) => {
      if (message?.type === "bar_code/scan_result") {
        finish("result", String(message?.payload?.rawValue || ""));
      } else if (message?.type === "bar_code/aborted") {
        finish("canceled");
      }
    };
    bridge.typeListeners.add(onBusMessage);
    timer = setTimeout(() => finish("canceled"), 120000);
    const sent = nativeExternalBusSend({
      id,
      type: "bar_code/scan",
      payload: {
        title: "Bitcoin Stack Tracker",
        description: "Bitcoin-Adresse, XPUB oder Descriptor scannen",
      },
    });
    if (!sent) {
      cleanup();
      return false;
    }
    this._postUiEvent(requestId, "qr-scan-state", { state: "started" });
    return true;
  }

  _openHaQrScanner(requestId) {
    // Secondary browser fallback for Home Assistant frontends that happen to
    // have this component loaded. The official Companion path above is the
    // external bus (bar_code/scan).
    if (!customElements.get("ha-qr-scanner")) return false;
    this._closeHaQrScanner();
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.78);display:grid;place-items:center;padding:16px;box-sizing:border-box";
    const card = document.createElement("div");
    card.style.cssText = "width:min(94vw,560px);max-height:94vh;overflow:auto;background:var(--card-background-color,#111318);color:var(--primary-text-color,#fff);border:1px solid var(--divider-color,rgba(255,255,255,.14));border-radius:18px;padding:16px;box-sizing:border-box";
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Schließen";
    close.style.cssText = "float:right;margin:0 0 10px 10px;padding:8px 12px;border-radius:10px;border:1px solid var(--divider-color,rgba(255,255,255,.18));background:transparent;color:inherit";
    const scanner = document.createElement("ha-qr-scanner");
    scanner.description = "Bitcoin-Adresse, XPUB oder Descriptor scannen";
    const finish = (state, value = "") => {
      this._closeHaQrScanner();
      this._postUiEvent(requestId, "qr-scan-state", { state, value });
    };
    close.addEventListener("click", () => finish("canceled"));
    overlay.addEventListener("click", (event) => { if (event.target === overlay) finish("canceled"); });
    scanner.addEventListener("qr-code-scanned", (event) => finish("result", String(event?.detail?.value || "")));
    scanner.addEventListener("qr-code-closed", () => finish("canceled"));
    scanner.addEventListener("qr-code-more-options", () => finish("canceled"));
    card.append(close, scanner);
    overlay.append(card);
    this.shadowRoot.append(overlay);
    this._qrOverlay = overlay;
    this._postUiEvent(requestId, "qr-scan-state", { state: "started" });
    return true;
  }

  async _onMessage(event) {
    if (!this._frame || event.source !== this._frame.contentWindow) return;
    if (event.origin !== window.location.origin) return;
    const message = event.data;
    if (!message || message.source !== RPC_SOURCE) return;

    if (message.type === "ui-action" && message.action === "open-menu") {
      this._openHomeAssistantMenu();
      return;
    }
    if (message.type === "ui-action" && message.action === "scan-qr" && message.id) {
      this._postUiEvent(message.id, "qr-scan-state", { state: "probing" });
      if (await this._openNativeQrScanner(message.id)) return;
      if (this._openHaQrScanner(message.id)) return;
      this._postUiEvent(message.id, "qr-scan-state", { state: "unsupported" });
      return;
    }

    if (message.type !== "request" || !message.id) return;
    const reply = { source: RPC_SOURCE, type: "response", id: message.id };
    try {
      if (!this._hass) throw new Error("Home Assistant frontend is not ready");
      // The payload is sent by Home Assistant's authenticated frontend API
      // directly to Core. Never log or persist it: it can contain passwords.
      reply.payload = await this._hass.callApi("POST", "bitcoin_stack_tracker/panel/rpc", {
        path: String(message.path || ""),
        method: String(message.method || "GET").toUpperCase(),
        content_type: String(message.content_type || ""),
        body_text: typeof message.body_text === "string" ? message.body_text : null,
        form: message.form || null,
      });
    } catch (error) {
      reply.error = panelErrorText(error);
    }
    this._frame.contentWindow.postMessage(reply, window.location.origin);
  }
}

if (!customElements.get(PANEL_ELEMENT)) {
  customElements.define(PANEL_ELEMENT, BitcoinStackTrackerPanel);
}
