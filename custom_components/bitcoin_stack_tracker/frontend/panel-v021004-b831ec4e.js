const FRONTEND_BUILD = "021004-b831ec4e";
const RPC_SOURCE = "bitcoin-stack-tracker-native";

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
    frame.src = src;
    frame.referrerPolicy = "no-referrer";
    frame.setAttribute("allow", "clipboard-write");

    shell.append(toolbar, frame);
    this.shadowRoot.append(style, shell);
    this._frame = frame;
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

if (!customElements.get("bitcoin-stack-tracker-panel")) {
  customElements.define("bitcoin-stack-tracker-panel", BitcoinStackTrackerPanel);
}
