"""Observable compact I/O invariants; no assertions about model token billing."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage_context as ctx
import prompt_compile as pc
import review_engine as engine
from _compact import compact_result

class CompactIOTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve()
  (self.p/'source.txt').write_text('original',encoding='utf-8')
 def tearDown(self):self.tmp.cleanup()
 def packet(self,sid,data=None,critical=None,details=None,evidence=None):
  return ctx.put_packet(self.p,sid,{'summary':'summary '+sid,'data':data or {},'critical':critical or [],'details':details,'evidence_files':evidence or []})
 def ready(self):
  self.packet('R0',{'observations':['reference fact']},['exact copy ABC 2026','protect original face'],details='long narrative '*10000)
  self.packet('R1',{'brand_rules':['blue'],'asset_roles':[]},['official label unchanged'],evidence=['source.txt'])
  self.packet('R2',{'canvas':{'width':64,'height':96},'copy':['ABC 2026'],'elements':[]},['unknown font license'])
 def spec(self):
  Image.new('RGBA',(20,20),(255,0,0,255)).save(self.p/'person.png')
  obj={'canvas':{'width':64,'height':96,'background':'#005EAD'},'elements':[{'id':'person','role':'person','box':[.1,.1,.3,.5],'lock':'L0','source':'person.png','description':'用户说明：真实人物，只供后期合成'},{'id':'bg','role':'background','box':[0,0,1,1],'lock':'L3'}],'style_rules':['保留少量胶片颗粒'],'editable_regions':[{'id':'edit','rect':[.8,.8,.9,.9]}]}
  spec=self.p/'blueprint.json';spec.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8');return spec
 def test_context_omits_narrative_keeps_all_critical_and_exact_copy(self):
  self.ready();r,c=ctx.build_context(self.p,'R3');self.assertEqual(c,0)
  self.assertNotIn('R0',r['context']['stages']);self.assertNotIn('long narrative',json.dumps(r))
  for text in ['exact copy ABC 2026','protect original face','official label unchanged','unknown font license']:self.assertIn(text,r['context']['critical'])
  self.assertEqual(r['context']['stages']['R2']['data']['copy'],['ABC 2026'])
 def test_context_unchanged_cursor_returns_no_old_content(self):
  self.ready();r,_=ctx.build_context(self.p,'R3');again,_=ctx.build_context(self.p,'R3',r['context_id'])
  self.assertEqual(again['kind'],'unchanged');self.assertNotIn('context',again)
 def test_context_changed_returns_delta_bound_to_base(self):
  self.ready();r,_=ctx.build_context(self.p,'R3');self.packet('R2',{'copy':['new exact copy']},['new restriction'])
  new,_=ctx.build_context(self.p,'R3',r['context_id']);self.assertEqual(new['kind'],'delta');self.assertEqual(new['base'],r['context_id'])
  self.assertEqual(new['changed']['stages']['R2']['data']['copy'],['new exact copy']);self.assertIn('new restriction',new['changed']['critical'])
 def test_context_unknown_cursor_returns_full(self):
  self.ready();r,_=ctx.build_context(self.p,'R3','not-in-memory');self.assertEqual(r['kind'],'full')
 def test_context_modified_evidence_is_stale_even_with_cursor(self):
  self.ready();r,_=ctx.build_context(self.p,'R3');(self.p/'source.txt').write_text('changed',encoding='utf-8')
  new,code=ctx.build_context(self.p,'R3',r['context_id']);self.assertEqual(code,2);self.assertEqual(new['status'],'STALE');self.assertNotIn('kind',new)
 def test_context_budget_does_not_truncate_rules(self):
  self.ready();r,_=ctx.build_context(self.p,'R3',budget=10);self.assertTrue(r['soft_budget_exceeded']);self.assertEqual(len(r['context']['critical']),4)
 def test_context_rejects_unknown_fields_and_external_evidence(self):
  with self.assertRaises(ValueError):ctx.put_packet(self.p,'R2',{'data':{'mystery':'must not silently disappear'}})
  with self.assertRaises(ValueError):ctx.put_packet(self.p,'R2',{'evidence_files':['../outside.txt']})
  with self.assertRaises(ValueError):ctx.put_packet(self.p,'R2',{'approved':True})
 def test_context_never_hides_missing_stage_inputs(self):
  r,_=ctx.build_context(self.p,'R3');self.assertEqual(r['context']['missing_packets'],['R1','R2'])
 def test_context_refreshes_actual_review_revision(self):
  self.ready();Image.new('RGB',(32,32),'red').save(self.p/'final.png');engine.load(self.p,create=True)
  engine.transact(self.p,'revision',{'revision':'v01','evidence_files':['final.png']})
  r,_=ctx.build_context(self.p,'R3');Image.new('RGB',(32,32),'green').save(self.p/'final.png')
  new,_=ctx.build_context(self.p,'R3',r['context_id']);self.assertTrue(new['changed']['review']['active_revision']['stale'])
 def test_prompt_cache_checks_input_and_output_files(self):
  spec=self.spec();out=self.p/'prompts';first=pc.compile_compact(spec,out);self.assertFalse(first['cache_hit'])
  second=pc.compile_compact(spec,out);self.assertTrue(second['cache_hit'])
  target=out/'01_background_prompt.txt';target.write_text('corrupted',encoding='utf-8');self.assertFalse(pc.compile_compact(spec,out)['cache_hit'])
  Image.new('RGBA',(20,20),(0,255,0,255)).save(self.p/'person.png');self.assertFalse(pc.compile_compact(spec,out)['cache_hit'])
 def test_prompt_intake_reuse_and_no_repeated_notes(self):
  spec=self.spec();brief={'notes':['保留右侧水花','保留右侧水花'],'asset_descriptions':[{'id':'person','description':'用户已提供人物原件，身份不改'}]}
  (self.p/'generation_brief.json').write_text(json.dumps(brief,ensure_ascii=False),encoding='utf-8')
  r=pc.compile_compact(spec,self.p/'prompts');text=(self.p/'prompts/01_background_prompt.txt').read_text(encoding='utf-8')
  self.assertEqual(r['intake_gaps'],[]);self.assertEqual(text.count('保留右侧水花'),1);self.assertIn('少量胶片颗粒',text);self.assertIn('身份不改',text);self.assertGreater(len(text.splitlines()),5)
 def test_prompt_brief_changes_invalidate_cache(self):
  spec=self.spec();brief=self.p/'generation_brief.json';brief.write_text('{"notes":["first"]}',encoding='utf-8')
  pc.compile_compact(spec,self.p/'prompts');brief.write_text('{"notes":["second"]}',encoding='utf-8');self.assertFalse(pc.compile_compact(spec,self.p/'prompts')['cache_hit'])
 def test_prompt_local_edit_needs_goal_and_keeps_masks(self):
  spec=self.spec()
  with self.assertRaises(ValueError):pc.compile_compact(spec,self.p/'prompts','local-edit')
  (self.p/'generation_brief.json').write_text(json.dumps({'change_request':'only remove banding'}),encoding='utf-8')
  pc.compile_compact(spec,self.p/'prompts','local-edit');text=(self.p/'prompts/02_local_edit_contract.txt').read_text(encoding='utf-8')
  self.assertIn('only remove banding',text);self.assertIn('person',text);self.assertIn('0.8',text)
 def test_prompt_rejects_same_effect_required_and_forbidden(self):
  spec=self.spec();(self.p/'generation_brief.json').write_text(json.dumps({'required_effects':['water'],'forbidden':['water']}),encoding='utf-8')
  with self.assertRaises(ValueError):pc.compile_compact(spec,self.p/'prompts')
 def test_summary_preserves_all_failures_and_scope(self):
  report={'status':'BLOCK','meaning':'geometry only','elements':[{'element':'ok','result':'PASS'}]+[{'element':str(i),'result':'UNKNOWN'} for i in range(40)],'warnings':['needs real observation']}
  brief=compact_result(report,'actual.json');self.assertEqual(len(brief['elements_attention']),40);self.assertEqual(brief['meaning'],'geometry only');self.assertEqual(brief['status'],'BLOCK')
 def test_audit_stdout_compact_full_file_still_has_rows(self):
  spec=self.spec();image=self.p/'actual.png';Image.new('RGB',(64,96),'blue').save(image)
  observed={'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'annotation_method':'manual','source':'test fixture','boxes':{'person':[.1,.1,.3,.5],'bg':[0,0,1,1]}}
  obs=self.p/'observed.json';obs.write_text(json.dumps(observed),encoding='utf-8');report=self.p/'layout.json'
  cmd=[sys.executable,str(ROOT/'scripts/layout_audit.py'),'--spec',str(spec),'--image',str(image),'--observed',str(obs),'--out',str(report)]
  r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  brief=json.loads(r.stdout);full=json.loads(report.read_text(encoding='utf-8'));self.assertEqual(len(full['elements']),2);self.assertEqual(brief['elements_count'],2);self.assertNotIn('elements',brief)
  r=subprocess.run(cmd+['--full-output'],capture_output=True,text=True,encoding='utf-8');self.assertEqual(len(json.loads(r.stdout)['elements']),2)
 def test_review_stage_filter_and_full_export(self):
  engine.load(self.p,create=True);s=engine.snapshot(self.p);brief=engine.review_brief(s,'R2');self.assertTrue(all(m['id']=='R2' for m in brief['modules']))
  out=self.p/'export.json';r=subprocess.run([sys.executable,str(ROOT/'scripts/review_engine.py'),'export','--project',str(self.p),'--out',str(out)],capture_output=True,text=True,encoding='utf-8')
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('history',json.loads(out.read_text(encoding='utf-8')))

if __name__=='__main__':unittest.main()
