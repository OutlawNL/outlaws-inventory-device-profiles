import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import profile_documents as engine
from app.device_profiles import match_profile, validate_profile

ROOT = Path(__file__).resolve().parents[1]
PDF = sorted((ROOT / 'tests/fixtures/expanded_profiles').glob('*/profile.json'))
HTML = sorted((ROOT / 'tests/fixtures/html_profiles').glob('*/profile.json'))

def load(path):
    return json.loads(path.read_text()), json.loads(path.with_name('expected.json').read_text())

@pytest.mark.parametrize('path', PDF, ids=lambda p: p.parent.name)
def test_expanded_official_pdf(path):
    p, expected = load(path)
    validate_profile(p)
    f = p['firmware']
    assert engine.discover(path.with_name('source.html').read_text(), f['source']['url'], f['discovery']) == expected['url']
    assert engine.extract_pdf(path.with_name('notes.pdf').read_bytes(), f) == {k:v for k,v in expected.items() if k != 'url'}

@pytest.mark.parametrize('path', HTML, ids=lambda p: p.parent.name)
def test_official_html_page(path):
    p, expected = load(path)
    validate_profile(p)
    assert engine.extract_html(path.with_name('source.html').read_text(), p['firmware']) == expected

@pytest.mark.parametrize('path', HTML, ids=lambda p: p.parent.name)
def test_html_never_uses_another_product_or_history_version(path):
    p, expected = load(path)
    html = path.with_name('source.html').read_text()
    f = p['firmware']
    bad = copy.deepcopy(f)
    bad['validation']['document_titles'] = ['Another model Firmware update']
    assert engine.extract_html(html, bad)['latest'] == ''
    html = html.replace('Version: '+expected['latest'], 'Version: invalid')
    assert engine.extract_html(html, f)['latest'] == ''


def test_html_ambiguous_history_keeps_header_but_not_summary():
    from bs4 import BeautifulSoup
    p, expected = load(HTML[0])
    html = HTML[0].with_name('source.html').read_text()
    item = BeautifulSoup(html, 'html.parser').select_one('.accordion-item')
    result = engine.extract_html(html+str(item), p['firmware'])
    assert result['latest'] == expected['latest']
    assert result['summary'] == ''
    assert result['error']

@pytest.mark.parametrize('path', PDF + HTML, ids=lambda p: p.parent.name)
def test_full_application_profile_result(path):
    p, expected = load(path)
    is_html = p['firmware']['strategy'] == 'html_release'
    name = '_html_profile_result' if is_html else '_release_notes_pdf_profile_result'
    names = {name, '_discover_profile_document', '_profile_versions_are_comparable'}
    nodes = [n for n in ast.parse((ROOT/'app/main.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    def get(url, **kwargs):
        assert url in (p['firmware']['source']['url'], expected.get('url'))
        return SimpleNamespace(url=url, text=path.with_name('source.html').read_text(), content=b'' if is_html else path.with_name('notes.pdf').read_bytes(), raise_for_status=lambda:None)
    ns = {'requests':SimpleNamespace(get=get),'profile_documents':engine,'APP_VERSION':'0.18.8',
          'sqlite3':SimpleNamespace(Row=dict),'_version_key':lambda s:tuple(map(int,s.split('.'))),
          '_firmware_status':lambda c,l:'attention' if l else 'unknown'}
    ns['_document_get'] = lambda client, url, **kwargs: client.get(url, **kwargs)
    exec(compile(ast.Module(body=nodes,type_ignores=[]), 'main.py', 'exec'),ns)
    result=ns[name]({'current_firmware':'0.0'},p)
    for field in ['latest','release_date','summary','error']:assert result[field]==expected[field]


def test_component_releases_never_use_pro_or_skip_malformed_target(monkeypatch):
    path=next(p for p in PDF if p.parent.name=='dji-o4-air-unit')
    p,_=load(path);f=p['firmware']
    own='DJI O4 Air Unit Series Release Notes\nDate: 2026.06.25\nDJI O4 Air Unit Firmware: v01.00.0400\nWhat’s New\n• Fixed bugs.\nNotes:'
    pro=own.replace('2026.06.25','2026.07.02').replace('DJI O4 Air Unit Firmware:', 'DJI O4 Air Unit Pro Firmware:').replace('v01.00.0400','v01.00.07.00')
    class PDFDoc:
        def __init__(self,texts):self.pages=[SimpleNamespace(extract_text=lambda t=t,**kw:t) for t in texts]
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def check(texts):
        monkeypatch.setattr(engine.pdfplumber,'open',lambda *a:PDFDoc(texts))
        return engine.extract_pdf(b'pdf',f)
    assert check([pro,own])['latest']=='01.00.0400'
    assert check([own.replace('v01.00.0400','invalid'),own])['latest']==''
    assert check(['unreadable',own])['latest']==''
    assert check([pro.replace('2026.07.02','invalid'),own])['latest']==''
    assert check([pro])['latest']==''


def test_plus_identity_and_ambiguous_profiles():
    plus={'id':'plus','device':{'vendor':'DJI','model':'Osmo+'}}
    plain={'id':'plain','device':{'vendor':'DJI','model':'Osmo'}}
    catalog={'profiles':[plus,plain]}
    assert match_profile(catalog,'DJI','Osmo+')['id']=='plus'
    assert match_profile(catalog,'DJI','Osmo')['id']=='plain'
    assert match_profile({'profiles':[plain,dict(plain,id='other')]},'DJI','Osmo') is None


def test_mark_updated_returns_to_origin_and_saves(tmp_path):
    import sqlite3
    from contextlib import contextmanager
    database=tmp_path/'test.db'
    con=sqlite3.connect(database)
    con.execute('CREATE TABLE devices (id INTEGER PRIMARY KEY, current_firmware TEXT, latest_firmware TEXT, latest_firmware_override TEXT, status TEXT,last_firmware_update TEXT,updated_at TEXT)')
    con.execute("INSERT INTO devices VALUES (1,'1.0','2.0','','attention','','')");con.commit();con.close()
    @contextmanager
    def db():
        con=sqlite3.connect(database);con.row_factory=sqlite3.Row
        with con:yield con
        con.close()
    def fetch(id):
        with db() as con:return con.execute('SELECT * FROM devices WHERE id=?',(id,)).fetchone()
    tree=ast.parse((ROOT/'app/main.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='mark_firmware_updated');node.decorator_list=[]
    ns={'Form':lambda default:default,'fetch_device':fetch,'db':db,'now':lambda:'now','_effective_latest_version':lambda latest,override:override or latest,'require_current_user_id':lambda:1,'add_activity_event':lambda *args:None,'RedirectResponse':lambda url,**kw:url}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'main.py','exec'),ns)
    for target,expected in [('firmware','/firmware'),('device','/devices/1'),('https://evil.example','/devices/1')]:
        assert ns['mark_firmware_updated'](1,target)==expected
        assert fetch(1)['current_firmware']=='2.0'
        assert fetch(1)['status']=='ok'


@pytest.mark.parametrize('identity,old_date', [('dji-mic-mini-2s','20260702'), ('dji-rs-intelligent-tracking-module','20250312')])
def test_document_discovery_survives_new_date_in_filename(identity, old_date):
    path = next(p for p in PDF if p.parent.name == identity)
    profile, expected = load(path)
    html = path.with_name('source.html').read_text().replace(old_date, '20270915')
    f = profile['firmware']
    assert engine.discover(html, f['source']['url'], f['discovery']) == expected['url'].replace(old_date, '20270915')
