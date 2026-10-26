import json,sys,tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage_context as ctx
import prompt_compile as pc
import _evidence as ev
from impact_audit import inspect_tree

class ImpactOptimizationTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def put(self,sid,data=None,details=''):return ctx.put_packet(self.p,sid,{'summary':sid,'data':data or {},'critical':[],'details':details})
 def ready(self):self.put('R0',{'observations':['original']});self.put('R1',{'brand_rules':['blue']});self.put('R2',{'copy':['TITLE']})
 def spec(self,root=None):
  p=root or self.p;p.mkdir(exist_ok=True,parents=True);Image.new('RGB',(16,16),'blue').save(p/'reference.png')
  bp={'canvas':{'width':64,'height':96,'background':'#FFFFFF'},'elements':[{'id':'background','role':'background','box':[.12345,.2,.5,.6],'lock':'L3'}]}
  (p/'blueprint.json').write_text(json.dumps(bp),encoding='utf-8');(p/'generation_brief.json').write_text(json.dumps({'input_images':[{'path':'reference.png','role':'color only','description':'provided reference'}]}),encoding='utf-8');return p/'blueprint.json'
 def test_changed_parent_invalidates_downstream_packet(self):
  self.ready();old,_=ctx.build_context(self.p,'R3');self.put('R1',{'brand_rules':['red']});r,code=ctx.build_context(self.p,'R3',old['context_id'])
  self.assertEqual(code,2);self.assertEqual(r['status'],'STALE');self.assertIn('R2',r['refresh_stages']);self.assertTrue(any(x.get('upstream_stage')=='R1' for x in r['changed_sources']))
 def test_transitive_refresh_plan_in_one_response(self):
  self.ready();self.put('R0',{'observations':['changed']});r,_=ctx.build_context(self.p,'R3');self.assertEqual(r['refresh_stages'],['R1','R2'])
 def test_details_only_change_does_not_invalidate_downstream(self):
  self.ready();self.put('R0',{'observations':['original']},details='expanded explanation');r,code=ctx.build_context(self.p,'R3');self.assertEqual(code,0);self.assertEqual(r['status'],'READY')
 def test_legacy_packets_are_explicitly_unbound(self):
  self.put('R0');f=self.p/'.visual-context/stages/R0.json';o=json.loads(f.read_text(encoding='utf-8'));o['schema']='cvisual.context.packet.v1';o.pop('upstream');f.write_text(json.dumps(o),encoding='utf-8');r,_=ctx.build_context(self.p,'R1');self.assertIn('R0',r['context']['unbound_packets'])
 def test_corrupt_context_cache_rebuilds(self):
  self.ready();ctx.build_context(self.p,'R3');(self.p/'.visual-context/cache/R3.json').write_text('broken',encoding='utf-8');r,c=ctx.build_context(self.p,'R3');self.assertEqual(c,0);self.assertEqual(r['kind'],'full')
 def test_context_cursor_does_not_hide_project_relocation(self):
  self.ready();old,_=ctx.build_context(self.p,'R3');dest=self.p/'copy';shutil.copytree(self.p/'.visual-context',dest/'.visual-context');r,_=ctx.build_context(dest,'R3',old['context_id']);self.assertNotEqual(r['kind'],'unchanged');self.assertNotEqual(r['context_id'],old['context_id'])
 def test_prompt_cache_relocation_refreshes_absolute_image_paths(self):
  spec=self.spec();pc.compile_compact(spec,self.p/'prompts');dest=self.p/'copy';dest.mkdir()
  for f in ['blueprint.json','generation_brief.json','reference.png']:shutil.copyfile(self.p/f,dest/f)
  shutil.copytree(self.p/'prompts',dest/'prompts');r=pc.compile_compact(dest/'blueprint.json',dest/'prompts');self.assertFalse(r['cache_hit']);manifest=json.loads((dest/'prompts/.prompt_manifest.background.json').read_text(encoding='utf-8'));self.assertEqual(manifest['input_images'][0]['path'],str((dest/'reference.png').resolve()))
 def test_corrupt_prompt_cache_recompiles(self):
  spec=self.spec();pc.compile_compact(spec,self.p/'prompts');(self.p/'prompts/.prompt_manifest.background.json').write_text('[]',encoding='utf-8');self.assertFalse(pc.compile_compact(spec,self.p/'prompts')['cache_hit'])
 def test_fractional_layout_coordinates_are_not_rounded(self):
  self.assertIn('12.345%',pc.boxtext({'id':'region','box':[.12345,.2,.5,.6]}));self.assertIn('宽100%',pc.boxtext({'id':'full','box':[0,0,1,1]}))
 def test_unrelated_export_change_does_not_invalidate_geometry(self):
  before={t:ev.tool_fingerprint(t) for t in ev.TOOLS};original=ev.digest
  with patch.object(ev,'digest',side_effect=lambda p:'changed' if Path(p).name=='export_layers.py' else original(p)):
   after={t:ev.tool_fingerprint(t) for t in ev.TOOLS}
  self.assertEqual(before['layout_audit'],after['layout_audit']);self.assertEqual(before['pixel_audit'],after['pixel_audit']);self.assertNotEqual(before['preflight'],after['preflight']);self.assertNotEqual(before['layer_export'],after['layer_export'])
 def test_display_helper_change_does_not_invalidate_metrics(self):
  before={t:ev.tool_fingerprint(t) for t in ev.TOOLS};original=ev.digest
  with patch.object(ev,'digest',side_effect=lambda p:'changed' if Path(p).name=='_compact.py' else original(p)):
   self.assertEqual(before,{t:ev.tool_fingerprint(t) for t in ev.TOOLS})
 def test_impact_inventory_does_not_mutate_state(self):
  import review_engine as engine
  engine.load(self.p,create=True);state=self.p/'review_state.json';before=state.read_bytes();r=inspect_tree(self.p);self.assertEqual(r['counts']['states'],1);self.assertEqual(state.read_bytes(),before);self.assertTrue(r['states'][0]['file_unchanged'])

if __name__=='__main__':unittest.main()
