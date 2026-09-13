import copy
import json
from pathlib import Path
import pytest
from app import profile_documents as engine

FIXTURES = Path(__file__).parent / 'fixtures/profile_documents'
PROFILES = sorted(FIXTURES.glob('*/profile.json'))

@pytest.mark.parametrize('path', PROFILES, ids=lambda p: p.parent.name)
def test_real_download_page_and_pdf(path):
    profile = json.loads(path.read_text())
    expected = json.loads(path.with_name('expected.json').read_text())
    f = profile['firmware']
    assert engine.discover(path.with_name('source.html').read_text(), f['source']['url'], f['discovery']) == expected['url']
    text = engine.first_page_text(path.with_name('notes.pdf').read_bytes())
    result = engine.extract(text, f)
    assert result == {k: v for k, v in expected.items() if k != 'url'}

@pytest.fixture
def sample():
    p = FIXTURES / 'dji-neo-2/profile.json'
    f = json.loads(p.read_text())['firmware']
    text = engine.first_page_text(p.with_name('notes.pdf').read_bytes())
    return f, text


def test_missing_device_firmware_never_uses_controller_or_older_release(sample):
    f, text = sample
    bad = text.replace('DJI Neo 2 Firmware: V01.00.0700', 'DJI Neo 2 Firmware:')
    result = engine.extract(bad + '\n' + text, f)
    assert result['latest'] == ''
    assert result['summary'] == ''


def test_invalid_or_missing_date_stays_unknown(sample):
    f, text = sample
    for date in ['', '2026.02.30', 'tomorrow']:
        result = engine.extract(text.replace('2026.06.23', date), f)
        assert result['release_date'] == ''
        assert result['latest'] == '01.00.0700'


def test_duplicate_labels_fail_closed(sample):
    f, text = sample
    result = engine.extract(text.replace('Date: 2026.06.23', 'Date: 2026.06.23\nDate: 2025.12.10'), f)
    assert result['release_date'] == ''


def test_wrong_product_title_rejects_generic_firmware_label(sample):
    f, text = sample
    result = engine.extract(text.replace('DJI Neo 2 Release Notes', 'Other Device Release Notes'), f)
    assert result['latest'] == result['release_date'] == result['summary'] == ''


def test_missing_section_end_does_not_capture_next_release(sample):
    f, text = sample
    bad = text.replace('Notes:', 'Instructions:')
    assert engine.extract(bad, f)['summary'] == ''
    assert engine.extract(bad + '\n' + text, f)['summary'] == ''


def test_unicode_punctuation_and_date_normalization(sample):
    f, text = sample
    text = text.replace('Firmware:', 'Firmware：').replace('2026.06.23', '2026.6.23')
    result = engine.extract(text, f)
    assert result['latest'] == '01.00.0700'
    assert result['release_date'] == '2026-06-23'


def test_discovery_requires_one_matching_product_document():
    rule = {'title_contains': ['Camera - Release Notes'], 'url_contains': ['Camera_Release'], 'url_pattern': r'_en\.pdf$'}
    own = '<li>Camera - Release Notes<a href="/Camera_Release_en.pdf">PDF</a></li>'
    unrelated = '<li>Microphone - Release Notes<a href="/Microphone_Release_en.pdf">PDF</a></li>'
    assert engine.discover(own + unrelated, 'https://example.com', rule) == 'https://example.com/Camera_Release_en.pdf'
    assert engine.discover(unrelated, 'https://example.com', rule) == ''
    assert engine.discover(own + own.replace('/Camera_', '/new/Camera_'), 'https://example.com', rule) == ''
    assert engine.discover(own + own, 'https://example.com', rule) == 'https://example.com/Camera_Release_en.pdf'
    assert engine.discover(own.replace('_en.pdf', '_cn.pdf'), 'https://example.com', rule) == ''


def test_real_pdf_does_not_mix_releases_with_identical_version():
    p = FIXTURES / 'dji-osmo-360/profile.json'
    f = json.loads(p.read_text())['firmware']
    result = engine.extract(engine.first_page_text(p.with_name('notes.pdf').read_bytes()), f)
    assert result['latest'] == '01.03.08.70'
    assert result['release_date'] == '2026-02-24'
    assert 'Adaptive Tone' in result['summary']
    assert 'livestream' not in result['summary']

@pytest.mark.parametrize('path', PROFILES, ids=lambda p: p.parent.name)
def test_application_result_uses_new_engine(path):
    import ast
    from types import SimpleNamespace
    main = Path(__file__).resolve().parents[1] / 'app/main.py'
    names = {'_discover_profile_document', '_profile_versions_are_comparable', '_release_notes_pdf_profile_result'}
    nodes = [n for n in ast.parse(main.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    profile = json.loads(path.read_text())
    expected = json.loads(path.with_name('expected.json').read_text())
    source = profile['firmware']['source']['url']
    def get(url, **kwargs):
        assert url in (source, expected['url'])
        return SimpleNamespace(url=url, text=path.with_name('source.html').read_text(), content=path.with_name('notes.pdf').read_bytes(), raise_for_status=lambda: None)
    ns = {'requests': SimpleNamespace(get=get), 'profile_documents': engine, 'APP_VERSION': '0.18.4',
          '_version_key': lambda s: tuple(map(int,s.split('.'))), '_firmware_status': lambda c,l: 'update' if l else 'unknown',
          'sqlite3': SimpleNamespace(Row=dict)}
    ns['_document_get'] = lambda client, url, **kwargs: client.get(url, **kwargs)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(main), 'exec'), ns)
    result = ns['_release_notes_pdf_profile_result']({'current_firmware': '00.00.0000'}, profile)
    assert result['latest'] == expected['latest']
    assert result['release_date'] == expected['release_date']
    assert result['summary'] == expected['summary']
    assert result['notes_url'] == expected['url']
    assert result['error'] == ''


def test_malformed_pdf_fails_without_guessing():
    with pytest.raises(Exception):
        engine.first_page_text(b'not a PDF')


def test_incomplete_first_release_never_falls_through_to_complete_second(sample):
    f, text = sample
    bad = 'DJI Neo 2 Release Notes\nNotes:\nUnavailable\n' + text
    result = engine.extract(bad, f)
    assert result['latest'] == result['release_date'] == ''
