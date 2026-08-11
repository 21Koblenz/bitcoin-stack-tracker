from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"
PANEL = (FRONTEND / "panel-v021005-28d54128.js").read_text(encoding="utf-8")


def test_header_uses_existing_full_color_brand_asset_without_resizing_rules():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "static" / "style-v021005-28d54128.css").read_text(encoding="utf-8")
    asset = FRONTEND / "static" / "assets" / "bitcoin-stack-tracker-logo.png"
    assert asset.exists()
    assert 'src="static/assets/bitcoin-stack-tracker-logo.png"' in html
    assert 'brand-koblenz-logo brand-color-logo' in html
    assert '.brand-koblenz-logo.brand-color-logo{filter:none!important}' in css
    assert '.brand-koblenz-logo{width:40px;height:34px}' in css


def test_menu_uses_home_assistant_custom_panel_toggle_event():
    assert 'this.dispatchEvent(new CustomEvent("hass-toggle-menu"' in PANEL
    assert 'external.fireMessage' not in PANEL
    assert 'home-assistant-main' not in PANEL
