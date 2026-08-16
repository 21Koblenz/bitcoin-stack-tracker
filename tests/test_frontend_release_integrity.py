from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
PANEL = (COMP / "frontend/panel.js").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style.css").read_text(encoding="utf-8")


def test_heavy_tabs_render_lazily():
    block = APP.split("function renderAll()", 1)[1].split("function lifetimeFiatSecured", 1)[0]
    assert "renderActiveTabContent(state.activeTab);" in block
    assert "renderOverview(); renderLedger();" not in block


def test_network_polling_is_visibility_aware_and_less_aggressive():
    block = APP.split("function startNetworkPolling()", 1)[1].split("function renderSecurity", 1)[0]
    assert "if(document.hidden)return;" in block
    assert "},30000);" in block
    assert "},4000);" not in block
    assert 'state.activeTab==="settings"' in block
    assert 'state.activeTab==="settings" ||' not in block


def test_resize_work_waits_until_viewport_settles():
    assert "function scheduleViewportSettledWork()" in APP
    assert 'window.addEventListener("resize",scheduleViewportSettledWork,{passive:true});' in APP
    assert '}, 220);' in APP
    assert 'window.addEventListener("resize",updateCsvHorizontalScroll);' not in APP
    assert 'csvModal && !csvModal.classList.contains("hidden")' in APP
    assert "viewport-resizing" in APP


def test_fifo_mobile_fiat_values_hide_in_fiat_free_mode():
    assert "body.fiat-free-mode .fifo-fiat-metric{display:none!important}" in CSS


def test_menu_uses_home_assistant_custom_panel_toggle_event():
    assert 'this.dispatchEvent(new CustomEvent("hass-toggle-menu"' in PANEL
    assert 'external.fireMessage' not in PANEL
    assert 'home-assistant-main' not in PANEL


def test_frontend_release_uses_only_stable_entrypoint_filenames():
    frontend = COMP / "frontend"
    static = frontend / "static"
    assert (frontend / "index.html").is_file()
    assert (frontend / "panel.js").is_file()
    assert (static / "app.js").is_file()
    assert (static / "style.css").is_file()
    assert (static / "performance-math.js").is_file()
    assert not list(frontend.glob("index-v*.html"))
    assert not list(frontend.glob("panel-v*.js"))
    assert not list(static.glob("app-v*.js"))
    assert not list(static.glob("style-v*.css"))
    assert not list(static.glob("performance-math-v*.js"))
    panel_py = (COMP / "panel.py").read_text(encoding="utf-8")
    assert 'module_url=f"{STATIC_URL}/panel.js?v={VERSION}"' in panel_py
    assert '"frontend_url": f"{STATIC_URL}/index.html?native=1&v={VERSION}"' in panel_py
    assert 'static/app.js?v=0.21.0.11' in INDEX
    assert 'static/style.css?v=0.21.0.11' in INDEX
    assert 'static/performance-math.js?v=0.21.0.11' in INDEX
