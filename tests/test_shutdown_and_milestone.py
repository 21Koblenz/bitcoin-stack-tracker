from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
STYLE = (COMP / "frontend/static/style.css").read_text(encoding="utf-8")
APPARMOR = (ROOT / "bitcoin_stack_tracker_dashboard" / "apparmor.txt").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard" / "run.sh").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")


def test_tor_profile_can_receive_forced_shutdown_signals():
    assert "signal (send) set=(kill,term,int,hup,cont,exists)," in APPARMOR
    assert "signal (receive) set=(kill,term,int,quit,hup,usr1,usr2,cont,exists)," in APPARMOR
    assert 'signal_pid_checked "${tor_pid}" KILL "Tor"' in RUN
    assert "managed_process_details" in RUN
    assert "comm=%s state=%s ppid=%s uid=%s" in RUN


def test_partial_milestone_progress_is_not_blocked_by_csp_inline_style_policy():
    # The page intentionally has style-src 'self' without unsafe-inline. Dynamic
    # ring progress therefore must not depend on an inline style attribute.
    assert "style-src 'self'" in INDEX
    goal_template = APP.split('function renderGoalCards()', 1)[1].split('function firstPortfolioActivityDay()', 1)[0]
    assert 'stroke-dasharray="${ringDash} ${ringGap}"' in goal_template
    assert 'stroke-dashoffset="${Math.max(0,100-ringProgress)}"' not in goal_template
    assert 'style="stroke-dashoffset:' not in goal_template
    assert '.goal-ring-progress{stroke:var(--orange);stroke-linecap:round;' in STYLE
    assert '.goal-ring-progress{stroke:var(--orange);stroke-dasharray:100;stroke-dashoffset:100;' not in STYLE
