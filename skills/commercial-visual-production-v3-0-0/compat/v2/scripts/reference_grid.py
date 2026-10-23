#!/usr/bin/env python3
"""Add a true normalized-coordinate grid to a reference image for measured layout annotation."""
import argparse,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--steps',type=int,default=10,help='Grid cells per axis, 2..40')
    ap.add_argument('--opacity',type=int,default=155)
    args=ap.parse_args()
    if not 2<=args.steps<=40 or not 20<=args.opacity<=255:ap.error('steps must be 2..40 and opacity 20..255')
    with Image.open(args.image) as im: rgba=im.convert('RGBA')
    w,h=rgba.size
    layer=Image.new('RGBA',(w,h),(0,0,0,0))
    d=ImageDraw.Draw(layer,'RGBA')
    try: font=ImageFont.truetype('DejaVuSans.ttf',max(10,min(w,h)//50))
    except Exception:font=ImageFont.load_default()
    for i in range(args.steps+1):
        x=round(i*w/args.steps);y=round(i*h/args.steps)
        d.line((x,0,x,h),fill=(255,255,255,args.opacity),width=2)
        d.line((0,y,w,y),fill=(255,255,255,args.opacity),width=2)
        if i<args.steps:
            d.text((max(0,x+3),2),f'x={i/args.steps:.2f}',font=font,fill='white',stroke_width=1,stroke_fill='black')
            d.text((2,max(0,y+4)),f'y={i/args.steps:.2f}',font=font,fill='white',stroke_width=1,stroke_fill='black')
    rgba=Image.alpha_composite(rgba,layer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    rgba.save(args.out)
    print(f'PASS: grid={args.steps}x{args.steps} size={w}x{h} output={args.out}. Labels are image-normalized coordinates; not automatic semantic detection.')
    return 0
if __name__=='__main__':sys.exit(main())
