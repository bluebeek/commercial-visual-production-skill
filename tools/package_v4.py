"""Make native skill and host-specific project bundles from one V4 core."""
import argparse, hashlib, json, sys, zipfile
from pathlib import Path

NAME='commercial-visual-production-v4-0-0'
PREFIXES={'native':NAME,'codex':'.agents/skills/'+NAME,'claude-code':'.claude/skills/'+NAME,'cursor':'.cursor/skills/'+NAME}

def sources(skill):
    files={}
    for f in sorted(skill.rglob('*')):
        if f.is_symlink():raise ValueError('skill symlinks not packaged')
        if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.pyo'):
            if f.name=='.env' or f.name.startswith('.env.') or f.name in ('credentials.json','api_keys.json'):raise ValueError('credentials not packaged')
            files[f.relative_to(skill).as_posix()]=f.read_bytes()
    if 'SKILL.md' not in files:raise ValueError('missing skill entrypoint')
    return files

def package(skill,out):
    skill=Path(skill).resolve();out=Path(out).resolve()
    if out.is_relative_to(skill):raise ValueError('package output must be outside skill')
    out.mkdir(parents=True,exist_ok=True);files=sources(skill)
    manifest={'schema':'cvisual.skill.manifest.v1','version':'4.0.0-rc.1','skill_name':NAME,
              'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
    results=[]
    for host,prefix in PREFIXES.items():
        archive=out/(NAME+'-'+host+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for n,b in files.items():
                info=zipfile.ZipInfo(prefix+'/'+n,(2026,11,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
        with zipfile.ZipFile(archive) as z:
            if set(z.namelist())!={prefix+'/'+n for n in files}:raise ValueError('archive structure mismatch')
            if any(hashlib.sha256(z.read(prefix+'/'+n)).hexdigest()!=h for n,h in manifest['files'].items()):raise ValueError('archive core mismatch')
        results.append({'host':host,'archive':archive.name,'entrypoint':prefix+'/SKILL.md',
                        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'core_match':True,'native_host_import':'NOT_TESTED'})
    (out/'V4_SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'packages.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return {'core_files':len(files),'packages':results}

def main():
    a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);o=a.parse_args()
    r=package(Path(__file__).resolve().parents[1]/'skills'/NAME,o.out);print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
