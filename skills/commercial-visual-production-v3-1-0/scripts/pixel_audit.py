#!/usr/bin/env python3
"""Audit declared flat-color/whitespace regions using exact decoded RGB samples."""
import argparse,sys,json
from pathlib import Path
from _compact import emit_result
from PIL import Image
import numpy as np
from _common import load_project,validate_project,mask_for_regions
from _evidence import save_report,project_inputs
from _images import rgba_image,srgb_bytes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--spec',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--full-output',action='store_true',help='Print full report instead of compact summary')
    args=ap.parse_args()
    project,root=load_project(args.spec)
    preflight,_=validate_project(project,root)
    if preflight['status']=='BLOCK':ap.error('invalid blueprint: '+'; '.join(preflight['errors']))
    checks=project.get('color_checks',[])
    if not checks:
        result={'status':'UNKNOWN','reason':'no color_checks defined in blueprint; cannot infer exact brand colors from stylistic references','checks':[]}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        inputs=project_inputs(project,root,args.spec);inputs['image']=args.image
        save_report(args.out,'pixel_audit',result,inputs)
        emit_result(result,args.out,args.full_output)
        return 3
    with Image.open(args.image) as im:
        if im.size != (project['canvas']['width'],project['canvas']['height']):ap.error('image dimensions do not match blueprint')
        icc=bool(im.info.get('icc_profile'))
    assume=project.get('color_management',{}).get('assume_untagged_srgb',False)
    inputs=project_inputs(project,root,args.spec);inputs['image']=args.image
    if not icc and not assume:
        result={'status':'UNKNOWN','reason':'untagged image: explicitly set color_management.assume_untagged_srgb=true or supply managed sRGB input','checks':[]}
        save_report(args.out,'pixel_audit',result,inputs)
        emit_result(result,args.out,args.full_output);return 3
    rgba,_=rgba_image(args.image,srgb_bytes(),assume)
    pixels=np.asarray(rgba,dtype=np.uint8);rgb=pixels[:,:,:3]
    findings=[]
    for i,c in enumerate(checks):
        name=c.get('id',f'check_{i}')
        col=c.get('expected_hex','')
        if len(col)!=7 or not col.startswith('#'):
            ap.error(f'{name}: requires #RRGGBB expected_hex')
        try: target=np.array([int(col[k:k+2],16) for k in [1,3,5]],dtype=np.int16)
        except ValueError:ap.error(f'{name}: invalid target hex')
        tolerance=int(c.get('tolerance',3))
        min_ratio=float(c.get('min_match_ratio',0.98))
        if not 0<=tolerance<=255 or not 0<=min_ratio<=1:ap.error(f'{name}: bad tolerance or min_match_ratio')
        selection=mask_for_regions([c],rgb.shape[1],rgb.shape[0])
        pix=rgb[selection].astype(np.int16)
        if len(pix)==0:ap.error(f'{name}: empty region')
        delta=np.max(np.abs(pix-target),axis=1)
        ratio=float(np.mean(delta<=tolerance))
        nonopaque=int(np.count_nonzero(pixels[:,:,3][selection]!=255))
        passed=ratio>=min_ratio and nonopaque==0
        findings.append({'id':name,'status':'PASS' if passed else 'BLOCK','nonopaque_pixels':nonopaque,'target_hex':col,'pixels':int(len(pix)),'tolerance_max_RGB_channel':tolerance,'min_match_ratio':min_ratio,'actual_match_ratio':round(ratio,6),'median_observed_hex':'#'+''.join(f'{int(v):02X}' for v in np.median(pix,axis=0)), 'p95_max_delta':round(float(np.percentile(delta,95)),2),'per_channel_std':[round(float(x),2) for x in pix.std(axis=0)]})
    status='BLOCK' if any(r['status']=='BLOCK' for r in findings) else 'PASS'
    result={'status':status,'warnings':['Samples are encoded RGB values. Exact print/PANTONE matching requires properly managed ICC/proofing; this is not a colorimetric Pantone measurement.'], 'icc_profile_present':icc,'checks':findings}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    save_report(args.out,'pixel_audit',result,inputs)
    emit_result(result,args.out,args.full_output)
    return 0 if status=='PASS' else 2
if __name__=='__main__':sys.exit(main())
