import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import zipfile

import pytest

from test_v01807_audit_repairs import m

ROOT = Path(__file__).resolve().parents[1]
import types
verifier = types.ModuleType('root_release_verifier')
exec(compile((ROOT/'scripts/outlaws-inventory-verify-release').read_text(), 'root_release_verifier', 'exec'), verifier.__dict__)


def package_fixture(tmp_path, *, extra=None):
    staging=tmp_path/'staging';staging.mkdir()
    private=tmp_path/'root';private.mkdir()
    name='outlaws-inventory-v0.18.8.zip';package=staging/name
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('outlaws-inventory-v0.18.8/app/main.py','APP_VERSION = "0.18.8"')
        archive.writestr('outlaws-inventory-v0.18.8/update.sh','#!/bin/sh\nexit 0\n')
        if extra: archive.writestr(extra, 'untrusted')
    digest=hashlib.sha256(package.read_bytes()).hexdigest()
    pending=staging/'pending.json';pending.write_text(json.dumps(dict(version='0.18.8',zip=str(package),sha256='not-trusted')))
    def fetch(url,token,accept=None):
        assert url.startswith('https://api.github.com/repos/OutlawNL/outlaws-inventory/releases/')
        if '/assets/' in url:return f'{digest}  {name}\n'.encode()
        return json.dumps(dict(tag_name='v0.18.8',draft=False,assets=[dict(name='SHA256SUMS',id=3),dict(name=name,id=4)])).encode()
    return pending,private,staging,package,fetch


def test_root_verifier_uses_official_hash_and_private_copy(tmp_path):
    pending,private,staging,package,fetch=package_fixture(tmp_path)
    verified=verifier.verify(pending,private,staging=staging,token_file=tmp_path/'none',fetcher=fetch)
    trusted=Path(verified['zip'])
    assert trusted.parent==private and trusted.read_bytes()==package.read_bytes()
    package.write_bytes(b'changed after verification')
    assert hashlib.sha256(trusted.read_bytes()).hexdigest()==verified['sha256']


def test_root_verifier_rejects_package_even_if_local_hash_matches(tmp_path):
    pending,private,staging,package,fetch=package_fixture(tmp_path)
    package.write_bytes(b'forged package')
    info=json.loads(pending.read_text());info['sha256']=hashlib.sha256(package.read_bytes()).hexdigest();pending.write_text(json.dumps(info))
    with pytest.raises(ValueError,match='official release checksum'):
        verifier.verify(pending,private,staging=staging,token_file=tmp_path/'none',fetcher=fetch)


@pytest.mark.parametrize('member',['../outside','/absolute','other-root/file','outlaws-inventory-v0.18.8/../outside'])
def test_root_verifier_rejects_unsafe_archive(tmp_path,member):
    pending,private,staging,package,fetch=package_fixture(tmp_path,extra=member)
    with pytest.raises(ValueError,match='Unsafe release'):
        verifier.verify(pending,private,staging=staging,token_file=tmp_path/'none',fetcher=fetch)


def test_root_verifier_rejects_symlink_package(tmp_path):
    pending,private,staging,package,fetch=package_fixture(tmp_path)
    actual=tmp_path/'actual';package.rename(actual);package.symlink_to(actual)
    with pytest.raises(ValueError,match='package path'):
        verifier.verify(pending,private,staging=staging,token_file=tmp_path/'none',fetcher=fetch)


@pytest.fixture
def recovery_environment(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'DB_PATH',tmp_path/'database.sqlite3')
    monkeypatch.setattr(m,'BACKUP_DIR',tmp_path/'backups')
    monkeypatch.setattr(m,'normalize_runtime_data_permissions',lambda:None)
    monkeypatch.setattr(m,'init_db',lambda:None)
    dirs=tuple((name,tmp_path/name) for name in ('uploads','keys','secrets','avatars'))
    monkeypatch.setattr(m,'BACKUP_COMPONENTS',dirs)
    for name,directory in dirs:
        directory.mkdir();(directory/'original').write_text('backup value')
    with m.db() as con:
        con.execute('CREATE TABLE marker(value TEXT)');con.execute("INSERT INTO marker VALUES ('backup value')")
    backup=m.create_full_backup()
    with m.db() as con:con.execute("UPDATE marker SET value='live value'")
    for _,directory in dirs:(directory/'original').write_text('live value')
    return backup,dirs


