"""Explicit synthetic transport contracts; no image service or credentials used."""
import base64, copy, io, json, shutil
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from PIL import Image
from test_workflow_v3 import Fixture,w,prod,checks,load,WorkflowError,atomic
import generation,model_catalog,budget,providers,materialize

NOTES='## November, 2026\n### Nov 4\nReleased gpt-image-2.6-sunburst and gpt-image-2.6-flare.\n'
GOOGLE='## October 15, 2026\nReleased gemini-nano-banana-2.1 for images.\n'

class OfficialGeneration(Fixture):
 def setUp(self):
  super().setUp()
  self.bp['canvas'].update(width=1024,height=1024);atomic(self.p/'api-blueprint.json',self.bp)
  Image.new('RGB',(1024,1024),'blue').save(self.p/'api-preview.png')
  r2=copy.deepcopy(self.r2);r2.update(spec='api-blueprint.json',preview='api-preview.png')
  w.perform(self.p,'stage',{'stage':'R2','data':r2,'evidence_files':['source.txt']});w.perform(self.p,'confirm-blueprint',self.decision())
  self.catalog('openai');self.ledger=self.p.parent/(self.p.name+'-budget.json');budget.init(self.ledger,8,'8',True);budget.bind(self.p,self.ledger)
 def tearDown(self):
  if self.ledger.exists():self.ledger.unlink()
  super().tearDown()
 def catalog(self,provider):
  model_catalog.refresh(provider,self.p/'model_catalog.json',lambda url: NOTES if provider=='openai' else GOOGLE)
  d=json.loads((self.p/'model_catalog.json').read_text());d['fixture']=True;atomic(self.p/'model_catalog.json',d)
 def prepare_api(self,jid='api1',**extra):
  prod.action(self.p,'prepare',{'id':jid,'kind':'background','goal':'follow the actual current requirements',
                              'provider':'openai','catalog':'model_catalog.json','maximum_cost_usd':'1',**extra})
  return load(self.p)['jobs'][jid]
 def execute_api(self,jid='api1',transport=None):
  j=load(self.p)['jobs'][jid]
  return generation.execute(self.p,jid,{'covered_requirement_ids':list(j['coverage']),'unresolved':[],
                                      'observation':'TEST inspected intent and ordered input sources'},
                            [x['sha256'] for x in j['input_images']],transport=transport or self.success)
 def success(self,url,headers,body):
  b=io.BytesIO();Image.new('RGBA',(1024,1024),'blue').save(b,format='PNG')
  return {'status_code':200,'request_id':'fixture-request','body':{'data':[{'b64_json':base64.b64encode(b.getvalue()).decode()}],'usage':{'fixture':True}}}
 def test_success_enters_existing_materialize_revision_and_review_gate(self):
  self.prepare_api();result=self.execute_api();self.assertEqual(result['status'],'GENERATED')
  out=materialize.materialize(self.p,'api1');out['id']='api-v1';w.perform(self.p,'revision',out)
  self.assertEqual(load(self.p)['revisions']['api-v1']['status'],'candidate');self.assertIsNone(load(self.p)['accepted_revision'])
  with self.assertRaises(WorkflowError):w.perform(self.p,'freeze',{'revision':'api-v1'})
 def test_latest_uses_new_release_not_fixed_25(self):
  j=self.prepare_api();self.assertEqual(j['selection']['model'],'gpt-image-2.6-sunburst')
 def test_test_project_cannot_call_live_transport(self):
  self.prepare_api()
  with self.assertRaises(WorkflowError):generation.execute(self.p,'api1',{},[])
  self.assertEqual(len(budget.read(self.ledger)['attempts']),0)
 def test_429_has_one_attempt_no_hidden_retry(self):
  self.prepare_api();calls=[]
  result=self.execute_api(transport=lambda *args:(calls.append(args) or {'status_code':429,'body':{}}))
  self.assertEqual(result['status'],'FAILED');self.assertEqual(len(calls),1);self.assertEqual(load(self.p)['calls_used'],1)
  with self.assertRaises(WorkflowError):self.execute_api()
 def test_500_is_unknown_and_never_replayed(self):
  self.prepare_api();calls=[];self.execute_api(transport=lambda *a:(calls.append(a) or {'status_code':500,'body':{}}))
  self.assertEqual(load(self.p)['jobs']['api1']['status'],'result_unknown');self.assertEqual(len(calls),1)
  with self.assertRaises(WorkflowError):budget.release(self.p)
 def test_timeout_retains_reservation_and_no_candidate(self):
  self.prepare_api()
  def timeout(*a):raise TimeoutError('secret must not enter persisted logs')
  self.assertEqual(self.execute_api(transport=timeout)['status'],'UNKNOWN')
  self.assertEqual(next(iter(budget.read(self.ledger)['attempts'].values()))['reserved_usd'],'1')
  self.assertEqual(load(self.p)['revisions'],{})
 def test_zero_budget_stops_before_transport(self):
  def zero(s,r):s['call_budget']=0
  from _workflow import transact
  transact(self.p,zero);self.prepare_api();calls=[]
  with self.assertRaises(WorkflowError):self.execute_api(transport=lambda *a:calls.append(a))
  self.assertEqual(calls,[]);self.assertEqual(len(budget.read(self.ledger)['attempts']),0)
 def test_corrupt_response_is_failure_but_attempt_still_counts(self):
  self.prepare_api();r=self.execute_api(transport=lambda *a:{'status_code':200,'body':{'data':[{'b64_json':'not base64!'}]}})
  self.assertEqual(r['status'],'FAILED');self.assertEqual(len(budget.read(self.ledger)['attempts']),1)
 def test_zero_images_not_success(self):
  self.prepare_api();self.assertEqual(self.execute_api(transport=lambda *a:{'status_code':200,'body':{'data':[]}})['status'],'FAILED')
 def test_wrong_dimensions_not_resized(self):
  self.prepare_api();b=io.BytesIO();Image.new('RGB',(64,64)).save(b,format='PNG')
  r=self.execute_api(transport=lambda *a:{'status_code':200,'body':{'data':[{'b64_json':base64.b64encode(b.getvalue()).decode()}]}})
  self.assertEqual(r['status'],'FAILED')
  with Image.open(self.p/'production/api1/raw.png') as im:self.assertEqual(im.size,(64,64))
 def test_alpha_requirement_checks_real_output(self):
  self.prepare_api(transparent_background=True);self.assertEqual(self.execute_api()['status'],'FAILED')
 def test_changed_output_receipt_blocks_materialize(self):
  self.prepare_api();self.execute_api();(self.p/'production/api1/receipt.json').write_text('{}')
  with self.assertRaises(WorkflowError):materialize.materialize(self.p,'api1')
 def test_wrong_project_execution_owner(self):
  self.prepare_api();dest=self.p.parent/(self.p.name+'-copy');shutil.copytree(self.p,dest)
  try:
   j=load(dest)['jobs']['api1'];args=json.loads((dest/j['tool_args_file']).read_text())
   with self.assertRaises(WorkflowError):prod.action(dest,'begin',{'job_id':'api1','tool_args':args,'intent_review':{'covered_requirement_ids':list(j['coverage']),'unresolved':[],'observation':'TEST current intent checked'},'inspected_images':[]})
  finally:shutil.rmtree(dest)
 def test_unsupported_size_blocked_before_request(self):
  self.catalog('google')
  self.bp['canvas']['width']=2048;atomic(self.p/'api-blueprint.json',self.bp)
  with self.assertRaises(WorkflowError):self.prepare_api(provider='google')
 def test_google_contract_preserves_order_and_filters_thought_images(self):
  self.catalog('google');self.prepare_api(provider='google',input_images=[{'path':'product.png','role':'product','description':'red original'},{'path':'reference.png','role':'color','description':'blue reference'}])
  b=io.BytesIO();Image.new('RGB',(1024,1024),'blue').save(b,format='PNG');enc=base64.b64encode(b.getvalue()).decode()
  seen=[]
  def google(url,headers,body):
   seen.append(json.loads(body));return {'status_code':200,'body':{'id':'fixture-google','steps':[{'type':'thought','content':[{'type':'image','data':'not an output'}]},{'type':'model_output','content':[{'type':'image','data':enc}]}]}}
  self.assertEqual(self.execute_api(transport=google)['status'],'GENERATED')
  self.assertEqual([x['type'] for x in seen[0]['input']],['text','image','image']);self.assertNotIn('tools',seen[0])
 def test_google_alpha_not_silently_dropped(self):
  self.catalog('google')
  with self.assertRaises(WorkflowError):self.prepare_api(provider='google',transparent_background=True)
 def test_builtin_cannot_claim_latest(self):
  with self.assertRaises(WorkflowError):self.prepare_api(provider='builtin')
 def test_old_catalog_refresh_does_not_invalidate_completed_evidence(self):
  self.prepare_api();self.execute_api();self.catalog('google')
  self.assertIsNotNone(materialize.materialize(self.p,'api1'))
 def test_shared_usd_limit_stops_new_project(self):
  self.prepare_api(maximum_cost_usd='9');calls=[]
  with self.assertRaises(WorkflowError):self.execute_api(transport=lambda *a:calls.append(a))
  self.assertEqual(calls,[])
 def test_wrong_reported_model_is_not_adopted(self):
  self.prepare_api()
  def wrong(*a):
   response=self.success(*a);response['body']['model']='gpt-image-2.5-sunburst';return response
  self.assertEqual(self.execute_api(transport=wrong)['status'],'FAILED')
 def test_old_output_cannot_impersonate_this_attempt(self):
  self.prepare_api();Image.new('RGB',(1024,1024)).save(self.p/'production/api1/raw.png')
  with self.assertRaises(WorkflowError):self.execute_api()
  self.assertEqual(len(budget.read(self.ledger)['attempts']),0)
 def test_unknown_can_recover_without_second_network_call(self):
  self.prepare_api()
  def timeout(*a):raise TimeoutError()
  self.execute_api(transport=timeout)
  (self.p/'provider-evidence.txt').write_text('TEST retained provider result, not commercial proof')
  atomic(self.p/'provider-response.json',self.success(None,None,None))
  result=generation.recover(self.p,'api1','provider-response.json','provider-evidence.txt')
  self.assertEqual(result['status'],'GENERATED');self.assertEqual(load(self.p)['calls_used'],1)
  self.assertEqual(len(budget.read(self.ledger)['attempts']),1)
 def test_unknown_failure_recovery_does_not_refund(self):
  self.prepare_api()
  def timeout(*a):raise TimeoutError()
  self.execute_api(transport=timeout);(self.p/'provider-evidence.txt').write_text('TEST confirmed provider failure')
  self.assertEqual(generation.recover(self.p,'api1',None,'provider-evidence.txt',True)['status'],'FAILED')
  self.assertEqual(load(self.p)['calls_used'],1)
 def test_api_local_edits_hard_lock_and_keep_prior_patch(self):
  import numpy as np
  self.prepare_api();self.execute_api();out=materialize.materialize(self.p,'api1');out['id']='v1';w.perform(self.p,'revision',out)
  for number,parent in ((2,'v1'),(3,'v2')):
   previous=load(self.p)['revisions'][parent];jid='api'+str(number)
   self.prepare_api(jid,kind='local-edit',baseline=parent,spec=previous['spec'],change_request='recolor only the right permitted region',
                    input_images=[{'path':previous['image'],'role':'baseline','description':'actual selected baseline'}])
   def changed(url,headers,body):
    with Image.open(self.p/previous['image']) as im:arr=np.array(im.convert('RGBA'))
    arr[120:130,650+number*20:660+number*20]=[255,200,number,255];arr[0,0]=[255,0,255,255]
    b=io.BytesIO();Image.fromarray(arr).save(b,format='PNG')
    return {'status_code':200,'body':{'data':[{'b64_json':base64.b64encode(b.getvalue()).decode()}]}}
   self.execute_api(jid,changed);out=materialize.materialize(self.p,jid);out['id']='v'+str(number);w.perform(self.p,'revision',out)
   checks.action(self.p,'run',{'revision':out['id']})
   self.assertEqual(load(self.p)['checks'][out['id']]['non_target']['detail']['outside_changed'],0)
  state=load(self.p);prior=state['revisions']['v2'];last=state['revisions']['v3']
  for n,h in prior['files'].items():
   if n.endswith('/patch.png'):self.assertEqual(last['files'].get(n),h)
