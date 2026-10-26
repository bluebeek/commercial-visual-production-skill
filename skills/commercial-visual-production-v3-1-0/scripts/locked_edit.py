#!/usr/bin/env python3
"""Hard-lock compositing: output outside editable mask is pixel-identical to baseline."""
import argparse,sys,json
from pathlib import Path
from _compact import emit_result
import numpy as np
from PIL import Image
from _common import load_project,validate_project,mask_for_regions,protection_mask
from _evidence import save_report,project_inputs
from _images import rgba_image,srgb_bytes

def main():
    ap=argparse.ArgumentParser(description='Composite AI candidate only into editable regions while preserving baseline pixels elsewhere.')
    ap.add_argument('--baseline',required=True,type=Path)
    ap.add_argument('--candidate',required=True,type=Path)
    ap.add_argument('--spec',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--feather',type=int,default=0,help='Inner-edge blend width (pixels) without changing outside mask')
    ap.add_argument('--full-output',action='store_true',help='Print full report instead of compact summary')
    args=ap.parse_args()
    if args.feather<0 or args.feather>200: ap.error('feather must be between 0 and 200')
    project,root=load_project(args.spec)
    report,boxes=validate_project(project,root)
    if report['status']=='BLOCK': ap.error('preflight BLOCK: '+'; '.join(report['errors']))
    if not project.get('editable_regions'): ap.error('no editable regions; refusing unrestricted replacement')
    try:
        with Image.open(args.baseline) as f: saved_icc=f.info.get('icc_profile'); saved_dpi=f.info.get('dpi')
        base,_=rgba_image(args.baseline)
        with Image.open(args.candidate) as f:candidate_icc=f.info.get('icc_profile')
        assume=project.get('color_management',{}).get('assume_untagged_srgb',False)
        if bool(saved_icc)!=bool(candidate_icc) and not assume:ap.error('baseline/candidate ICC tagging differs; explicitly define an untagged sRGB assumption')
        # Keep baseline bytes untouched; convert only the candidate to baseline's space.
        target=saved_icc or (srgb_bytes() if candidate_icc else None)
        cand,_=rgba_image(args.candidate,target,assume)
    except Exception as ex: ap.error(f'cannot open image: {ex}')
    if base.size!=cand.size: ap.error(f'images not aligned: baseline {base.size}, candidate {cand.size}; no auto resizing')
    if base.size!=(project['canvas']['width'],project['canvas']['height']): ap.error('images do not match blueprint canvas')
    w,h=base.size
    mask=mask_for_regions(project.get('editable_regions',[]),w,h)
    lock=protection_mask(project,root,w,h)
    if (mask & lock).any(): ap.error('editable area overlaps protected mask')
    if not mask.any(): ap.error('editable mask empty')
    b=np.asarray(base,dtype=np.uint8); c=np.asarray(cand,dtype=np.uint8)
    if args.feather==0:
        out=b.copy(); out[mask]=c[mask]
    else:
        try:
            from scipy.ndimage import distance_transform_edt
            dist=distance_transform_edt(mask)
            alpha=np.minimum(1,dist/(args.feather+1.0))[:,:,None]
        except ImportError:
            from PIL import ImageFilter
            # Feather only within the editable selection; never blur baseline or extend the selection.
            blurred=Image.fromarray(mask.astype('uint8')*255).filter(ImageFilter.GaussianBlur(args.feather))
            alpha=np.clip((np.asarray(blurred,dtype=float)/255-.5)*2,0,1)[:,:,None]
        out=b.copy()
        out[mask]=np.rint(b[mask]*(1-alpha[mask])+c[mask]*alpha[mask]).astype(np.uint8)
    # Invariant: all pixels outside editable mask must match exactly, even alpha.
    changed_out=int(np.count_nonzero(np.any(out[~mask]!=b[~mask],axis=1)))
    changed_protected=int(np.count_nonzero(np.any(out[lock]!=b[lock],axis=1)))
    if changed_out or changed_protected: ap.error('internal invariant failed, refusing to save')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    opts={}
    if target: opts['icc_profile']=target
    elif saved_icc: opts['icc_profile']=saved_icc
    if saved_dpi: opts['dpi']=saved_dpi
    Image.fromarray(out,mode='RGBA').save(args.out,format='PNG',**opts)
    out_report={
        'status':'PASS','guarantee':'decoded RGBA pixels outside editable mask are identical to baseline',
        'limits':'No automatic identity/style/edge seam/commercial quality check; same-size aligned inputs required',
        'pixel_dimensions':[w,h], 'editable_pixels':int(mask.sum()),
        'protected_pixels':int(lock.sum()),
        'changed_outside_editable':changed_out,'changed_in_protected':changed_protected,
        'changed_inside_editable':int(np.count_nonzero(np.any(out[mask]!=b[mask],axis=1))),
        'feather_inside_mask':args.feather,
        'baseline':str(args.baseline),'candidate':str(args.candidate),'output':str(args.out),
        'color_management':'candidate converted to baseline space' if target else 'both untagged; encoded values only, not brand-color verification'
    }
    report_path=args.out.with_suffix('.report.json')
    inputs=project_inputs(project,root,args.spec);inputs.update(baseline=args.baseline,candidate=args.candidate)
    save_report(report_path,'locked_edit',out_report,inputs,{'locked':args.out})
    emit_result(out_report,report_path,args.full_output)
    return 0
if __name__=='__main__':sys.exit(main())
