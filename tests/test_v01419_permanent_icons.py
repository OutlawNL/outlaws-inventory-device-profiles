from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_icons_are_permanent_and_preferences_removed():
    base=(ROOT/'app/templates/base.html').read_text()
    settings=(ROOT/'app/templates/settings.html').read_text()
    dashboard=(ROOT/'app/templates/dashboard.html').read_text()
    main=(ROOT/'app/main.py').read_text()
    setup=(ROOT/'app/templates/setup_wizard.html').read_text()
    assert '<body class="icons-on">' in base
    assert "settings.get('icons'" not in base+settings+dashboard
    assert 'data-setting-name="icons"' not in settings
    assert 'id="interface"' not in settings
    assert 'Account and notifications.' in settings
    assert '"icons": "off"' not in main
    assert '"icons", "language"' not in main
    assert 'name="theme"' not in setup

def test_no_current_theme_or_appearance_preferences_remain():
    settings=(ROOT/'app/templates/settings.html').read_text().lower()
    setup=(ROOT/'app/templates/setup_wizard.html').read_text().lower()
    ideas=(ROOT/'docs/IDEAS.md').read_text().lower()
    todo=(ROOT/'docs/TODO.md').read_text().lower()
    assert 'appearance' not in settings
    assert 'theme' not in settings
    assert 'theme' not in setup
    assert 'themes and colour schemes' not in ideas
    assert 'light theme' not in todo
