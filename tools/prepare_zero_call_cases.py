"""Zero-live-call Chinese source correction with explicit test provenance."""
import argparse,copy,json,sys,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True);ap.add_argument("--samples",required=True);ap.add_argument("--font",required=True)
    a=ap.parse_args();repo=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(repo/"skills/commercial-visual-production-v3-1-0/scripts"))
    import workflow as w,production as prod,materialize as mat,checks
    from _workflow import create,load,atomic,active
    from blueprint import preview
    root=Path(a.out).resolve();src=Path(a.samples).resolve();create(root,"chinese-source-zero-call",True,1,editor_backend=None)
    for p in src.glob("*.png"):shutil.copyfile(p,root/p.name)
    shutil.copyfile(src/"export/merged_preview.png",root/"reference.png")
    brief="TEST ONLY: repair 我们的产吕 to 我们的产品; preserve all other content and pixels."
    (root/"request.txt").write_text(brief,encoding="utf-8")
    modules=[
        ("observed","扁平几何图形与栅格文字，未观察到摄影质感。"),
        ("observed","大标题位于左上，主体居中偏下，左下圆环与右上弧线平衡画面。"),
        ("observed","可见圆角轮廓与独立几何边缘；不从外观推断实际制作软件。"),
        ("estimated","大面积深青绿色、米白主体、金色辅助；面积比例为视觉估计。"),
        ("unknown","可见中文无衬线字形与字号层级；仅凭参考不确定字体家族。"),
        ("observed","主要是平涂，右下三角形呈半透明叠加效果。"),
        ("observed","弧线、产品和圆环形成上下与前后关系，未见明显透视场景。"),
        ("observed","白弧、金色圆环和半透明三角形作为装饰。"),
        ("observed","标题的尺度与明度先吸引视线，再连接主体和两侧装饰；仅总结参考。")]
    obs=[dict(id="o"+str(i),module=i,certainty=c,text=t,evidence_file="reference.png")
         for i,(c,t) in enumerate(modules,1)]
    draft=dict(original_input="先只记录第4项色彩判断，其他项尚未分析",observation=obs[3],
               status="DRAFT_ONLY",not_a_stage=True)
    atomic(root/"input-draft.json",draft)
    before=load(root)["seq"]
    try:w.perform(root,"stage",dict(stage="R0",data=dict(references=[dict(path="reference.png",role="layout")],observations=[obs[3]])))
    except ValueError:single_blocked=True
    else:single_blocked=False
    atomic(root/"single-input-result.json",dict(blocked=single_blocked,state_unchanged=before==load(root)["seq"]))
    w.perform(root,"stage",dict(stage="R0",data=dict(references=[dict(path="reference.png",role="layout")],observations=obs)))
    w.perform(root,"asset",dict(id="product",path="product-original.png",role="product",
        description="Observed synthetic rounded product fixture",description_source="observed"))
    decisions=[dict(observation_id=o["id"],decision="reject" if o["certainty"]=="unknown" else "adapt",
                    reason="Keep uncertainty explicit; use only selected visual characteristics in this test") for o in obs]
    r1=dict(purpose="TEST ONLY Chinese source correction",asset_roles=["product"],decisions=decisions)
    w.perform(root,"stage",dict(stage="R1",data=r1,evidence_files=["request.txt"]))
    bp=json.loads((src/"spec.json").read_text(encoding="utf-8"))
    for e in bp["elements"]:
        e["role"]={"product-original":"product","logo-original":"logo","headline-raster":"headline"}.get(e["id"],e["role"])
    bp["editable_regions"]=[dict(id="title-only",rect=[.08,.13,.76,.30])]
    bp["protected_regions"]=[dict(id="product",rect=[.38,.39,.65,.80]),dict(id="logo",rect=[.08,.04,.36,.10])]
    bad=Image.new("RGBA",(1024,1536),(0,0,0,0));d=ImageDraw.Draw(bad)
    d.text((100,225),"我们的产吕",font=ImageFont.truetype(a.font,70),fill="white")
    d.text((100,330),"我们坚持产品的高品质，",font=ImageFont.truetype(a.font,34),fill="white")
    d.text((100,385),"全力打造天然、健康产品。",font=ImageFont.truetype(a.font,34),fill="white")
    bad.save(root/"headline-bad.png")
    next(e for e in bp["elements"] if e["id"]=="headline-raster")["source"]="headline-bad.png"
    atomic(root/"bad-spec.json",bp);preview(bp,root,(1024,1536),[]).save(root/"bad-preview.png")
    w.perform(root,"stage",dict(stage="R2",data=dict(creative_input=dict(kind="text",text=brief),
        spec="bad-spec.json",preview="bad-preview.png"),evidence_files=["request.txt"]))
    w.perform(root,"requirement",dict(id="copy",scope="headline-raster",property="copy",
        text="我们的产品\n我们坚持产品的高品质，全力打造天然、健康产品。",
        verification="Manual character-by-character and source comparison",method="composite",
        source=dict(kind="test",quote=brief),evidence_files=["request.txt"]))
    decision=dict(actor="test",reason="Explicit synthetic fixture decision; not commercial approval",evidence_files=["request.txt"])
    w.perform(root,"confirm-blueprint",decision)
    prod.action(root,"prepare",dict(id="synthetic-bg",kind="background",goal="Synthetic raster background; no image service"))
    j=load(root)["jobs"]["synthetic-bg"]
    args=json.loads((root/j["tool_args_file"]).read_text(encoding="utf-8"))
    prod.action(root,"begin",dict(job_id=j["id"],tool_args=args,inspected_images=[],
        intent_review=dict(covered_requirement_ids=list(j["coverage"]),unresolved=[],
                           observation="TEST ONLY simulation of the image adapter; no real call")))
    prod.action(root,"finish",dict(job_id=j["id"],output="background.png",
        tool_metadata=dict(fixture=True,not_a_live_call=True)))
    v1=mat.materialize(root,j["id"]);v1["id"]="bad-copy";w.perform(root,"revision",v1)
    checks.action(root,"run",dict(revision="bad-copy"))
    w.perform(root,"review",dict(revision="bad-copy",check_id="req:copy",status="FAIL",actor="test",
        observation="Injected fixture has 吕 where the required title has 品",evidence_files=[v1["image"]]))
    w.perform(root,"issue",dict(id="copy-error",revision="bad-copy",check_id="req:copy",severity="P1",
        expected="我们的产品",actual="我们的产吕",scope="headline-raster"))
    fixed=json.loads((root/v1["spec"]).read_text(encoding="utf-8"))
    next(e for e in fixed["elements"] if e["id"]=="headline-raster")["source"]="headline-raster.png"
    atomic(root/"fixed-spec.json",fixed);preview(fixed,root,(1024,1536),[]).save(root/"fixed-preview.png")
    w.perform(root,"stage",dict(stage="R2",data=dict(creative_input=dict(kind="text",text=brief),
        spec="fixed-spec.json",preview="fixed-preview.png"),evidence_files=["request.txt"]))
    w.perform(root,"confirm-blueprint",decision)
    ids=[x["id"] for x in active(load(root))]
    before=load(root)["calls_used"]
    prod.action(root,"prepare-source",dict(id="source-repair",baseline="bad-copy",spec="fixed-spec.json",
        goal="Repair one raster title character only",layer_updates=["headline-raster"],
        intent_review=dict(covered_requirement_ids=ids,unresolved=[],observation=brief)))
    w.perform(root,"repair",dict(issue_id="copy-error",job_id="source-repair",baseline="bad-copy"))
    v2=mat.materialize(root,"source-repair");v2["id"]="correct-copy";w.perform(root,"revision",v2)
    w.perform(root,"submit-repair",dict(issue_id="copy-error",revision="correct-copy"))
    checks.action(root,"run",dict(revision="correct-copy"))
    summary=dict(real_image_tool_calls=0,simulated_begin_events=load(root)["calls_used"],
        source_repair_added_begin_events=load(root)["calls_used"]-before,
        issue_status=load(root)["issues"]["copy-error"]["status"],
        measurements=load(root)["checks"]["correct-copy"]["non_target"]["detail"],
        bad_image=v1["image"],correct_image=v2["image"],
        semantic_review="PENDING_AGENT_REVIEW; no fabricated PASS or user acceptance")
    atomic(root/"CASE_RESULT.json",summary);print(json.dumps(summary))
if __name__=="__main__":main()
