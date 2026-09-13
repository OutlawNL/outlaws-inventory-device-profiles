from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_single_classic_interface_only():
    base=(ROOT/'app/templates/base.html').read_text()
    settings=(ROOT/'app/templates/settings.html').read_text()
    setup=(ROOT/'app/templates/setup_wizard.html').read_text()
    main=(ROOT/'app/main.py').read_text()
    css=(ROOT/'app/static/app.css').read_text()
    assert '<body class="icons-on">' in base
    assert 'theme-brand-mark' not in base
    assert '>OI<' not in base
    assert 'data-setting-name="theme"' not in settings
    assert '<strong>Interface</strong>' not in settings
    assert 'name="theme"' not in setup
    assert '"theme": "dark"' not in main
    assert '"dashboard_refresh_minutes", "theme", "icons"' not in main
    assert '.theme-light' not in css

def test_icons_are_permanent():
    settings=(ROOT/'app/templates/settings.html').read_text()
    assert 'data-setting-name="icons"' not in settings
    assert 'Show interface icons in primary navigation' not in settings

def test_branding_refinement_present():
    css=(ROOT/'app/static/app.css').read_text()
    assert '.brand-text strong{font-size:32px' in css
    assert '.brand-text span{font-size:14.5px' in css