def test_restore_real_wal_database_and_component_files(recovery_environment):
    backup,dirs=recovery_environment
    m.restore_full_backup(backup)
    with m.db() as con:assert con.execute('SELECT value FROM marker').fetchone()[0]=='backup value'
    assert all((directory/'original').read_text()=='backup value' for _,directory in dirs)


def test_failure_after_database_restore_recovers_live_state(recovery_environment,monkeypatch):
    backup,dirs=recovery_environment
    copy=m._copy_tree_contents;calls=[]
    def fail_once(*args):
        calls.append(True)
        if len(calls)==1:raise OSError('simulated replacement failure')
        return copy(*args)
    monkeypatch.setattr(m,'_copy_tree_contents',fail_once)
    with pytest.raises(OSError,match='replacement failure'):m.restore_full_backup(backup)
    with m.db() as con:assert con.execute('SELECT value FROM marker').fetchone()[0]=='live value'
    assert all((directory/'original').read_text()=='live value' for _,directory in dirs)


def test_failed_recovery_retains_complete_safety_copy(recovery_environment,monkeypatch):
    backup,dirs=recovery_environment
    def fail(*args):raise OSError('persistent disk error')
    monkeypatch.setattr(m,'_copy_tree_contents',fail)
    with pytest.raises(RuntimeError,match='Recovery files retained at') as caught:m.restore_full_backup(backup)
    retained=Path(str(caught.value).split('retained at ',1)[1].split(': ',1)[0])
    try:
        assert (retained/'database.sqlite3').is_file()
        assert all((retained/name/'original').read_text()=='live value' for name,_ in dirs)
    finally:
        import shutil
        shutil.rmtree(retained)


def test_database_gate_waits_for_active_connection(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'DB_PATH',tmp_path/'db')
    started=threading.Event();finished=threading.Event()
    con=m.db()
    def restore_access():
        started.set()
        m._database_gate.acquire_exclusive()
        try: finished.set()
        finally: m._database_gate.release_exclusive()
    thread=threading.Thread(target=restore_access);thread.start()
    assert started.wait(1)
    assert not finished.wait(0.05)
    con.close();thread.join(2)
    assert finished.is_set()


