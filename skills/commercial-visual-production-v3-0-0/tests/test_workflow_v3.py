import copy,json,sys,tempfile,unittest,zipfile,threading,urllib.request,urllib.error
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import workflow as w, production as prod, checks, materialize as mat, stage_context as ctx
from _workflow import *
from blueprint import preview
from ora_verify import read_ora

class Fixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.p=Path(self.temp.name).resolve();create(self.p,'test-project',True,20)
  (self.p/'source.txt').write_text('TEST ONLY: user brief, no commercial approval. Blue background; product unchanged.',encoding='utf-8')
  Image.new('RGBA',(20,20),'red').save(self.p/'product.png');Image.new('RGB',(64,96),'blue').save(self.p/'reference.png')
  w.perform(self.p,'asset',{'id':'product','path':'product.png','role':'product','description':'测试产品原件','description_source':'test','must_keep':['颜色、轮廓'],'allowed_changes':[]})
  self.obs=[{'id':'o'+str(n),'module':n,'text':'reference observation '+str(n),'certainty':'observed','evidence_file':'reference.png'} for n in range(1,10)]
  w.perform(self.p,'stage',{'stage':'R0','data':{'observations':self.obs,'references':[{'path':'reference.png','role':'color'}]}})
  self.r1={'purpose':'受控测试海报','asset_roles':['product'],'decisions':[{'observation_id':o['id'],'decision':'reject' if o['id']=='o1' else 'adapt','reason':'按品牌用途选择'} for o in self.obs]}
  w.perform(self.p,'stage',{'stage':'R1','data':self.r1,'evidence_files':['source.txt']})
  self.bp={'canvas':{'width':64,'height':96,'background':'#005EAD'},'color_management':{'assume_untagged_srgb':True},'elements':[
   {'id':'background','role':'background','box':[0,0,1,1],'lock':'L3','z':0},
   {'id':'product','role':'product','box':[.1,.1,.3,.3],'lock':'L0','z':1,'source':'product.png'}],
   'editable_regions':[{'id':'right','rect':[.6,.1,.9,.5]}]}
  atomic(self.p/'blueprint.json',self.bp);preview(self.bp,self.p,(64,96),[]).save(self.p/'preview.png')
  self.r2={'creative_input':{'kind':'text','text':'左侧产品，右侧辅助图形'},'spec':'blueprint.json','preview':'preview.png'}
  w.perform(self.p,'stage',{'stage':'R2','data':self.r2,'evidence_files':['source.txt']})
  self.rule('blue','background','color','背景为蓝色')
  self.rule('product-lock','product','identity','产品保持原件','composite')
  w.perform(self.p,'confirm-blueprint',self.decision())
 def tearDown(self):self.temp.cleanup()
 def decision(self):return {'actor':'test','reason':'TEST ONLY: explicit fixture decision','evidence_files':['source.txt']}
 def rule(self,rid,scope,prop,text,method='prompt',**extra):
  return w.perform(self.p,'requirement',{'id':rid,'scope':scope,'property':prop,'text':text,'source':{'kind':'test','quote':text},'verification':'实际图像与原件核对','method':method,'evidence_files':['source.txt'],**extra})
 def prepare(self,jid='j1',kind='background',baseline=None):
  s=load(self.p);d={'id':jid,'kind':kind,'goal':'遵循当前有效要求制作背景和指定元素','notes':['保留刻意颗粒']}
  if baseline:
   r=s['revisions'][baseline];d.update(baseline=baseline,spec=r['spec'],change_request='只修改右侧色块',input_images=[{'path':r['image'],'role':'baseline','description':'本轮实际基准'}])
  prod.action(self.p,'prepare',d);return load(self.p)['jobs'][jid]
 def begin(self,j):
  args=json.loads(local(self.p,j['tool_args_file']).read_text(encoding='utf-8'))
  return prod.action(self.p,'begin',{'job_id':j['id'],'tool_args':args,'inspected_images':[x['sha256'] for x in j['input_images']],'intent_review':{'covered_requirement_ids':list(j['coverage']),'unresolved':[],'observation':'Test-only review of full prompt and actual image roles'}})
 def generate(self,jid='j1',rid='v1',baseline=None):
  j=self.prepare(jid,'local-edit' if baseline else 'background',baseline);self.begin(j)
  if baseline:
   with Image.open(local(self.p,load(self.p)['revisions'][baseline]['image'])) as im:a=np.asarray(im.convert('RGBA')).copy()
   a[12:25,42:50]=[255,180,0,255];a[0,0]=[255,0,255,255] # raw drift must be removed
   Image.fromarray(a).save(self.p/(jid+'-raw.png'))
  else:Image.new('RGBA',(64,96),'#005EAD').save(self.p/(jid+'-raw.png'))
  prod.action(self.p,'finish',{'job_id':jid,'output':jid+'-raw.png','tool_metadata':{'fixture':True,'not_a_live_call':True}})
  result=mat.materialize(self.p,jid);result['id']=rid;w.perform(self.p,'revision',result);return load(self.p)['revisions'][rid]
 def all_checks(self,rid):
  checks.action(self.p,'run',{'revision':rid});s=load(self.p);r=s['revisions'][rid]
  for cid in ['target','history','seams','design']+['req:'+x['id'] for x in active(s)]:
   w.perform(self.p,'review',{'revision':rid,'check_id':cid,'status':'PASS','actor':'test','observation':'TEST fixture observation of actual image; no commercial approval','evidence_files':[r['image']]})
 def accept(self,rid):w.perform(self.p,'accept',dict(self.decision(),revision=rid))

