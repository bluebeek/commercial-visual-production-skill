"""Round-two zero-live-call regression probes. Fixture returns are synthetic."""
import copy
import json
from PIL import Image
from test_workflow_v3 import (
    Fixture, w, prod, checks, mat, ctx, load, active, atomic,
    transact, WorkflowError, stage_fresh
)

class RoundTwo(Fixture):
    def issue(self, severity="P1", check="target", iid="probe"):
        return w.perform(self.p, "issue", dict(
            id=iid, revision="v1", check_id=check, severity=severity,
            expected="Only the requested target changes", actual="Injected test defect",
            scope="background"))

    def review_status(self, rid, check, status):
        w.perform(self.p, "review", dict(
            revision=rid, check_id=check, status=status, actor="test",
            observation="TEST ONLY: injected " + status + " for " + check,
            evidence_files=[load(self.p)["revisions"][rid]["image"]]))

    def export_fixture(self):
        self.generate()
        self.all_checks("v1")
        self.accept("v1")
        w.perform(self.p, "freeze", {"revision":"v1"})
        checks.action(self.p, "export", {"id":"d1", "revision":"v1"})

    def test_single_r0_item_cannot_replace_complete_state(self):
        before = load(self.p)
        with self.assertRaises(WorkflowError):
            w.perform(self.p, "stage", {"stage":"R0", "data":{
                "observations":[self.obs[3]], "references":[{"path":"reference.png","role":"color"}]}})
        self.assertEqual(load(self.p), before)

    def test_one_observation_correction_preserves_others_but_invalidates_downstream(self):
        revised = copy.deepcopy(self.obs)
        revised[3]["text"] = "Corrected color observation only"
        w.perform(self.p, "stage", {"stage":"R0","data":{
            "observations":revised,"references":[{"path":"reference.png","role":"color"}]}})
        s = load(self.p)
        for i in range(9):
            if i != 3:
                self.assertEqual(s["stages"]["R0"]["data"]["observations"][i], self.obs[i])
        self.assertFalse(stage_fresh(s,self.p,"R1"))
        self.assertFalse(stage_fresh(s,self.p,"R2"))
        with self.assertRaises(WorkflowError):
            self.prepare()

    def test_unregistered_observation_evidence_is_rejected(self):
        obs = copy.deepcopy(self.obs)
        obs[0]["evidence_file"] = "product.png"
        with self.assertRaises(WorkflowError):
            w.perform(self.p,"stage",{"stage":"R0","data":{
                "observations":obs,"references":[{"path":"reference.png","role":"color"}]}})

    def test_r1_missing_decision_does_not_partially_write(self):
        before = load(self.p)
        r1 = copy.deepcopy(self.r1)
        r1["decisions"].pop()
        with self.assertRaises(WorkflowError):
            w.perform(self.p,"stage",{"stage":"R1","data":r1,"evidence_files":["source.txt"]})
        self.assertEqual(load(self.p),before)

    def test_rejected_translation_not_in_actual_executable_requirements(self):
        j = self.prepare()
        self.assertFalse(any(r["source"].get("observation_id") == "o1" for r in j["requirements"]))
        self.assertNotIn("reference observation 1",json.loads((self.p/j["tool_args_file"]).read_text(encoding="utf-8"))["prompt"])

    def test_semantic_conflict_recorded_as_unresolved_blocks_begin(self):
        self.rule("alias","background","alternate-color-name","背景必须为绿色")
        j = self.prepare()
        args = json.loads((self.p/j["tool_args_file"]).read_text(encoding="utf-8"))
        with self.assertRaises(WorkflowError):
            prod.action(self.p,"begin",dict(job_id=j["id"],tool_args=args,
                inspected_images=[],intent_review={
                    "covered_requirement_ids":list(j["coverage"]),
                    "unresolved":["Blue and green conflict despite different property names"],
                    "observation":"TEST: assistant detected semantic conflict"}))
        self.assertEqual(load(self.p)["calls_used"],0)

    def test_new_blueprint_cannot_reuse_old_confirmation(self):
        d = copy.deepcopy(self.r2)
        d["creative_input"]["text"] += " revised"
        w.perform(self.p,"stage",{"stage":"R2","data":d,"evidence_files":["source.txt"]})
        with self.assertRaises(WorkflowError):
            self.prepare()

    def test_missing_protected_original_cannot_be_planned(self):
        bp = copy.deepcopy(self.bp)
        bp["elements"][1].pop("source")
        atomic(self.p/"missing.json",bp)
        d = dict(self.r2,spec="missing.json",planned_assets=["product"])
        with self.assertRaises(WorkflowError):
            w.perform(self.p,"stage",{"stage":"R2","data":d,"evidence_files":["source.txt"]})

    def test_wrong_first_attachment_blocks_local_job(self):
        self.generate()
        r = load(self.p)["revisions"]["v1"]
        with self.assertRaises(WorkflowError):
            prod.action(self.p,"prepare",dict(id="wrong-first",kind="local-edit",
                baseline="v1",goal="Only right block",change_request="Only right block",spec=r["spec"],
                input_images=[dict(path="reference.png",role="style",description="Not baseline"),
                              dict(path=r["image"],role="baseline",description="Actual baseline")]))

    def test_missing_edit_region_blocks_local_job(self):
        self.generate()
        r = load(self.p)["revisions"]["v1"]
        bp = json.loads((self.p/r["spec"]).read_text(encoding="utf-8"))
        bp["editable_regions"] = []
        atomic(self.p/"no-region.json",bp)
        with self.assertRaises(WorkflowError):
            prod.action(self.p,"prepare",dict(id="no-region",kind="local-edit",
                baseline="v1",goal="Only right block",change_request="Only right block",spec="no-region.json",
                input_images=[dict(path=r["image"],role="baseline",description="Actual baseline")]))

    def test_protected_region_collision_blocks_local_job(self):
        self.generate()
        r = load(self.p)["revisions"]["v1"]
        bp = json.loads((self.p/r["spec"]).read_text(encoding="utf-8"))
        bp["editable_regions"] = [{"id":"collision","rect":[.1,.1,.4,.4]}]
        atomic(self.p/"collision.json",bp)
        with self.assertRaises(WorkflowError):
            prod.action(self.p,"prepare",dict(id="collision",kind="local-edit",
                baseline="v1",goal="Collision",change_request="Collision",spec="collision.json",
                input_images=[dict(path=r["image"],role="baseline",description="Actual baseline")]))

    def test_opaque_output_cannot_satisfy_transparent_request(self):
        prod.action(self.p,"prepare",dict(id="transparent",kind="asset",goal="Transparent fixture",transparent_background=True))
        j=load(self.p)["jobs"]["transparent"]
        self.begin(j)
        Image.new("RGBA",(64,96),(1,2,3,255)).save(self.p/"opaque.png")
        result=prod.action(self.p,"finish",dict(job_id="transparent",output="opaque.png",
            tool_metadata={"fixture":True,"not_a_live_call":True}))
        self.assertEqual(result["status"],"FAILED")

    def test_machine_pass_does_not_override_target_fail(self):
        self.generate()
        self.generate("j2","v2","v1")
        self.all_checks("v2")
        self.review_status("v2","target","FAIL")
        self.assertEqual(load(self.p)["checks"]["v2"]["non_target"]["status"],"PASS")
        self.assertEqual(w.qc(load(self.p),self.p,"v2")["status"],"BLOCK")

    def test_noop_edit_requires_target_review_despite_zero_outside_change(self):
        self.generate()
        self.generate("j2","v2","v1")
        self.generate("j3","v3","v2")
        self.all_checks("v3")
        detail=load(self.p)["checks"]["v3"]["non_target"]["detail"]
        self.assertEqual(detail["inside_changed"],0)
        self.assertEqual(detail["outside_changed"],0)
        self.review_status("v3","target","UNKNOWN")
        self.assertEqual(w.qc(load(self.p),self.p,"v3")["status"],"BLOCK")

    def test_seam_failure_blocks_even_when_target_and_pixels_pass(self):
        self.generate()
        self.generate("j2","v2","v1")
        self.all_checks("v2")
        self.review_status("v2","seams","FAIL")
        self.assertEqual(w.qc(load(self.p),self.p,"v2")["status"],"BLOCK")

    def test_human_review_cannot_overwrite_machine_check(self):
        self.generate()
        checks.action(self.p,"run",{"revision":"v1"})
        with self.assertRaises(WorkflowError):
            self.review_status("v1","layers","PASS")

    def test_p1_exception_is_refused(self):
        self.generate()
        self.issue()
        with self.assertRaises(WorkflowError):
            w.perform(self.p,"accept-exception",dict(self.decision(),issue_id="probe",revision="v1"))

    def test_unknown_cannot_be_waived_by_p2_exception(self):
        self.generate()
        self.all_checks("v1")
        self.review_status("v1","design","UNKNOWN")
        self.issue("P2","design")
        w.perform(self.p,"accept-exception",dict(self.decision(),issue_id="probe",revision="v1"))
        self.assertEqual(w.qc(load(self.p),self.p,"v1")["status"],"BLOCK")

    def test_no_freeze_without_candidate_acceptance(self):
        self.generate()
        self.all_checks("v1")
        with self.assertRaises(WorkflowError):
            w.perform(self.p,"freeze",{"revision":"v1"})

    def test_no_export_without_frozen_master(self):
        self.generate()
        self.all_checks("v1")
        self.accept("v1")
        with self.assertRaises(WorkflowError):
            checks.action(self.p,"export",{"id":"d1","revision":"v1"})

    def test_revoke_candidate_invalidates_frozen_delivery(self):
        self.export_fixture()
        w.perform(self.p,"revoke",{"kind":"candidate","subject":"v1"})
        self.assertIsNone(load(self.p)["master"])
        with self.assertRaises(WorkflowError):
            checks.action(self.p,"accept-delivery",dict(self.decision(),delivery="d1"))

    def test_changed_delivery_png_cannot_be_accepted(self):
        self.export_fixture()
        p=next(x for x in load(self.p)["deliveries"]["d1"]["files"] if x.endswith("merged_preview.png"))
        (self.p/p).write_bytes(b"corrupt")
        with self.assertRaises(WorkflowError):
            checks.action(self.p,"accept-delivery",dict(self.decision(),delivery="d1"))

    def test_changed_delivery_ora_cannot_be_accepted(self):
        self.export_fixture()
        p=next(x for x in load(self.p)["deliveries"]["d1"]["files"] if x.endswith("layout_layers.ora"))
        (self.p/p).write_bytes(b"corrupt")
        with self.assertRaises(WorkflowError):
            checks.action(self.p,"accept-delivery",dict(self.decision(),delivery="d1"))

    def test_changed_attachment_after_compile_blocks_begin(self):
        self.generate()
        j=self.prepare("edit","local-edit","v1")
        Image.new("RGB",(64,96),"green").save(self.p/load(self.p)["revisions"]["v1"]["image"])
        with self.assertRaises(WorkflowError):
            self.begin(j)

    def test_full_resume_preserves_exact_copy_under_tiny_budget(self):
        copy_text="饮用天然水\n¥19.90 / 6罐｜2026.11.01—11.11"
        self.rule("exact-copy","title","copy",copy_text)
        resumed=ctx.build(self.p,budget=1)
        self.assertEqual(resumed["kind"],"full")
        self.assertEqual(next(x["text"] for x in resumed["context"]["requirements"] if x["id"]=="exact-copy"),copy_text)

    def test_two_five_eight_assets_retain_distinct_ids_roles_and_sources(self):
        for n in range(2,9):
            name="asset"+str(n)
            Image.new("RGBA",(20,20),(n*20,30,50,255)).save(self.p/(name+".png"))
            w.perform(self.p,"asset",dict(id=name,path=name+".png",role="test-role-"+str(n),
                description="Synthetic role fixture "+str(n),description_source="test"))
            if n in (2,5,8):
                with self.subTest(asset_count=n):
                    assets=load(self.p)["assets"]
                    self.assertEqual(len(assets),n)
                    self.assertEqual(len({tuple(a["files"].values()) for a in assets.values()}),n)
        s=load(self.p)
        self.assertEqual(len(s["assets"]),8)
        self.assertEqual(len({tuple(a["files"].values()) for a in s["assets"].values()}),8)

    def test_zero_budget_blocks_begin_without_counting_real_or_simulated_calls(self):
        transact(self.p,lambda s,r:s.update(call_budget=0))
        j=self.prepare()
        with self.assertRaises(WorkflowError):
            self.begin(j)
        self.assertEqual(load(self.p)["calls_used"],0)

    def commercial_root(self):
        from _workflow import create
        root=self.p/'commercial'
        create(root,'commercial-origin-probe',False,0)
        (root/'source.txt').write_text('Actual source declaration for a non-test project',encoding='utf-8')
        (root/'product.png').write_bytes((self.p/'product.png').read_bytes())
        return root

    def test_test_origin_cannot_override_commercial_brand(self):
        root=self.commercial_root()
        base=dict(id="brand",scope="background",property="brand-color",text="Official teal",
            verification="compare",source={"kind":"brand","quote":"Official teal"},evidence_files=["source.txt"])
        w.perform(root,"requirement",base)
        with self.assertRaises(WorkflowError):
            w.perform(root,"requirement",dict(base,id="test-override",text="Test gold",
                source={"kind":"test","quote":"Test gold"},supersedes=["brand"]))

    def test_test_asset_origin_cannot_enter_commercial_project(self):
        root=self.commercial_root()
        with self.assertRaises(WorkflowError):
            w.perform(root,"asset",dict(id="test-asset",path="product.png",role="product",
                description="Test-only source",description_source="test"))

    def test_legacy_commercial_test_sources_block_current_context(self):
        # Emulate a saved non-test project created before the origin guard existed.
        transact(self.p,lambda s,r:s.update(test_mode=False))
        state=ctx.build(self.p)["context"]
        self.assertEqual(state["status"],"BLOCK")
        self.assertIn("asset:product",state["test_sources"])
        self.assertIn("requirement:blue",state["test_sources"])

    def test_real_source_kinds_remain_available_in_commercial_project(self):
        root=self.commercial_root()
        for n,kind in enumerate(("user","brand")):
            w.perform(root,"requirement",dict(id="real-"+kind,scope="canvas",property="real-"+str(n),
                text="Real source declaration",verification="compare",source={"kind":kind,"quote":"source"},
                evidence_files=["source.txt"]))
        w.perform(root,"asset",dict(id="observed",path="product.png",role="product",
            description="Actually observed fixture",description_source="observed"))
        self.assertIn("observed",load(root)["assets"])

if __name__=="__main__":
    import unittest
    unittest.main()
