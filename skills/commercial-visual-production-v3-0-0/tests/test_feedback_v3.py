import copy,json,math
from PIL import Image
from test_workflow_v3 import Fixture,w,prod,checks,mat,load,WorkflowError,active,atomic

class FeedbackRegression(Fixture):
 def test_native_composition_reuses_actual_output_with_no_image_calls(self):
  self.generate();self.generate('j2','v2','v1');used=load(self.p)['calls_used']
  prod.action(self.p,'prepare-compose',{'id':'c2','baseline':'v2','source_job':'j2','goal':'缩小合成区域并修复接缝','application_regions':[{'id':'focus','rect':[.65,.13,.83,.32]}],'feather':2})
  r=mat.materialize(self.p,'c2');r['id']='v2b';w.perform(self.p,'revision',r);checks.action(self.p,'run',{'revision':'v2b'});s=load(self.p)
  self.assertEqual(s['calls_used'],used);self.assertEqual(s['jobs']['c2']['status'],'materialized');self.assertEqual(s['checks']['v2b']['non_target']['status'],'PASS');self.assertEqual(s['checks']['v2b']['layers']['status'],'PASS')
 def test_composition_cannot_expand_user_region(self):
  self.generate();self.generate('j2','v2','v1')
  with self.assertRaises(WorkflowError):prod.action(self.p,'prepare-compose',{'id':'bad','baseline':'v2','source_job':'j2','goal':'test','application_regions':[{'id':'all','rect':[0,0,1,1]}],'feather':0})
 def test_superseded_requirement_can_retire_its_issue_without_claiming_fixed(self):
  self.generate();w.perform(self.p,'issue',{'id':'old','revision':'v1','check_id':'req:blue','scope':'background','severity':'P1','expected':'blue','actual':'not blue'})
  self.rule('gold','background','color','gold',supersedes=['blue']);w.perform(self.p,'supersede-issue',{'issue_id':'old','replacement_requirement':'gold'});self.assertEqual(load(self.p)['issues']['old']['status'],'superseded')
 def test_unrelated_rule_cannot_retire_issue(self):
  self.generate();w.perform(self.p,'issue',{'id':'old','revision':'v1','check_id':'req:blue','scope':'background','severity':'P1','expected':'blue','actual':'not blue'})
  with self.assertRaises(WorkflowError):w.perform(self.p,'supersede-issue',{'issue_id':'old','replacement_requirement':'product-lock'})
 def test_polygon_prompt_is_compact_but_mask_is_exact(self):
  self.generate();r=load(self.p)['revisions']['v1'];p=json.loads((self.p/r['spec']).read_text());points=[[.75+.1*math.cos(i*2*math.pi/100),.65+.1*math.sin(i*2*math.pi/100)] for i in range(100)];p['editable_regions']=[{'id':'precise','polygon':points}];atomic(self.p/'polygon.json',p)
  out=prod.action(self.p,'prepare',{'id':'poly','kind':'local-edit','goal':'只修指定局部','change_request':'仅改变明确区域','baseline':'v1','spec':'polygon.json','input_images':[{'path':r['image'],'role':'baseline','description':'real baseline'}],'feather':4});j=load(self.p)['jobs']['poly'];self.assertLess(out['prompt_chars'],2000);self.assertEqual(j['editable_regions'][0]['polygon'],points);self.assertEqual(j['feather'],4)
 def test_cancelled_job_never_consumes_generation_budget(self):
  j=self.prepare();used=load(self.p)['calls_used'];prod.action(self.p,'cancel',{'job_id':j['id'],'reason':'replace unattempted prompt'})
  self.assertEqual(load(self.p)['calls_used'],used)
  with self.assertRaises(WorkflowError):self.begin(j)
 def native_setup(self,outside=False):
  self.generate();r=load(self.p)['revisions']['v1'];p=json.loads((self.p/r['spec']).read_text());Image.new('RGBA',(20,20),'green').save(self.p/'replacement.png');(self.p/'native-request.txt').write_text('TEST: replace product source with green fixture, keep other pixels',encoding='utf-8')
  w.perform(self.p,'requirement',{'id':'new-source','scope':'product','property':'identity','text':'产品采用新的绿色测试原件','verification':'source compare','method':'composite','supersedes':['product-lock'],'source':{'kind':'test','quote':'TEST: replace product source with green fixture, keep other pixels'},'evidence_files':['native-request.txt']})
  p['elements'][1]['source']='replacement.png';p['elements'][1]['edit_authorization']={'reason':'explicit fixture replacement of product only','evidence_file':'native-request.txt','regions':[{'id':'product','rect':[.1,.1,.4,.4]}]};p['editable_regions']=[{'id':'scope','rect':[.6,.1,.9,.5] if outside else [.1,.1,.4,.4]}];atomic(self.p/'native.json',p)
  from blueprint import preview
  preview(p,self.p,(64,96),[]).save(self.p/'native-preview.png');w.perform(self.p,'stage',{'stage':'R2','data':{'creative_input':{'kind':'text','text':'explicit source replacement'},'spec':'native.json','preview':'native-preview.png'},'evidence_files':['native-request.txt']});w.perform(self.p,'confirm-blueprint',self.decision())
  s=load(self.p);return prod.action(self.p,'prepare-source',{'id':'native','baseline':'v1','spec':'native.json','goal':'按新要求更换产品源图层，其他不变','layer_updates':['product'],'intent_review':{'covered_requirement_ids':[r['id'] for r in active(s)],'unresolved':[],'observation':'TEST: reviewed source intent, authorization and current requirements'}})
 def test_source_layer_replacement_does_not_require_generation(self):
  self.native_setup();before=load(self.p)['calls_used'];r=mat.materialize(self.p,'native');r['id']='v2';w.perform(self.p,'revision',r);checks.action(self.p,'run',{'revision':'v2'});s=load(self.p);self.assertEqual(s['calls_used'],before);self.assertEqual(s['checks']['v2']['non_target']['status'],'PASS');self.assertEqual(s['checks']['v2']['layers']['status'],'PASS')
 def test_native_changes_outside_scope_are_blocked(self):
  self.native_setup(True)
  with self.assertRaises(WorkflowError):mat.materialize(self.p,'native')
  self.assertNotIn('v2',load(self.p)['revisions'])

 def test_unknown_reference_cannot_be_promoted_to_active_requirement(self):
  obs=copy.deepcopy(self.obs);obs[1]['certainty']='unknown';w.perform(self.p,'stage',{'stage':'R0','data':{'observations':obs,'references':[{'path':'reference.png','role':'style'}]}});w.perform(self.p,'stage',{'stage':'R1','data':self.r1,'evidence_files':['source.txt']})
  with self.assertRaises(WorkflowError):w.perform(self.p,'requirement',{'id':'unknown-ref','scope':'background','property':'new','text':'unsupported font','verification':'view','source':{'kind':'translation','observation_id':'o2','quote':'unknown'},'evidence_files':['source.txt']})
 def test_unknown_critical_planning_cannot_be_signed_off(self):
  self.rule('font','title','font','unknown exact font',status='unknown')
  with self.assertRaises(WorkflowError):w.perform(self.p,'confirm-blueprint',self.decision())
 def test_master_retains_actual_acceptance_evidence_binding(self):
  self.generate();self.all_checks('v1');(self.p/'approval.txt').write_text('TEST ONLY candidate acceptance',encoding='utf-8');w.perform(self.p,'accept',{'revision':'v1','actor':'test','reason':'explicit test acceptance','evidence_files':['approval.txt']});w.perform(self.p,'freeze',{'revision':'v1'});(self.p/'approval.txt').write_text('changed decision source',encoding='utf-8')
  with self.assertRaises(WorkflowError):checks.action(self.p,'export',{'id':'bad-delivery','revision':'v1'})

 def test_project_relocation_cannot_reuse_old_absolute_attachment_paths(self):
  import tempfile,shutil
  from pathlib import Path
  self.generate();j=self.prepare('edit','local-edit','v1');args=json.loads((self.p/j['tool_args_file']).read_text(encoding='utf-8'))
  with tempfile.TemporaryDirectory() as td:
   other=Path(td)/'copy';shutil.copytree(self.p,other)
   with self.assertRaises(WorkflowError):prod.action(other,'begin',{'job_id':'edit','tool_args':args,'inspected_images':[x['sha256'] for x in j['input_images']],'intent_review':{'covered_requirement_ids':list(j['coverage']),'unresolved':[],'observation':'test reviewed current attachments'}})
