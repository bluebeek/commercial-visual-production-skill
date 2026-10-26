"""Persist a synthetic workflow trace without invoking any image service."""
import argparse,json,sys,shutil
from pathlib import Path
from PIL import Image
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"skills/commercial-visual-production-v3-1-0/tests"))
    from test_workflow_v3 import Fixture,w,prod,mat,checks,load
    f=Fixture();f.setUp()
    try:
        f.generate()
        rows=[]
        for n,color in enumerate(((255,180,0,255),(220,180,90,255),(180,160,90,255)),2):
            parent="v"+str(n-1);jid="j"+str(n);rid="v"+str(n)
            j=f.prepare(jid,"local-edit",parent);f.begin(j)
            r=load(f.p)["revisions"][parent]
            with Image.open(f.p/r["image"]) as im:raw=np.asarray(im.convert("RGBA")).copy()
            raw[12:25,42:50]=color
            raw[0,0]=(255,0,255,100)
            Image.fromarray(raw).save(f.p/(jid+"-raw.png"))
            prod.action(f.p,"finish",dict(job_id=jid,output=jid+"-raw.png",
                tool_metadata={"fixture":True,"not_a_live_call":True}))
            actual=mat.materialize(f.p,jid);actual["id"]=rid
            w.perform(f.p,"revision",actual);f.all_checks(rid)
            rows.append({"revision":rid,"pixels":load(f.p)["checks"][rid]["non_target"]["detail"]})
        f.accept("v4");w.perform(f.p,"freeze",{"revision":"v4"})
        checks.action(f.p,"export",{"id":"synthetic-delivery","revision":"v4"})
        checks.action(f.p,"accept-delivery",dict(f.decision(),delivery="synthetic-delivery"))
        out=Path(a.out).resolve()
        if out.exists():raise RuntimeError("Use a new output directory")
        shutil.copytree(f.p,out)
        result={"real_image_tool_calls":0,"simulated_begin_events":load(f.p)["calls_used"],
                "fixture":True,"decisions":"test-only; not commercial acceptance",
                "review_scope":"synthetic state/measurement probes; not an independent semantic evaluation",
                "local_edits":rows,"project":str(out),
                "relocation_note":"Historical compiled attachment paths are preserved; recompile new jobs after relocation."}
        (out/"ZERO_CALL_TRACE.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result))
    finally:f.tearDown()
if __name__=="__main__":main()
