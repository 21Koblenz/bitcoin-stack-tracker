from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app-v021002-81aa3197.js").read_text(encoding="utf-8")
PANEL = (COMP / "frontend/panel-v021002-81aa3197.js").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021002-81aa3197.css").read_text(encoding="utf-8")

def test_sidebar_animation_does_not_force_csv_layout_on_every_resize():
    assert 'window.addEventListener("resize",updateCsvHorizontalScroll);' not in APP
    assert 'window.addEventListener("resize",scheduleViewportSettledWork,{passive:true});' in APP
    assert '}, 220);' in APP

def test_mobile_iframe_is_compositor_isolated_without_changing_menu_path():
    assert 'iframe{width:100vw;max-width:100vw;contain:paint;transform:translateZ(0);backface-visibility:hidden}' in PANEL
    assert 'new CustomEvent("hass-toggle-menu"' in PANEL

def test_expensive_mobile_effects_are_suppressed_during_viewport_animation():
    assert 'html.viewport-resizing .app-header' in CSS
    assert 'html.viewport-resizing .panel' in CSS
    assert 'html.viewport-resizing .chart .series-primary{filter:none}' in CSS
