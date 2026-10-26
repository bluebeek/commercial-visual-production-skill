#!/usr/bin/env python3
"""Geometry-only audit using explicitly annotated object positions, not AI image recognition."""
import argparse,sys,json,math
from pathlib import Path
from _compact import emit_result
from _common import load_project,validate_project,parse_box,evaluate_constraint,area
from _evidence import save_report,project_inputs,digest
from PIL import Image

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--spec',required=True,type=Path)
    ap.add_argument('--observed',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--image',type=Path,help='Actual candidate image that was annotated')
    ap.add_argument('--full-output',action='store_true',help='Print full report instead of compact summary')
    args=ap.parse_args()
    project,root=load_project(args.spec)
    preflight,expected=validate_project(project,root)
    if preflight['status']=='BLOCK':ap.error('invalid blueprint: '+'; '.join(preflight['errors']))
    obsdata=json.loads(args.observed.read_text(encoding='utf-8'))
    if not isinstance(obsdata,dict):ap.error('observed must be a JSON object')
    if not args.image or not args.image.is_file():ap.error('--image is required; planned boxes alone are not observations')
    if obsdata.get('image_sha256')!=digest(args.image):ap.error('observed.image_sha256 must match the annotated image')
    if obsdata.get('annotation_method') not in ('manual','vision-assisted') or not obsdata.get('source'):ap.error('record annotation_method and source evidence')
    with Image.open(args.image) as image:
        if image.size!=(project['canvas']['width'],project['canvas']['height']):ap.error('annotated image size differs from blueprint')
    obs=obsdata.get('boxes',{})
    observed={}; rows=[]; failures=0; unknown=0
    elems={el['id']:el for el in project['elements']}
    for eid,el in elems.items():
        planned=expected[eid]
        if eid not in obs:
            rows.append({'element':eid,'result':'UNKNOWN','reason':'not annotated; no automatic recognition'})
            unknown+=1; continue
        if obs[eid] is None:
            result='BLOCK' if el.get('required',True) else 'UNKNOWN'
            rows.append({'element':eid,'result':result,'reason':'explicitly marked missing'})
            if result=='BLOCK':failures+=1
            else:unknown+=1
            continue
        try: actual=parse_box(obs[eid],f'observed.{eid}')
        except Exception as ex:
            rows.append({'element':eid,'result':'BLOCK','reason':str(ex)});failures+=1;continue
        observed[eid]=actual
        dx=abs((planned[0]+planned[2]/2)-(actual[0]+actual[2]/2))
        dy=abs((planned[1]+planned[3]/2)-(actual[1]+actual[3]/2))
        dw=abs(planned[2]-actual[2]);dh=abs(planned[3]-actual[3])
        pos_tol=float(el.get('position_tolerance',0.04))
        size_tol=float(el.get('size_tolerance',0.06))
        cw,ch=project['canvas']['width'],project['canvas']['height']
        pos_px=el.get('position_tolerance_px');size_px=el.get('size_tolerance_px')
        if pos_px is not None:ok_pos=dx*cw<=float(pos_px) and dy*ch<=float(pos_px)
        else:ok_pos=max(dx,dy)<=pos_tol
        if size_px is not None:ok_size=dw*cw<=float(size_px) and dh*ch<=float(size_px)
        else:ok_size=max(dw,dh)<=size_tol
        ok=ok_pos and ok_size
        rows.append({'element':eid,'result':'PASS' if ok else 'BLOCK','center_error':[round(dx,4),round(dy,4)],'size_error':[round(dw,4),round(dh,4)],'position_tolerance':pos_tol,'size_tolerance':size_tol})
        failures+=int(not ok)
    constraints=[]
    for i,c in enumerate(project.get('constraints',[])):
        res,detail=evaluate_constraint(c,observed)
        state='UNKNOWN' if res is None else ('PASS' if res else 'BLOCK')
        constraints.append({'id':c.get('id',f'constraint_{i}'),'type':c['type'],'result':state,'detail':detail})
        failures+=int(state=='BLOCK'); unknown+=int(state=='UNKNOWN')
    status='BLOCK' if failures else ('UNKNOWN' if unknown else 'PASS')
    report={'status':status,'meaning':'Geometry-only. Does NOT confirm facial identity, typography quality, brand fidelity or aesthetics.','annotation_source':obsdata.get('source','unspecified'), 'elements':rows, 'constraints':constraints,'failures':failures,'unknowns':unknown}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    inputs=project_inputs(project,root,args.spec);inputs.update(observed=args.observed,image=args.image)
    save_report(args.out,'layout_audit',report,inputs)
    emit_result(report,args.out,args.full_output)
    return 2 if status=='BLOCK' else 3 if status=='UNKNOWN' else 0
if __name__=='__main__':sys.exit(main())
