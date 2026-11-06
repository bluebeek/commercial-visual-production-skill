#!/usr/bin/env python3
"""Stream raster layers to PNG/ORA; verify the composite against the saved layers."""
import argparse,json,sys,zipfile
from pathlib import Path
from _compact import emit_result
from xml.etree import ElementTree as ET
from PIL import Image
from _common import load_project,validate_project
from _evidence import save_report,project_inputs
from _images import rgba_image,srgb_bytes

def layer_for(element,root,w,h,assume_srgb=False):
    canvas=Image.new('RGBA',(w,h),(0,0,0,0))
    with Image.open(root/element['source']) as info:has_icc=bool(info.info.get('icc_profile'))
    src,_=rgba_image(root/element['source'],srgb_bytes() if has_icc else None,assume_srgb)
    x,y,bw,bh=map(float,element['box'])
    x0,y0=round(x*w),round(y*h);x1,y1=round((x+bw)*w),round((y+bh)*h)
    pw,ph=x1-x0,y1-y0
    if pw<1 or ph<1:raise ValueError('element collapses below one pixel: '+element['id'])
    scale=min(pw/src.width,ph/src.height)
    dw,dh=max(1,round(src.width*scale)),max(1,round(src.height*scale))
    if (dw,dh)!=src.size:src=src.resize((dw,dh),Image.Resampling.LANCZOS)
    px=x0+(pw-dw)//2;py=y0+(ph-dh)//2 if element.get('anchor')!='bottom' else y1-dh
    canvas.alpha_composite(src,(px,py))
    return canvas

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--allow-incomplete',action='store_true')
    ap.add_argument('--max-working-mib',type=float,default=2048)
    ap.add_argument('--approved',type=Path,help='Approved current image for R6 pixel recomposition verification')
    ap.add_argument('--full-output',action='store_true',help='Print full report instead of compact summary')
    args=ap.parse_args();proj,root=load_project(args.spec)
    preflight,_=validate_project(proj,root,'draft' if args.allow_incomplete else 'production')
    if preflight['status']=='BLOCK':ap.error('invalid blueprint: '+'; '.join(preflight['errors']))
    w,h=proj['canvas']['width'],proj['canvas']['height']
    estimate=w*h*4*5/1024**2
    if estimate>args.max_working_mib:ap.error(f'working raster estimate {estimate:.1f} MiB exceeds budget; lower canvas size or explicitly raise --max-working-mib')
    elements=sorted(proj['elements'],key=lambda e:e.get('z',0))
    missing=[];warnings=[]
    for e in elements:
        if e['role'] in ('negative_space','group'):continue
        if e['role']=='background' and not e.get('source'):continue
        if not e.get('source') or not (root/e['source']).is_file():
            if e.get('required',True):missing.append(e['id'])
        elif e['role'] in ('headline','subhead','text'):warnings.append(e['id']+': raster typography, not live editable text')
    if missing and not args.allow_incomplete:ap.error('required real assets missing: '+','.join(missing))
    args.out.mkdir(parents=True,exist_ok=True);layerdir=args.out/'layers';layerdir.mkdir(exist_ok=True)
    merged=Image.new('RGBA',(w,h),proj['canvas'].get('background','#FFFFFF'))
    records=[];outputs={}
    base=layerdir/'00_canvas.png';merged.save(base)
    records.append({'name':'canvas','path':base,'source':'data/'+base.name});outputs['layer:canvas']=base
    for e in elements:
        if e['role'] in ('group','negative_space') or not e.get('source') or not (root/e['source']).is_file():continue
        layer=layer_for(e,root,w,h,proj.get('color_management',{}).get('assume_untagged_srgb',False))
        path=layerdir/f'{len(records):02d}_{e["id"]}.png';layer.save(path)
        merged.alpha_composite(layer);layer.close()
        records.append({'name':e['id'],'path':path,'source':'data/'+path.name});outputs['layer:'+e['id']]=path
    profile=srgb_bytes()
    merged_path=args.out/'merged_preview.png';merged.save(merged_path,icc_profile=profile);merged.close()
    image=ET.Element('image',{'w':str(w),'h':str(h),'name':proj.get('project_id','Untitled'),'version':'0.0.3'})
    stack=ET.SubElement(image,'stack')
    for rec in reversed(records):
        ET.SubElement(stack,'layer',{'name':rec['name'],'src':rec['source'],'x':'0','y':'0','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over'})
    ora=args.out/'layout_layers.ora'
    with zipfile.ZipFile(ora,'w') as z:
        z.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
        z.writestr('stack.xml',ET.tostring(image,encoding='utf-8',xml_declaration=True))
        for rec in records:z.write(rec['path'],rec['source'],compress_type=zipfile.ZIP_DEFLATED)
        z.write(merged_path,'mergedimage.png',compress_type=zipfile.ZIP_DEFLATED)
    with Image.open(base) as first:recomposite=first.convert('RGBA')
    for rec in records[1:]:
        with Image.open(rec['path']) as layer:recomposite.alpha_composite(layer.convert('RGBA'))
    with Image.open(merged_path) as reference:
        if recomposite.tobytes()!=reference.convert('RGBA').tobytes():ap.error('saved-layer recomposition mismatch')
    approved_match=None
    if args.approved:
        with Image.open(args.approved) as info:tagged=bool(info.info.get('icc_profile'))
        approved,_=rgba_image(args.approved,srgb_bytes() if tagged else None,proj.get('color_management',{}).get('assume_untagged_srgb',False))
        approved_match=approved.size==recomposite.size and approved.tobytes()==recomposite.tobytes()
        approved.close()
    recomposite.close();outputs.update(merged=merged_path,ora=ora)
    report={'status':'BLOCK' if approved_match is False else ('INCOMPLETE' if missing else 'RENDERABLE'),'note':'Separate raster layers, not live typography or PSD; verify in target editor.',
            'included_layers':[r['name'] for r in records],'missing_required_assets':missing,'warnings':warnings,
            'recomposition_verified':True,'approved_composite_match':approved_match,'working_raster_estimate_mib':round(estimate,1)}
    inputs=project_inputs(proj,root,args.spec)
    if args.approved:inputs['approved']=args.approved
    save_report(args.out/'layer_export_report.json','layer_export',report,inputs,outputs)
    emit_result(report,args.out/'layer_export_report.json',args.full_output);return 2 if approved_match is False else 3 if missing else 0
if __name__=='__main__':sys.exit(main())
