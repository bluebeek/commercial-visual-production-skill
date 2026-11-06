"""Verified project snapshots and explicit, unbound V3 imports. No credentials travel."""
import argparse, copy, hashlib, json, os, re, shutil, stat, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath
from _workflow import WorkflowError, atomic, create, load, now, objhash
from _storage import project_lock

LIMIT=512_000_000
DENIED={'.git','.env','.venv','__pycache__','.review.lock','credentials.json','api_keys.json','id_rsa'}

def safe_name(name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or any(x in ('','..','.') for x in name.split('/')):
        raise WorkflowError('unsafe archive member')
    return p

def project_files(root):
    root=Path(root).resolve();files={}
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if p.is_symlink():raise WorkflowError('project symlinks cannot be exported')
        if any(x in DENIED or x.startswith('.env.') for x in rel.parts):
            if p.name in ('.review.lock','__pycache__') or '__pycache__' in rel.parts:continue
            raise WorkflowError('credentials/environment repository must be removed from portable project')
        if not p.is_file():continue
        name=rel.as_posix();safe_name(name);data=p.read_bytes()
        if p.suffix.lower() in ('.json','.txt','.md','.yaml','.yml','.toml'):
            text=data.decode('utf-8',errors='replace')
            if re.search(r'(?:OPENAI_API_KEY|GEMINI_API_KEY)[\"\x27]?\s*[=:]\s*[\"\x27]?[A-Za-z0-9_-]{16,}|\bBearer\s+sk-[A-Za-z0-9_-]{16,}|\bAIza[A-Za-z0-9_-]{30,}',text):
                raise WorkflowError('credential-like value found; export blocked')
        files[name]=data
    if sum(map(len,files.values()))>LIMIT:raise WorkflowError('project snapshot too large')
    return files

def unresolved(state):return any(j.get('status') in ('running','result_unknown') for j in state.get('jobs',{}).values())

def export_project(root,out):
    import budget
    root=Path(root).resolve();out=Path(out).resolve()
    if out.is_relative_to(root):raise WorkflowError('snapshot output must be outside project')
    if out.exists():raise WorkflowError('snapshot output exists')
    if load(root).get('execution_lease'):budget.release(root)
    with project_lock(root):
        state=load(root)
        if unresolved(state):raise WorkflowError('unresolved image request blocks export')
        files=project_files(root)
        if 'BUNDLE_MANIFEST.json' in files:raise WorkflowError('reserved bundle manifest name in project')
        manifest={'schema':'cvisual.project.bundle.v1','project_uuid':state['project_uuid'],'at':now(),
                  'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},'execution_lease_transferred':False}
        out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
            for n,b in files.items():z.writestr(n,b)
            z.writestr('BUNDLE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return {'status':'EXPORTED','files':len(files),'project_uuid':state['project_uuid'],'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}

def import_project(archive,dest):
    archive=Path(archive).resolve();dest=Path(dest).resolve()
    if dest.exists():raise WorkflowError('destination exists; import never overwrites')
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        if len(names)!=len(set(n.casefold() for n in names)):raise WorkflowError('duplicate/case-colliding members')
        if sum(e.file_size for e in entries)>LIMIT:raise WorkflowError('archive exceeds unpacked limit')
        for e in entries:
            safe_name(e.filename)
            if stat.S_ISLNK(e.external_attr>>16):raise WorkflowError('archive symlink refused')
        if 'BUNDLE_MANIFEST.json' not in names:raise WorkflowError('missing bundle manifest')
        manifest=json.loads(z.read('BUNDLE_MANIFEST.json'))
        if manifest.get('schema')!='cvisual.project.bundle.v1' or set(names)!=(set(manifest['files'])|{'BUNDLE_MANIFEST.json'}):raise WorkflowError('bundle members do not match manifest')
        content={n:z.read(n) for n in manifest['files']}
        if any(hashlib.sha256(content[n]).hexdigest()!=h for n,h in manifest['files'].items()):raise WorkflowError('bundle content hash mismatch')
        state=json.loads(content['workflow_state.json'])
        if state.get('schema')!='cvisual.workflow.v4' or state.get('project_uuid')!=manifest['project_uuid'] or state.get('execution_lease') or unresolved(state):raise WorkflowError('invalid or still-active project snapshot')
        if any(Path(n).name in DENIED and Path(n).name!='.review.lock' for n in content):raise WorkflowError('environment material in archive')
    # Stage under the resolved destination parent; publish the complete directory atomically.
    dest.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='cvisual-import-',dir=dest.parent)).resolve()
    if not staging.is_relative_to(dest.parent):raise WorkflowError('invalid import staging location')
    for n,b in content.items():
        p=staging.joinpath(*safe_name(n).parts);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    state['execution_lease']=None
    original_state=json.loads(content['workflow_state.json'])
    archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
    atomic(staging/'.portable-import'/archive_hash/'source-state.json',original_state)
    # Keep the original decisions/history, but re-run machine/visual checks on this host.
    state['checks']={};state['master']=None
    state['host_reverification_required']=True
    for job in state['jobs'].values():
        if job.get('status')=='waiting_execution':job.update(status='cancelled',reason='project imported; refresh capabilities and recompile')
    state['seq']+=1;state['history'].append({'at':now(),'seq':state['seq'],'action':'import-portable-snapshot'})
    atomic(staging/'workflow_state.json',state)
    # Re-scan before publishing, including credential-like values and unsafe paths.
    project_files(staging)
    os.rename(staging,dest)
    return {'status':'IMPORTED_NO_EXECUTION_OWNER','project_uuid':state['project_uuid'],'requires':'bind original shared ledger; refresh catalog; prepare new jobs'}

