from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_experimental_themes_removed():
    main=(ROOT/'app/main.py').read_text()
    settings=(ROOT/'app/templates/settings.html').read_text()
    base=(ROOT/'app/templates/base.html').read_text()
    css=(ROOT/'app/static/app.css').read_text()
    assert 'data-setting-value="transformers"' not in settings
    assert 'data-setting-name="theme"' not in settings
    assert 'retro-green' not in settings
    assert '{"dark", "light"}' not in main
    assert 'theme-transformers' not in css
    assert 'transformers-commandbar' not in base
    assert not (ROOT/'app/static/transformers-emblem.png').exists()
    assert not (ROOT/'app/static/transformers-truck.png').exists()

def test_icons_are_permanent_classic_feature():
    base=(ROOT/'app/templates/base.html').read_text()
    settings=(ROOT/'app/templates/settings.html').read_text()
    assert '<body class="icons-on">' in base
    assert "settings.get('icons'" not in base
    assert 'data-setting-name="icons"' not in settings

def test_classic_typography_refinement_present():
    css=(ROOT/'app/static/app.css').read_text()
    for token in [
        'grid-template-columns:21px minmax(0,1fr)',
        '.sidebar nav a{font-size:15px',
        '.icons-on .dashboard-label-icon',
        'table td{font-size:15px',
        '.device-link{font-size:15px',
    ]:
        assert token in css
