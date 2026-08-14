from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"


def test_brand_logo_remains_full_color_and_not_a_dead_menu_control():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'src="static/assets/bitcoin-stack-tracker-logo.png"' in html
    assert 'brand-koblenz-logo brand-color-logo' in html
    assert 'id="haMenuButton"' not in html


def test_native_panel_handles_legacy_iframe_menu_action():
    panel = (FRONTEND / "panel-v021009-ae7b9cb3.js").read_text(encoding="utf-8")
    assert 'message.type === "ui-action" && message.action === "open-menu"' in panel
    assert 'this._openHomeAssistantMenu();' in panel


def test_native_panel_has_real_mobile_menu_button():
    panel = (FRONTEND / "panel-v021009-ae7b9cb3.js").read_text(encoding="utf-8")
    assert 'menu.className = "ha-menu-button"' in panel
    assert 'menu.addEventListener("click", this._openHomeAssistantMenu)' in panel
    assert 'Home-Assistant-Menü öffnen' in panel