def test_two_concurrent_recovery_attempts_only_one_succeeds(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'DB_PATH',tmp_path/'db')
    with m.db() as con:
        con.execute('CREATE TABLE users(id INTEGER,totp_secret TEXT,recovery_codes_hash TEXT,updated_at TEXT)')
        con.execute("INSERT INTO users VALUES (1,'',?,'')",(m._recovery_hashes(['ONE']),))
    outcomes=[];barrier=threading.Barrier(2)
    def verify():
        barrier.wait();outcomes.append(m._verify_totp_or_recovery({'id':1},'ONE'))
    threads=[threading.Thread(target=verify) for _ in range(2)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(3)
    assert sorted(outcomes)==[False,True]


def test_http_delete_checks_owner_before_touching_files(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m,'DB_PATH',tmp_path/'db')
    monkeypatch.setattr(m,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(m,'_users_exist',lambda:True)
    monkeypatch.setattr(m,'_session_user',lambda request:dict(id=1,role='user',must_change_password=0,mfa_enabled=0,csrf_token='test'))
    attachment=tmp_path/'owned-by-2';attachment.write_text('keep')
    with m.db() as con:
        con.executescript('CREATE TABLE devices(id INTEGER,owner_user_id INTEGER);CREATE TABLE attachments(device_id INTEGER,stored_name TEXT);')
        con.execute('INSERT INTO devices VALUES (42,2)');con.execute('INSERT INTO attachments VALUES (42,?)',(attachment.name,))
    client=TestClient(m.app)
    try:
        response=client.post('/devices/42/delete',headers={'Origin':'http://testserver'},follow_redirects=False)
        assert response.status_code==303
    finally:client.close()
    with m.db() as con:assert con.execute('SELECT COUNT(*) FROM attachments').fetchone()[0]==1
    assert attachment.read_text()=='keep'


def test_incomplete_updater_snapshot_never_replaces_live_files(tmp_path):
    import subprocess
    text=(ROOT/'update.sh').read_text()
    restore=text.split('restore_existing() {',1)[1].split('\nfinish_update()',1)[0]
    # Real restore function, with host commands stubbed; only temporary files.
    live=tmp_path/'live';live.mkdir();(live/'keep').write_text('original')
    backup=tmp_path/'backup';(backup/'app').mkdir(parents=True);(backup/'app'/'partial').write_text('partial')
    script='''set -eu
systemctl() { return 0; }
id() { return 1; }
APP_DIR="$1"; BACKUP_DIR="$2"; SERVICE=fake; SERVICE_USER=fake
SNAPSHOT_READY=0; LIVE_CHANGED=0
restore_existing() {'''+restore+'\nrestore_existing\n'
    subprocess.run(['bash','-c',script,'audit',str(live),str(backup)],check=True,capture_output=True)
    assert (live/'keep').read_text()=='original' and not (live/'partial').exists()


def test_updater_exit_guard_handles_explicit_exit(tmp_path):
    import subprocess
    text=(ROOT/'update.sh').read_text()
    guard='finish_update() {'+text.split('finish_update() {',1)[1].split('\ntrap finish_update EXIT',1)[0]
    marker=tmp_path/'rollback-called'
    script='set -eu\nrestore_existing() { touch "$1"; }\n'+guard.replace('restore_existing || true','restore_existing "$MARKER" || true')+'\nMARKER="$1"\ntrap finish_update EXIT\nexit 23\n'
    result=subprocess.run(['bash','-c',script,'audit',str(marker)],capture_output=True)
    assert result.returncode==23 and marker.exists()


def test_document_download_stops_at_size_limit_and_closes():
    from app.http_fetch import get
    from types import SimpleNamespace
    closed=[]
    response=SimpleNamespace(headers={},raise_for_status=lambda:None,iter_content=lambda **kw:iter([b'abcd',b'efgh']),close=lambda:closed.append(True))
    with pytest.raises(ValueError,match='limit'):
        get(SimpleNamespace(get=lambda *a,**kw:response),'https://example.com',max_bytes=5)
    assert closed==[True]


def test_document_download_preserves_response_content():
    from app.http_fetch import get
    from types import SimpleNamespace
    import requests
    response=requests.Response();response.status_code=200;response._content=b'firmware';response._content_consumed=True
    response.iter_content=lambda **kw:iter([b'firm',b'ware'])
    result=get(SimpleNamespace(get=lambda *a,**kw:response),'https://example.com',max_bytes=8)
    assert result.content==b'firmware' and result.text=='firmware'


def test_explicit_historical_firmware_confirmation_stays_green():
    device=dict(vendor='Example',model='Camera',firmware_provider='Auto',firmware_url='',lifecycle='End of Support',
                latest_firmware='1.0',current_firmware='1.0',release_date='',release_summary='',release_notes_url='',
                confidence='Manual',firmware_source='Manual',check_method='Manual')
    assert m._check_device_provider(device)['status']=='ok'


def test_real_schema_and_http_create_keep_existing_navigation(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m,'DB_PATH',tmp_path/'db')
    monkeypatch.setattr(m,'_available_device_profile',lambda *args,**kwargs:None)
    m.init_db()
    with m.db() as con:
        con.execute("INSERT INTO users(id,username,password_hash,role,created_at,updated_at) VALUES (1,'audit','unused','user','now','now')")
    monkeypatch.setattr(m,'_session_user',lambda request:dict(id=1,role='user',must_change_password=0,mfa_enabled=0,csrf_token='test'))
    client=TestClient(m.app)
    try:
        response=client.post('/devices',data={'display_name':'Audit camera','category':'Other'},headers={'Origin':'http://testserver'},follow_redirects=False)
        assert response.status_code==303
        with m.db() as con:
            row=con.execute("SELECT * FROM devices WHERE display_name='Audit camera'").fetchone()
        assert row['owner_user_id']==1
        assert response.headers['location']==f"/devices/{row['id']}?created=device"
    finally:client.close()
