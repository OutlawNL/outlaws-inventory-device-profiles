import ast
import asyncio
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
import pytest
from fastapi.responses import RedirectResponse

MAIN = (Path(__file__).parents[1] / 'app/main.py').read_text()

@pytest.fixture
def harness():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    columns = re.search(r'INSERT INTO devices\((.*?)\)', MAIN[MAIN.index('async def create_device'):]).group(1).split(',')
    conn.execute('CREATE TABLE devices(id INTEGER PRIMARY KEY, '+','.join(x+' TEXT' for x in columns)+',last_checked TEXT)')
    calls = []
    def check(device):
        assert conn.execute('SELECT id FROM devices WHERE id=?',(device['id'],)).fetchone()
        calls.append(device['id'])
        return dict(status='ok', latest='01.00.1500', release_date='2026-09-01', summary='Fixed issues.', notes_url='https://example.com/notes.pdf', confidence='Official', source='Device Profile source', method='Device Profile', error='')
    profile = {'firmware': {'source': {'url': 'https://example.com/downloads'}, 'strategy': 'release_notes_pdf'}}
    async def in_worker(func, *args, **kwargs):
        return func(*args, **kwargs)
    ns = dict(run_in_threadpool=in_worker,Form=lambda default=None,**kw:default,File=lambda default=None,**kw:default,
              now=lambda:'2026-09-12T12:00:00',format_euro=lambda x:x,
              _available_device_profile=lambda *a,**kw:profile, db=lambda:conn,
              fetch_device=lambda i:conn.execute('SELECT * FROM devices WHERE id=? AND owner_user_id=?',(i,7)).fetchone(),
              require_current_user_id=lambda:7,category_config=lambda c:{'show_firmware':c!='Other'},
              _firmware_monitoring_supported=lambda d:True,check_device=check,
              RedirectResponse=RedirectResponse,quote=quote,datetime=datetime)
    wanted={'create_device','_initial_device_firmware_check','_check_and_store_device_firmware'}
    nodes=[n for n in ast.parse(MAIN).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in wanted]
    for n in nodes:n.decorator_list=[]
    exec(compile(ast.Module(body=ast.parse('from __future__ import annotations').body+nodes,type_ignores=[]),'main.py','exec'),ns)
    request=SimpleNamespace(state=SimpleNamespace(user={'id':7}))
    def create(**kw):
        return asyncio.run(ns['create_device'](request,display_name='Goggles',**kw))
    yield ns, conn, calls, create
    conn.close()


def test_save_checks_persisted_device_even_without_daily_auto_check(harness):
    ns,con,calls,create=harness
    response=create(category='FPV Goggles',current_firmware='01.00.1500')
    row=con.execute('SELECT * FROM devices').fetchone()
    assert calls==[row['id']]
    assert row['auto_check']=='0'
    assert row['latest_firmware']=='01.00.1500'
    assert row['release_date']=='2026-09-01'
    assert row['status']=='ok' and row['last_checked']
    assert response.headers['location']==f"/devices/{row['id']}?created=device"


@pytest.mark.parametrize('mode',['no_source','hidden_firmware','unsupported'])
def test_skip_devices_without_usable_firmware_monitoring(harness,mode):
    ns,con,calls,create=harness
    if mode=='no_source':ns['_available_device_profile']=lambda *a,**k:None
    if mode=='unsupported':ns['_firmware_monitoring_supported']=lambda d:False
    create(category='Other' if mode=='hidden_firmware' else 'FPV Goggles')
    assert calls==[]
    assert con.execute('SELECT COUNT(*) FROM devices').fetchone()[0]==1


def test_initial_check_failure_keeps_device_saved_and_offers_retry(harness):
    ns,con,calls,create=harness
    def fail(device):raise RuntimeError('network unavailable')
    ns['check_device']=fail
    response=create(category='FPV Goggles')
    assert response.status_code==303
    assert 'firmware_check_error=' in response.headers['location']
    assert con.execute('SELECT COUNT(*) FROM devices').fetchone()[0]==1


def test_first_run_redirect_is_preserved(harness):
    ns,con,calls,create=harness
    response=create(category='FPV Goggles',first_run='1')
    assert calls==[1]
    assert response.headers['location']=='/first-run/item-saved?device_id=1&item_type=device'


def test_initial_check_is_only_in_creation_path():
    tree=ast.parse(MAIN)
    funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    callers=[]
    for name,node in funcs.items():
        if any(isinstance(n,ast.Name) and n.id=='_initial_device_firmware_check' for n in ast.walk(node)):callers.append(name)
    assert callers==['create_device']