def inspect(root):
    p=Path(root).resolve();state=json.loads((p/'workflow_state.json').read_text(encoding='utf-8'))
    if state.get('schema') not in ('cvisual.workflow.v3','cvisual.workflow.v4'):raise WorkflowError('unknown state schema')
    return {'status':'READ_ONLY','schema':state['schema'],'project_id':state['project_id'],
            'stage_ids':{k:v['id'] for k,v in state.get('stages',{}).items()},'jobs':len(state.get('jobs',{})),
            'revisions':len(state.get('revisions',{})),'state_sha256':hashlib.sha256((p/'workflow_state.json').read_bytes()).hexdigest()}

def migrate_v3(source,dest,apply=False):
    source=Path(source).resolve();dest=Path(dest).resolve()
    if dest.exists() or dest.is_relative_to(source) or source.is_relative_to(dest):raise WorkflowError('migration requires a separate new directory')
    with project_lock(source):
        old=json.loads((source/'workflow_state.json').read_text(encoding='utf-8'))
        if old.get('schema')!='cvisual.workflow.v3':raise WorkflowError('expected V3 state')
        if unresolved(old):raise WorkflowError('unresolved legacy calls must be reconciled before migration')
        files=project_files(source)
        result={'status':'DRY_RUN','approvals_imported':0,'files':len(files),'objects':{k:len(old.get(k,{})) for k in ('stages','requirements','jobs','revisions','issues','decisions')}}
        if not apply:return result
        create(dest,old['project_id'],old['test_mode'],0)
        for name,data in files.items():
            p=dest/'legacy/v3'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        state=load(dest);state['migration']={'kind':'V3_UNBOUND','at':now(),'historical_calls_used':old.get('calls_used',0),
            'objects':result['objects'],'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},'approvals_imported':0,
            'next_action':'rebind sources and R0-R2 requirements; confirm blueprint; historical state remains read-only'}
        atomic(dest/'workflow_state.json',state)
    return dict(result,status='IMPORTED_UNBOUND')

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=['inspect','export','import','migrate-v3']);a.add_argument('--project',type=Path);a.add_argument('--archive',type=Path);a.add_argument('--destination',type=Path);a.add_argument('--apply',action='store_true');o=a.parse_args()
    try:
        if o.action=='inspect':r=inspect(o.project)
        elif o.action=='export':r=export_project(o.project,o.archive)
        elif o.action=='import':r=import_project(o.archive,o.destination)
        else:r=migrate_v3(o.project,o.destination,o.apply)
        print(json.dumps(r,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as e:print(json.dumps({'status':'BLOCK','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
