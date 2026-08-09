from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"
PANEL = (FRONTEND / "panel-v021000-197f97c6.js").read_text(encoding="utf-8")
CSS = (FRONTEND / "static" / "style-v021000-197f97c6.css").read_text(encoding="utf-8")


def test_mobile_panel_has_home_assistant_style_app_bar():
    assert '.ha-mobile-bar{display:none' in PANEL
    assert '@media(max-width:870px)' in PANEL
    assert '.ha-mobile-bar{display:flex}' in PANEL
    assert 'title.textContent = "Bitcoin Stack Tracker"' in PANEL
    assert 'bitcoin-stack-tracker-logo.png' in PANEL


def test_mobile_bar_uses_home_assistant_custom_panel_toggle_event():
    assert 'this.dispatchEvent(new CustomEvent("hass-toggle-menu"' in PANEL
    assert 'external.fireMessage' not in PANEL
    assert 'home-assistant-main' not in PANEL


def test_inner_mobile_header_does_not_duplicate_branding():
    assert '.app-header .brand-lockup{display:none!important}' in CSS
