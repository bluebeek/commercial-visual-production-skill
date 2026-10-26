"""Deterministic raster/ORA fixtures; never calls an image model."""
import argparse, hashlib, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--font",required=True)
    ap.add_argument("--samples")
    a=ap.parse_args()
    repo=Path(__file__).resolve().parents[1]
    scripts=repo/"skills/commercial-visual-production-v3-0-0/scripts"
    sys.path.insert(0,str(scripts))
    from ora_verify import read_ora
    from export_layers import main as export_main
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    W,H=1024,1536
    font=lambda n:ImageFont.truetype(a.font,n)
    layers=[]
    def layer(name):
        im=Image.new("RGBA",(W,H),(0,0,0,0));layers.append((name,im));return ImageDraw.Draw(im)
    d=layer("background");d.rectangle((0,0,W,H),fill="#0B5F5C")
    d=layer("white-arc");d.arc((650,180,1110,720),50,270,fill="white",width=14)
    d=layer("product-original");d.rounded_rectangle((390,650,650,1220),40,fill="#F0EEE4");d.rectangle((440,610,600,680),fill="#B44F40");d.rectangle((410,850,630,1020),fill="#D7B56D")
    d=layer("logo-original");d.text((100,90),"TEST BRAND",font=font(34),fill="white")
    d=layer("headline-raster");d.text((100,225),"我们的产品",font=font(70),fill="white");d.text((100,330),"我们坚持产品的高品质，",font=font(34),fill="white");d.text((100,385),"全力打造天然、健康产品。",font=font(34),fill="white")
    d=layer("gold-ring");d.ellipse((100,1120,420,1440),outline="#D7B56D",width=60)
    d=layer("alpha-decoration");d.polygon([(710,1000),(940,900),(930,1320)],fill=(255,255,255,100))
    # export_layers adds its canvas, so the seven sources yield eight actual layers.
    elements=[]
    for n,(name,im) in enumerate(layers):
        f=out/(name+".png");im.save(f)
        elements.append(dict(id=name,role="background" if n==0 else "decoration",
                             source=f.name,box=[0,0,1,1],lock="L3",z=n))
    spec=dict(project_id="round2-synthetic-eight-layers",
              canvas=dict(width=W,height=H,background="#0B5F5C"),
              color_management=dict(assume_untagged_srgb=True),elements=elements)
    (out/"spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding="utf-8")
    saved=sys.argv;sys.argv=["export_layers.py","--spec",str(out/"spec.json"),"--out",str(out/"export")]
    try:rc=export_main()
    finally:sys.argv=saved
    if rc:raise RuntimeError("export failed")
    image,names=read_ora(out/"export/layout_layers.ora")
    merged=Image.open(out/"export/merged_preview.png").convert("RGBA")
    result=dict(real_image_tool_calls=0,fixture=True,layers=names,
                independent_rgba_match=image.tobytes()==merged.tobytes(),
                font_source=str(Path(a.font).resolve()),
                font_sha256=hashlib.sha256(Path(a.font).read_bytes()).hexdigest(),
                originals={})
    # Original-image comparisons use the rendered source at the approved scale,
    # rather than comparing a resized placement against unscaled camera pixels.
    if a.samples:
        s=Path(a.samples)
        for name in ("portrait","packaging"):
            src=s/(name+".jpg")
            if not src.exists():continue
            source=Image.open(src).convert("RGBA")
            source.thumbnail((700,1000),Image.Resampling.LANCZOS)
            sample=Image.new("RGBA",(W,H),"#0B5F5C")
            x=(W-source.width)//2;y=(H-source.height)//2
            sample.alpha_composite(source,(x,y))
            sample.save(out/(name+"-original-composite.png"))
            with Image.open(out/(name+"-original-composite.png")) as stored:
                actual_crop=stored.convert("RGBA").crop((x,y,x+source.width,y+source.height))
            result["originals"][name]=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                rendered_source_rgba_match=actual_crop.tobytes()==source.tobytes(),
                scope="source preservation and deterministic placement only; no identity generation")
    (out/"measurements.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