class Contracts(Fixture):
 def test_nine_modules_required(self):
  with self.assertRaises(WorkflowError):w.perform(self.p,'stage',{'stage':'R0','data':{'observations':self.obs[:-1]}})
 def test_r0_and_r1_cannot_make_blueprint(self):
  for sid in ['R0','R1']:
   with self.assertRaises(WorkflowError):w.perform(self.p,'stage',{'stage':sid,'data':{'canvas':{}}})
 def test_rejected_reference_never_promoted(self):
  with self.assertRaises(WorkflowError):w.perform(self.p,'requirement',{'id':'bad','scope':'background','property':'style','text':'red','verification':'view','source':{'kind':'translation','observation_id':'o1','quote':'red'},'evidence_files':['source.txt']})
 def test_replacement_removes_old_rule_from_actual_prompt(self):
  self.rule('gold','background','color','背景改为金色',supersedes=['blue']);j=self.prepare();args=json.loads(local(self.p,j['tool_args_file']).read_text(encoding='utf-8'))
  self.assertNotIn('背景为蓝色',args['prompt']);self.assertIn('背景改为金色',args['prompt']);self.assertIn('刻意颗粒',args['prompt'])
 def test_competing_rule_cannot_silently_win(self):
  with self.assertRaises(WorkflowError):self.rule('green','background','color','绿色')
 def test_unrelated_scope_cannot_be_superseded(self):
  with self.assertRaises(WorkflowError):self.rule('bad','product','color','green',supersedes=['blue'])
 def test_stale_source_blocks_generation(self):
  (self.p/'source.txt').write_text('changed',encoding='utf-8')
  with self.assertRaises(WorkflowError):self.prepare()
 def test_unknown_critical_rule_blocks(self):
  self.rule('unknown','canvas','copy','unknown',status='unknown')
  with self.assertRaises(WorkflowError):self.prepare()
 def test_blueprint_confirmation_needed_and_revocable(self):
  sid=load(self.p)['stages']['R2']['id'];w.perform(self.p,'revoke',{'kind':'blueprint','subject':sid})
  with self.assertRaises(WorkflowError):self.prepare()
 def test_sketch_and_mixed_inputs(self):
  for kind in ('sketch','mixed'):
   d=copy.deepcopy(self.r2);d['creative_input']={'kind':kind,'path':'reference.png','text':'sketch explanation'}
   w.perform(self.p,'stage',{'stage':'R2','data':d,'evidence_files':['source.txt']})
   self.assertFalse(approved_blueprint(load(self.p),self.p))
 def test_no_user_approval_fabrication_from_test(self):
  with self.assertRaises(WorkflowError):w.perform(self.p,'confirm-blueprint',dict(self.decision(),actor='user'))
 def test_context_resume_no_raw_rejected_fact(self):
  a=ctx.build(self.p);self.assertNotIn('R0',a['context']['stages']);b=ctx.build(self.p,since=a['context_id']);self.assertEqual(b['kind'],'unchanged')
  self.rule('gold','background','color','gold',supersedes=['blue']);c=ctx.build(self.p,since=a['context_id']);self.assertEqual(c['kind'],'delta');self.assertEqual(ctx.build(self.p)['kind'],'full')
 def test_context_budget_does_not_drop_exact_copy(self):
  text='新品\nABC 2026：¥99.00';self.rule('copy','title','copy',text)
  out=ctx.build(self.p,budget=1);self.assertTrue(out['soft_budget_exceeded']);self.assertEqual(next(r for r in out['context']['requirements'] if r['id']=='copy')['text'],text)
 def test_conflicting_write_rejected(self):
  seq=load(self.p)['seq'];self.rule('detail','background','texture','grain')
  with self.assertRaises(ConflictError):w.perform(self.p,'confirm-blueprint',self.decision(),seq)

