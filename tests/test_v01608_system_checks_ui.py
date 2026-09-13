from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text()
DETAIL = (ROOT / "app" / "templates" / "system_check_detail.html").read_text()
CSS = (ROOT / "app" / "static" / "app.css").read_text()


def test_version_is_0168():
    assert 'APP_VERSION = "0.18.8"' in MAIN


def test_system_upgrade_success_uses_standard_success_notice():
    assert 'notice success">System upgrade completed successfully.' in DETAIL


def test_action_alignment_targets_sixth_column():
    assert '>td:nth-child(6) .system-checks-row-actions' in CSS
    assert '>td:nth-child(6) form' in CSS


def test_mobile_detail_cards_stretch_full_width_and_preserve_order():
    assert 'align-items:stretch!important' in CSS
    for selector in ('#checks', '#updates', '#minecraft-updates', '#pihole-updates', '#history'):
        assert selector in CSS
    assert 'width:100%!important' in CSS
    assert '.classic-system-detail-form #updates{order:2}' in CSS
    assert '.classic-system-detail-form #history{order:4}' in CSS
