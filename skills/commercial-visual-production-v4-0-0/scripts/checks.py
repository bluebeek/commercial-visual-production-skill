"""Execute real checks and export current approved PNG/ORA delivery."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
from _workflow import *
from _common import load_project,mask_for_regions,protection_mask
from _evidence import verify_report
from ora_verify import read_ora

def implementation(cid='layers'):
    names=('checks.py','_workflow.py')+{'editor':('photocraft.py','ora_verify.py','_common.py'), 'files':(), 'non_target':('_common.py',), 'layers':('ora_verify.py','export_layers.py','_common.py','_images.py','_evidence.py'), 'geometry':('layout_audit.py','_common.py','_evidence.py'), 'color':('pixel_audit.py','_common.py','_images.py','_evidence.py')}.get(cid,())
    return {n:sha(Path(__file__).parent/n) for n in names}
def run_script(name,args):
    cmd=[sys.executable,'-B','-X','utf8',str(Path(__file__).parent/name)]+list(map(str,args))
    p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=120)
    if p.returncode:raise WorkflowError(name+': '+(p.stderr or p.stdout)[-2000:])
    return p.stdout

def inspect_layers(root,revision,out):
    spec=local(root,revision['spec']);image=local(root,revision['image'])
    run_script('export_layers.py',['--spec',spec,'--out',out,'--approved',image])
    report=verify_report(out/'layer_export_report.json','layer_export',root)
    if not report.get('approved_composite_match'):raise WorkflowError('saved PNG layers differ from candidate')
    actual,names=read_ora(out/'layout_layers.ora')
    with Image.open(image) as im:
        if im.size!=actual.size or im.convert('RGBA').tobytes()!=actual.tobytes():raise WorkflowError('ORA stack differs from current image')
    if names!=report['included_layers']:raise WorkflowError('ORA layer order/name mismatch')
    return {'layers':names,'rgba_match':True,'ora_readback':True,'editor_open':'NOT_TESTED','type':'raster PNG/ORA; no live text or PSD'}

def run_checks(s,root,d):
    rid=d['revision'];r=s['revisions'][rid]
    if not rev_fresh(s,root,rid):raise WorkflowError('candidate inputs changed; register/review current revision')
    folder=root/'checks'/rid/('%08d'%(s['seq']+1));folder.mkdir(parents=True,exist_ok=False)
    base_files=dict(r['files']);checks=s['checks'][rid]
    def record(cid,status,detail,extra=None):
        report={'status':status,'detail':detail,'revision':rid,'rules_hash':rules_hash(s),'files':{**base_files,**(extra or {})},'implementation':implementation(cid),'actor':'machine','at':now()}
        report_path=folder/(cid+'.json');atomic(report_path,report)
        report['files'].update(bind(root,[report_path.relative_to(root)]));checks[cid]=report
    with Image.open(local(root,r['image'])) as im:im.load();size=im.size;mode=im.mode
    record('files','PASS',{'size':size,'mode':mode,'decoded':True})
    try:
        result=inspect_layers(root,r,folder/'layers')
        extra=bind(root,[p.relative_to(root) for p in (folder/'layers').rglob('*') if p.is_file()])
        record('layers','PASS',result,extra)
    except (ValueError,OSError) as e:record('layers','FAIL',str(e))
    if r['parent']:
        parent=s['revisions'][r['parent']]
        if not rev_fresh(s,root,r['parent'],False):raise WorkflowError('baseline files stale')
        p,base=load_project(local(root,r['spec']));w,h=size
        with Image.open(local(root,r['image'])) as im:a=np.asarray(im.convert('RGBA'))
        with Image.open(local(root,parent['image'])) as im:b=np.asarray(im.convert('RGBA'))
        if a.shape!=b.shape:raise WorkflowError('no resizing is permitted for local comparison')
        mask=mask_for_regions(r['editable_regions'],w,h);protected=protection_mask(p,base,w,h)
        if not mask.any() or (mask&protected).any():raise WorkflowError('invalid revision edit mask')
        changed=np.any(a!=b,axis=2)
        outside=int(np.count_nonzero(changed & ~mask));inside=int(np.count_nonzero(changed & mask));locked=int(np.count_nonzero(changed & protected))
        diff=np.zeros((h,w,3),dtype=np.uint8);diff[changed]=[255,90,70];Image.fromarray(diff).save(folder/'difference.png')
        extra={**parent['files'],**bind(root,[(folder/'difference.png').relative_to(root)])}
        record('non_target','PASS' if outside==0 and locked==0 else 'FAIL',{'outside_changed':outside,'protected_changed':locked,'inside_changed':inside,'meaning':'pixel protection only; target/seams/history still require actual observation'},extra)
    project,_=load_project(local(root,r['spec']))
    optional=[]
    if d.get('observed'):optional.append(('geometry','layout_audit','layout_audit.py',['--spec',local(root,r['spec']),'--image',local(root,r['image']),'--observed',local(root,d['observed'])]))
    if project.get('color_checks'):optional.append(('color','pixel_audit','pixel_audit.py',['--spec',local(root,r['spec']),'--image',local(root,r['image'])]))
    for cid,tool,script,args in optional:
        reportpath=folder/(cid+'-raw.json')
        try:
            try:run_script(script,args+['--out',reportpath])
            except WorkflowError:
                if not reportpath.is_file():raise
            actual=verify_report(reportpath,tool,root)
            bindings=[reportpath]+[(reportpath.parent/x['path']).resolve() for group in ('inputs','outputs') for x in actual.get(group,{}).values()]
            record(cid,'PASS' if actual['status']=='PASS' else 'FAIL',actual,bind(root,[x.relative_to(root) for x in bindings]))
        except (ValueError,OSError) as e:record(cid,'FAIL',str(e))
    return {'revision':rid,'checks':{k:v['status'] for k,v in checks.items()},'reports':str(folder)}

def export_delivery(s,root,d):
    from workflow import qc
    did=ident(d.get('id'));rid=d['revision'];master=s.get('master')
    if did in s['deliveries']:raise WorkflowError('delivery id immutable')
    if not master or master['revision']!=rid or not fresh(root,master['files']) or master['rules_hash']!=rules_hash(s) or qc(s,root,rid)['status']!='PASS':raise WorkflowError('delivery needs current frozen master')
    out=root/'delivery'/did;out.mkdir(parents=True,exist_ok=False)
    result=inspect_layers(root,s['revisions'][rid],out)
    editor=s['checks'][rid].get('editor',{})
    if editor.get('status')=='PASS':result.update(editor_open='PASS_ENGINE',editor_gui='NOT_TESTED',editor_backend='photocraft',editor_report=editor['detail'])
    files=bind(root,[p.relative_to(root) for p in out.rglob('*') if p.is_file()])
    rec={'id':did,'revision':rid,'status':'awaiting_acceptance','files':files,'master_files':dict(master['files']),'rules_hash':rules_hash(s),'verification':result,'implementation':implementation(),'at':now()}
    s['deliveries'][did]=rec;return rec

def accept_delivery(s,root,d):
    rec=s['deliveries'][d['delivery']]
    if not fresh(root,rec['files']) or not fresh(root,rec['master_files']) or rec['rules_hash']!=rules_hash(s) or rec['implementation']!=implementation():raise WorkflowError('delivery evidence stale')
    from workflow import qc
    if not s.get('master') or s['master']['revision']!=rec['revision'] or qc(s,root,rec['revision'])['status']!='PASS':raise WorkflowError('master changed')
    approval=user_evidence(s,root,d);approval.update(kind='delivery',subject=rec['id']);approval['files'].update(rec['files'])
    s['decisions'].append(approval);rec['status']='accepted';rec['acceptance']=approval;return rec

def action(root,name,data,expected_seq=None):
    from photocraft import verify_editor
    def operation(s,r):return {'verify-editor':verify_editor,'run':run_checks,'export':export_delivery,'accept-delivery':accept_delivery}[name](s,r,data)
    operation.__name__='checks-'+name
    return transact(root,operation,expected_seq)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['run','export','accept-delivery','verify-editor']);ap.add_argument('--project',required=True,type=Path);ap.add_argument('--input',required=True,type=Path);a=ap.parse_args()
    try:print(dump(action(a.project,a.action,json.loads(a.input.read_text(encoding='utf-8')))));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
