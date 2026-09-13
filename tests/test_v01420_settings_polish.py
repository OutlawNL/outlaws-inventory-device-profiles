from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_notification_form_is_compact_and_grouped():
    html=(ROOT/'app/templates/settings.html').read_text()
    css=(ROOT/'app/static/app.css').read_text()
    assert 'notification-settings-wrap' in html
    assert 'notification-field-grid' in html
    assert '<h4>Notify For</h4>' in html
    assert 'E-mail Server' in html
    assert 'max-width:980px' in css
    assert 'max-width:820px' in css

def test_dashboard_kpis_are_slightly_reduced():
    css=(ROOT/'app/static/app.css').read_text()
    assert '.dashboard-kpis .card strong{font-size:26px' in css

def test_account_visual_nesting_is_reduced():
    css=(ROOT/'app/static/app.css').read_text()
    assert '.account-settings-grid>.profile-card{border:0!important' in css
    assert '.profile-security-panel{border:0!important' in css
