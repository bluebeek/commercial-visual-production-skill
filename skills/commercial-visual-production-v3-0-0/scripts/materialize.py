"""Materialize an actual generated result into source layers, without overwriting a revision."""
import argparse,copy,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
from _workflow import *
from _common import load_project,mask_for_regions
from production import validate_job
from checks import run_script
from export_layers import layer_for
from _images import srgb_bytes

def materialize(root,job_id,target_element=None):
    root=Path(root).resolve();s=load(root);j=s['jobs'][job_id]
    if j['status'] not in ('generated','source_ready') or not fresh(root,j['output_files']):raise WorkflowError('actual unmodified generated result required')
    validate_job(s,root,j,False)
    folder=root/'production'/job_id/'materialized';folder.mkdir(parents=True,exist_ok=False)
    p,base=load_project(local(root,j['spec']));p=copy.deepcopy(p);w,h=p['canvas']['width'],p['canvas']['height']
    # Project-local sources remain usable when the new spec is written in a version directory.
    for e in p['elements']:
        if e.get('source'):e['source']=(base/e['source']).relative_to(root).as_posix()
    updates=[]
    if j['kind'] in ('local-edit','compose-repair'):
        baseline=s['revisions'][j.get('restoration_base') or j['baseline']]
        if j.get('application_regions'):p['editable_regions']=j['application_regions']
        applyspec=root/('apply-'+job_id+'.json');atomic(applyspec,p)
        lock=folder/'locked.png'
        run_script('locked_edit.py',['--spec',applyspec,'--baseline',local(root,baseline['image']),'--candidate',local(root,j['output']),'--out',lock,'--feather',j.get('feather',0)])
        mask=mask_for_regions(p.get('editable_regions',[]),w,h)
        with Image.open(lock) as im:arr=np.asarray(im.convert('RGBA')).copy()
        patch=np.zeros_like(arr);patch[mask]=arr[mask]
        patchfile=folder/'patch.png';Image.fromarray(patch).save(patchfile)
        eid='patch-'+job_id
        p['elements'].append({'id':eid,'role':'decoration','box':[0,0,1,1],'lock':'L3','z':max([e.get('z',0) for e in p['elements']]+[0])+1,
                              'source':patchfile.relative_to(root).as_posix(),'provenance':'raster_patch','description':'局部栅格补丁，不是重建的完整背景或原生文字层'})
        updates=[{'element':eid,'method':'raster_patch','regions':p.get('editable_regions',[]),'restoration_scope':j['editable_regions'],'feather':j.get('feather',0),'source':j['output']}]
    elif j['kind']=='source-edit':
        updates=[{'element':eid,'method':'native_source_replace','source':next(e['source'] for e in p['elements'] if e['id']==eid)} for eid in j['layer_updates']]
    else:
        targets=[e for e in p['elements'] if e['id']==target_element] if target_element else [e for e in p['elements'] if e.get('role')=='background']
        if len(targets)!=1:raise WorkflowError('choose exactly one planned target_element')
        e=targets[0]
        if e.get('lock') in ('L0','L1'):raise WorkflowError('cannot replace protected original with generated output')
        e['source']=j['output'];e['description']='生成素材；'+('完整候选的栅格层，不保证语义分层' if j['kind']=='whole' else j['goal'])
        updates=[{'element':e['id'],'method':'generated_raster','source':j['output']}]
    # Save each spec at project root so all source references stay confined and portable.
    specname='spec-'+job_id+'.json'
    if (root/specname).exists():raise WorkflowError('spec already exists')
    atomic(root/specname,p)
    composite=Image.new('RGBA',(w,h),p['canvas'].get('background','#FFFFFF'))
    for e in sorted(p['elements'],key=lambda x:x.get('z',0)):
        if e.get('source'):composite.alpha_composite(layer_for(e,root,w,h,p.get('color_management',{}).get('assume_untagged_srgb',False)))
    if j['kind'] in ('local-edit','compose-repair'):
        with Image.open(folder/'locked.png') as locked:
            if composite.tobytes()!=locked.convert('RGBA').tobytes():raise WorkflowError('patch cannot exactly reconstruct locked image; requires another native layer strategy')
    if j['kind']=='source-edit':
        with Image.open(local(root,s['revisions'][j['baseline']]['image'])) as old:
            a=np.asarray(composite);b=np.asarray(old.convert('RGBA'));allowed=mask_for_regions(j['editable_regions'],w,h)
            if a.shape!=b.shape or np.any(a[~allowed]!=b[~allowed]):raise WorkflowError('native source edit changed outside explicit scope')
    image=folder/'candidate.png';composite.save(image,icc_profile=srgb_bytes())
    output=bind(root,[specname,image.relative_to(root)]+[e['source'] for e in p['elements'] if e.get('source')])
    report={'schema':'cvisual.materialization.v3','job_id':job_id,'parent':j['baseline'],'image':image.relative_to(root).as_posix(),'spec':specname,
            'input_files':{**j['input_files'],**j['output_files']},'output_files':output,'layer_updates':updates,
            'execution_kind':j.get('execution_kind','image_generation'),'implementation':{'materialize.py':sha(__file__),'locked_edit.py':sha(Path(__file__).with_name('locked_edit.py'))}}
    atomic(folder/'materialization.json',report)
    return {'materialization':(folder/'materialization.json').relative_to(root).as_posix(),**{k:report[k] for k in ('image','spec','parent','layer_updates')},'job_id':job_id}

def main():
    a=argparse.ArgumentParser();a.add_argument('--project',required=True,type=Path);a.add_argument('--job',required=True);a.add_argument('--target-element');o=a.parse_args()
    try:print(dump(materialize(o.project,o.job,o.target_element)));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
