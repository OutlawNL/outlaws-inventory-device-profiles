#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
import shutil
import tempfile
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT, catalog_version=None):
    schema=json.loads((root/'schemas/device-profile-v1.schema.json').read_text())
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    entries=[];files={};runtime={}
    # Complete validation before touching any previously built artifact.
    for path in sorted((root/'profiles').rglob('*.yaml')):
        data=yaml.safe_load(path.read_text(encoding='utf-8'))
        errors=sorted(validator.iter_errors(data),key=lambda e:str(list(e.path)))
        if errors:raise ValueError(f'{path}: '+ '; '.join(e.message for e in errors))
        profile_id=data['id']
        if profile_id in runtime:raise ValueError(f'Duplicate Device Profile id: {profile_id}')
        raw=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode()
        runtime[profile_id]=raw
        relative=f'catalog/profiles/{profile_id}.json';digest=hashlib.sha256(raw).hexdigest()
        files[relative]=digest
        entries.append({**{key:data[key] for key in ('schema_version','id','profile_version','origin','status','updated','device')},
            'profile_path':path.relative_to(root).as_posix(),
            'profile_url':f'https://raw.githubusercontent.com/OutlawNL/outlaws-inventory-device-profiles/main/{relative}', 'sha256':digest})
    if not entries:raise ValueError('No Device Profiles found')
    old_version=0
    if (root/'catalog/index.json').exists():old_version=int(json.loads((root/'catalog/index.json').read_text()).get('catalog_version',0))
    version=catalog_version if catalog_version is not None else max(1,old_version)
    if version<1:raise ValueError('catalog version must be >= 1')
    catalog=dict(schema_version=1,catalog_version=version,generated=str(date.today()),repository='OutlawNL/outlaws-inventory-device-profiles',profiles=entries)
    raw=(json.dumps(catalog,indent=2,ensure_ascii=False)+'\n').encode()
    files['catalog/index.json']=hashlib.sha256(raw).hexdigest()
    manifest=dict(schema_version=1,catalog_version=version,generated=catalog['generated'],files=files,signature=None,signature_status='not-signed-yet')
    stage=Path(tempfile.mkdtemp(prefix='.catalog-build-',dir=root))
    published=False;old_catalog=False;old_manifest=False;keep=False
    try:
        (stage/'catalog/profiles').mkdir(parents=True)
        for identity,content in runtime.items():(stage/f'catalog/profiles/{identity}.json').write_bytes(content)
        (stage/'catalog/index.json').write_bytes(raw)
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if (root/'manifest.json').exists():
            shutil.copy2(root/'manifest.json',stage/'previous-manifest.json');old_manifest=True
        if (root/'catalog').exists():
            (root/'catalog').replace(stage/'previous-catalog');old_catalog=True
        (stage/'catalog').replace(root/'catalog');published=True
        (stage/'manifest.json').replace(root/'manifest.json')
    except BaseException:
        try:
            if published:shutil.rmtree(root/'catalog')
            if old_catalog:(stage/'previous-catalog').replace(root/'catalog')
            if old_manifest:(stage/'previous-manifest.json').replace(root/'manifest.json')
        except BaseException:
            keep=True
            raise RuntimeError(f'Build recovery failed; original artifacts retained at {stage}')
        raise
    finally:
        if not keep:shutil.rmtree(stage,ignore_errors=True)
    return version,len(entries)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Validate all profiles before replacing the runtime catalog.')
    parser.add_argument('--catalog-version',type=int,default=None)
    args=parser.parse_args()
    version,count=build(catalog_version=args.catalog_version)
    print(f'Built catalog v{version} with {count} index entries and on-demand runtime profiles')
