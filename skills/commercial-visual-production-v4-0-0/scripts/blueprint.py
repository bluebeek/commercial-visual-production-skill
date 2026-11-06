#!/usr/bin/env python3
"""Validate visual layout blueprint, draw guide, generate safe 1:1 asset mockup and edit masks."""
import argparse,json,sys
from pathlib import Path
from _compact import emit_result
from PIL import Image, ImageDraw, ImageFont,ImageColor
import numpy as np
from _common import load_project,validate_project,mask_for_regions,protection_mask
from _evidence import save_report,project_inputs
from export_layers import layer_for
from _images import srgb_bytes

COLORS = {'L0': '#F27272', 'L1':'#EDAC57','L2':'#4AADB6','L3':'#8696ED'}

def ft(size=15):
    try: return ImageFont.truetype('DejaVuSans.ttf',size)
    except Exception: return ImageFont.load_default()

def to_pixel(box,w,h):
    x,y,bw,bh=box
    return [round(x*w),round(y*h),round((x+bw)*w),round((y+bh)*h)]

def draw_guide(project,size):
    w,h=size
    guide=Image.new('RGB',(w,h),project['canvas'].get('background','#FFFFFF'))
    draw=ImageDraw.Draw(guide,'RGBA')
    small=ft(max(11,min(w,h)//55))
    for e in sorted(project['elements'],key=lambda e:e.get('z',0)):
        xy=to_pixel(e['box'],w,h)
        rgb=ImageColor.getrgb(COLORS[e.get('lock','L3')])
        if e.get('role')=='negative_space':
            draw.rectangle(xy, fill=(*rgb,22),outline=(*rgb,255),width=max(2,w//500))
        else:
            draw.rectangle(xy,fill=(*rgb,54),outline=(*rgb,255),width=max(2,w//500))
        x0,y0,x1,y1=xy
        label=f"{e['id']} | {e.get('role','?')} | {e.get('lock','L3')}"
        draw.text((x0+3,y0+3),label,font=small,fill=(255,255,255,255),stroke_width=1,stroke_fill=(0,0,0,255))
    for key,color in [('editable_regions',(0,255,85,255)),('protected_regions',(255,0,0,255))]:
        for reg in project.get(key,[]):
            if 'rect' in reg:
                x0,y0,x1,y1=reg['rect']; pts=(round(x0*w),round(y0*h),round(x1*w),round(y1*h))
                draw.rectangle(pts,outline=color,width=max(3,w//350))
            else:
                pts=[(round(x*w),round(y*h)) for x,y in reg['polygon']]
                draw.line(pts+[pts[0]],fill=color,width=max(3,w//350))
    return guide

def preview(project,root,size,warnings):
    w,h=size
    img=Image.new('RGBA',(w,h),project['canvas'].get('background','#FFFFFF'))
    d=ImageDraw.Draw(img)
    small=ft(max(11,min(w,h)//55))
    for e in sorted(project['elements'],key=lambda e:e.get('z',0)):
        if e.get('role') in ('negative_space','group'): continue
        x0,y0,x1,y1=to_pixel(e['box'],w,h)
        tw,th=x1-x0,y1-y0
        if tw<1 or th<1: continue
        if e.get('source') and (root/e['source']).exists():
            try:
                with Image.open(root/e['source']) as fh:
                    a=fh.convert('RGBA')
                if e.get('role') in ('person','coach','product','logo') and np.asarray(a.getchannel('A')).min()==255:
                    warnings.append(f'{e["id"]}: source is fully opaque; may contain unwanted rectangle background')
                a.close()
                layer=layer_for(e,root,w,h,project.get('color_management',{}).get('assume_untagged_srgb',False))
                img.alpha_composite(layer);layer.close()
            except Exception as ex:
                warnings.append(f'{e["id"]}: cannot open asset: {ex}')
        else:
            # Planned placement only; cannot invent identity or product from missing sources.
            rgb=ImageColor.getrgb(COLORS[e.get('lock','L3')]); d.rectangle([x0,y0,x1-1,y1-1],outline=(*rgb,220),width=max(2,w//500))
            d.line((x0,y0,x1,y1),fill=(*rgb,120),width=1)
            d.line((x0,y1,x1,y0),fill=(*rgb,120),width=1)
            d.text((x0+3,y0+3),e['id'],fill='white',font=small,stroke_width=1,stroke_fill='black')
    return img

def contract(project, report):
    rows=['# Production Contract · 编译输出（非图像生成结果）','','## 前置审查',f"STATUS: **{report['status']}**"]
    rows.extend(['- BLOCK: '+err for err in report['errors']])
    rows.extend(['- WARN: '+err for err in report['warnings']])
    rows+=['','## 源素材分配']
    for e in sorted(project['elements'],key=lambda e:e.get('z',0)):
        lock=e.get('lock','L3'); role=e.get('role')
        how = '原素材透明图层合成，禁止AI重绘身份/标签/文字' if lock=='L0' else '先保留原素材结构，仅修改明确授权的部分' if lock=='L1' else '可选局部生成/手动排版' if lock=='L2' else '可自由探索，仍须符合蓝图'
        rows.append(f"- `{e['id']}` ({role}, {lock}): box `{e['box']}`, z `{e.get('z',0)}`, source `{e.get('source','尚缺')}` → {how}")
    rows+=['','## 使用 Image 2.5 生成时的指令限制','1. 先按蓝图只生成允许的背景/辅助元素，不让模型重绘受保护内容。','2. 必须以实际图层或蒙版合成L0/L1素材；不能仅用其他不变承诺。','3. 若无严格区域编辑工具，将输出作为候选而非直接覆盖已确认版。','4. 按设计蓝图核对标题块、留白、主次大小、方向和几何关系。','5. 可编辑文字、准确Logo和品牌色最终由设计软件或可确定性控制的合成工具负责。']
    return '\n'.join(rows)+'\n'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--spec',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--mode',choices=['draft','production'],default='draft')
    ap.add_argument('--full-output',action='store_true',help='Print full report instead of compact summary')
    args=ap.parse_args()
    try: project,root=load_project(args.spec); report,boxes=validate_project(project,root,args.mode)
    except Exception as e: print('FAIL:',e,file=sys.stderr); return 2
    args.out.mkdir(parents=True,exist_ok=True)
    w,h=report['canvas']['width'],report['canvas']['height']
    # Fail before creating misleading guide where source data is structurally invalid.
    if report['status']=='BLOCK':
        save_report(args.out/'preflight.json','preflight',report,project_inputs(project,root,args.spec))
        emit_result(report,args.out/'preflight.json',args.full_output); return 2
    guide=draw_guide(project,(w,h))
    guide.save(args.out/'blueprint_guide.png')
    im=preview(project,root,(w,h),report['warnings']);im.save(args.out/'layout_preview.png',icc_profile=srgb_bytes())
    edit=mask_for_regions(project.get('editable_regions',[]),w,h)
    prot=protection_mask(project,root,w,h)
    Image.fromarray(edit.astype('uint8')*255,mode='L').save(args.out/'mask_editable.png')
    Image.fromarray(prot.astype('uint8')*255,mode='L').save(args.out/'mask_protected.png')
    (args.out/'production_contract.md').write_text(contract(project,report),encoding='utf-8')
    save_report(args.out/'preflight.json','preflight',report,project_inputs(project,root,args.spec),{
        'guide':args.out/'blueprint_guide.png','preview':args.out/'layout_preview.png',
        'editable_mask':args.out/'mask_editable.png','protected_mask':args.out/'mask_protected.png'})
    emit_result(report,args.out/'preflight.json',args.full_output)
    return 0
if __name__=='__main__':sys.exit(main())