class Production(Fixture):
 def test_four_task_modes(self):
  for k in ['background','asset','whole']:
   j=self.prepare(k,k);args=json.loads(local(self.p,j['tool_args_file']).read_text(encoding='utf-8'));self.assertIn('禁止事项',args['prompt']);self.assertEqual(set(args),{'prompt','transparent_background'})
  self.generate();self.prepare('edit','local-edit','v1')
 def test_local_edit_without_baseline_blocked(self):
  with self.assertRaises(WorkflowError):self.prepare(kind='local-edit')
 def test_attachment_order_and_prompt_bound(self):
  self.generate();j=self.prepare('edit','local-edit','v1');args=json.loads(local(self.p,j['tool_args_file']).read_text(encoding='utf-8'));args['prompt']+='extra'
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin',{'job_id':'edit','tool_args':args,'inspected_images':[x['sha256'] for x in j['input_images']]})
 def test_input_image_must_be_inspected(self):
  self.generate();j=self.prepare('edit','local-edit','v1');args=json.loads(local(self.p,j['tool_args_file']).read_text(encoding='utf-8'))
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin',{'job_id':'edit','tool_args':args})
 def test_failed_calls_count_and_no_duplicate_begin(self):
  def setbudget(s,r):s['call_budget']=1
  transact(self.p,setbudget);j=self.prepare();self.begin(j);prod.action(self.p,'finish',{'job_id':'j1','error':'test failure'})
  with self.assertRaises(WorkflowError):self.begin(j)
  j2=self.prepare('j2')
  with self.assertRaises(WorkflowError):self.begin(j2)
 def test_changed_rules_invalidate_prepared_job(self):
  j=self.prepare();self.rule('gold','background','color','gold',supersedes=['blue'])
  with self.assertRaises(WorkflowError):self.begin(j)
 def test_changed_prompt_file_cannot_be_reused(self):
  j=self.prepare();local(self.p,j['tool_args_file']).write_text('{}',encoding='utf-8')
  with self.assertRaises(WorkflowError):self.begin(j)
 def test_actual_dimensions_not_assumed(self):
  j=self.prepare();self.begin(j);Image.new('RGB',(32,32)).save(self.p/'wrong.png')
  r=prod.action(self.p,'finish',{'job_id':'j1','output':'wrong.png'});self.assertEqual(r['status'],'FAILED')
 def test_materialization_required(self):
  self.generate()
  with self.assertRaises((WorkflowError,KeyError)):w.perform(self.p,'revision',{'id':'fake','job_id':'j1','parent':None,'image':'reference.png','spec':'blueprint.json'})
 def test_hard_lock_and_source_layers_match_after_edit(self):
  a=self.generate();b=self.generate('j2','v2','v1');checks.action(self.p,'run',{'revision':'v2'});s=load(self.p)
  self.assertEqual(s['checks']['v2']['non_target']['detail']['outside_changed'],0);self.assertEqual(s['checks']['v2']['layers']['status'],'PASS');self.assertEqual(s['accepted_revision'],None)
 def test_third_edit_keeps_prior_patch_layers(self):
  self.generate();self.generate('j2','v2','v1');self.generate('j3','v3','v2');r=self.generate('j4','v4','v3');checks.action(self.p,'run',{'revision':'v4'})
  p=json.loads(local(self.p,r['spec']).read_text(encoding='utf-8'));self.assertEqual(len([e for e in p['elements'] if e.get('provenance')=='raster_patch']),3)
 def test_protected_original_cannot_be_replaced(self):
  bp=copy.deepcopy(self.bp);Image.new('RGB',(20,20),'green').save(self.p/'other.png');bp['elements'][1]['source']='other.png';atomic(self.p/'bad-spec.json',bp)
  with self.assertRaises(WorkflowError):prod.action(self.p,'prepare',{'id':'bad','kind':'background','goal':'test','spec':'bad-spec.json'})

class ReviewDelivery(Fixture):
 def test_no_acceptance_before_actual_checks(self):
  self.generate()
  with self.assertRaises(WorkflowError):self.accept('v1')
 def test_report_tampering_invalidates_qc(self):
  self.generate();self.all_checks('v1');self.assertEqual(w.qc(load(self.p),self.p,'v1')['status'],'PASS')
  c=load(self.p)['checks']['v1']['files'];p=next(x for x in c['files'] if x.endswith('/files.json'));local(self.p,p).write_text('{}',encoding='utf-8');self.assertEqual(w.qc(load(self.p),self.p,'v1')['status'],'BLOCK')
 def test_revision_id_immutable(self):
  r=self.generate()
  with self.assertRaises(WorkflowError):w.perform(self.p,'revision',dict(r,id='v1'))
 def test_restore_branch_does_not_accept_candidate(self):
  self.generate();self.all_checks('v1');self.accept('v1');self.generate('j2','v2','v1');w.perform(self.p,'select',{'revision':'v1'});self.generate('j3','branch','v1');s=load(self.p)
  self.assertEqual(s['revisions']['branch']['parent'],'v1');self.assertEqual(s['accepted_revision'],'v1');self.assertIn('v2',s['revisions'])
 def test_actual_png_ora_delivery(self):
  self.generate();self.all_checks('v1');self.accept('v1');w.perform(self.p,'freeze',{'revision':'v1'});checks.action(self.p,'export',{'id':'d1','revision':'v1'});checks.action(self.p,'accept-delivery',dict(self.decision(),delivery='d1'))
  d=load(self.p)['deliveries']['d1'];self.assertEqual(d['status'],'accepted');self.assertTrue(d['verification']['ora_readback']);self.assertEqual(d['verification']['editor_open'],'NOT_TESTED')
 def test_delivery_cannot_accept_changed_master(self):
  self.generate();self.all_checks('v1');self.accept('v1');w.perform(self.p,'freeze',{'revision':'v1'});checks.action(self.p,'export',{'id':'d1','revision':'v1'});local(self.p,load(self.p)['revisions']['v1']['image']).write_bytes(b'bad')
  with self.assertRaises(WorkflowError):checks.action(self.p,'accept-delivery',dict(self.decision(),delivery='d1'))
 def test_issue_requires_real_repair_and_review(self):
  self.generate();w.perform(self.p,'issue',{'id':'i1','revision':'v1','expected':'right block','actual':'needs adjustment','scope':'background','check_id':'target','severity':'P1'})
  self.generate('j2','v2','v1');w.perform(self.p,'repair',{'issue_id':'i1','job_id':'j2','baseline':'v1'});w.perform(self.p,'submit-repair',{'issue_id':'i1','revision':'v2'})
  self.assertEqual(load(self.p)['issues']['i1']['status'],'ready_for_review')
  with self.assertRaises(WorkflowError):w.perform(self.p,'close-issue',{'issue_id':'i1','revision':'v2'})
  self.all_checks('v2');w.perform(self.p,'close-issue',{'issue_id':'i1','revision':'v2'});self.assertEqual(w.qc(load(self.p),self.p,'v2')['status'],'PASS')
 def test_p0_cannot_be_waived(self):
  self.generate();w.perform(self.p,'issue',{'id':'i1','revision':'v1','expected':'correct identity','actual':'wrong identity','scope':'product','check_id':'req:product-lock','severity':'P0'})
  with self.assertRaises(WorkflowError):w.perform(self.p,'accept-exception',dict(self.decision(),issue_id='i1',revision='v1'))
 def test_ora_corrupted_stack_is_detected(self):
  self.generate();checks.action(self.p,'run',{'revision':'v1'});p=next((self.p/'checks').rglob('layout_layers.ora'));bad=self.p/'bad.ora'
  with zipfile.ZipFile(p) as src,zipfile.ZipFile(bad,'w') as out:
   for n in src.namelist():out.writestr(n,src.read(n).replace(b'opacity="1.0"',b'opacity="0.5"') if n=='stack.xml' else src.read(n),compress_type=zipfile.ZIP_STORED if n=='mimetype' else zipfile.ZIP_DEFLATED)
  with self.assertRaises(ValueError):read_ora(bad)

if __name__=='__main__':unittest.main()
