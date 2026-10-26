"""Synthetic tool receipts test protocol boundaries; no real PhotoCraft or image service."""
import copy,io,json,zipfile
from pathlib import Path
from PIL import Image,ImageDraw
from test_workflow_v3 import Fixture,w,prod,checks,mat,load,atomic,active,transact,WorkflowError
from ora_verify import read_layers

def snapshot(root,source,index=0,idbase=10):
 im,layers=read_layers(root/source)
 return {'path':str((root/source).resolve()),'width':im.width,'height':im.height,'depth':8,'mode':'Rgb','layers':[{'id':idbase+i,'name':l['name'],'kind':'Pixel','visible':True,'opacity':1,'blend':'Normal','bounds':list(l['image'].getbbox() or (0,0,0,0))} for i,l in enumerate(layers)]}
def call(tool,args,result):return {'tool':tool,'args':args,'result':result,'isError':False}
def opening(root,source,idx=0,idbase=10):
 snap=snapshot(root,source,idx,idbase)
 return [call('doc_open',{'path':str(root/source)},{'index':idx,'width':snap['width'],'height':snap['height'],'warnings':[]}),call('doc_select',{'index':idx},{'active':idx}),call('doc_inspect',{'index':idx},snap)]
def receipt(root,path,calls):
 atomic(root/path,{'schema':'cvisual.photocraft.receipt.v1','backend':'photocraft','mode':'engine','fixture':True,'calls':calls})
def write_ora(path,layers):
 import xml.etree.ElementTree as E
 size=layers[0]['image'].size;xml=E.Element('image',w=str(size[0]),h=str(size[1]));stack=E.SubElement(xml,'stack');merged=Image.new('RGBA',size)
 for l in reversed(layers):merged.alpha_composite(l['image'])
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('mimetype',b'image/openraster')
  for i,l in enumerate(layers):
   box=l['image'].getbbox() or (0,0,1,1);data=io.BytesIO();l['image'].crop(box).save(data,format='PNG');src='data/'+str(i)+'.png';z.writestr(src,data.getvalue());E.SubElement(stack,'layer',{'name':l['name'],'src':src,'x':str(box[0]),'y':str(box[1]),'opacity':'1','visibility':'visible','composite-op':'svg:src-over'})
  z.writestr('stack.xml',E.tostring(xml));b=io.BytesIO();merged.save(b,format='PNG');z.writestr('mergedimage.png',b.getvalue())
 return merged

class EditorCases(Fixture):
 def setUp(self):
  super().setUp();self.generate();self.used=load(self.p)['calls_used'];transact(self.p,lambda s,r:s.update(call_budget=0));self.op={'type':'rectangle_fill','layer':'background','rect':[42,12,8,8],'color':'#FFAA00'}
 def plan(self):
  prod.action(self.p,'prepare-editor',{'id':'edit','baseline':load(self.p)['working_revision'],'goal':'Only fill authorized rectangle','operation':self.op,'intent_review':{'covered_requirement_ids':[x['id'] for x in active(load(self.p))],'unresolved':[],'observation':'TEST ONLY semantic scope review'}})
  return load(self.p)['jobs']['edit']
 def begin_editor(self,j=None):
  j=j or self.plan();self.calls=opening(self.p,j['editor_plan']['input']);receipt(self.p,'begin.json',self.calls)
  result=prod.action(self.p,'begin-editor',{'job_id':'edit','receipt':'begin.json'});return load(self.p)['jobs']['edit']
 def output(self,j=None):
  j=j or self.begin_editor();_,layers=read_layers(self.p/j['editor_plan']['input']);x,y,rw,rh=self.op['rect'];target=next(l for l in layers if l['name']==self.op['layer']);ImageDraw.Draw(target['image']).rectangle([x,y,x+rw-1,y+rh-1],fill=self.op['color'])
  self.layers=layers;png=j['editor_plan']['outputs']['png'];ora=j['editor_plan']['outputs']['ora'];write_ora(self.p/ora,layers).save(self.p/png)
  snap=copy.deepcopy(self.calls[2]['result'])
  for command in j['editor_commands']:
   self.calls.extend([call('command_run',command,{}),call('doc_select',{'index':0},{'active':0}),call('doc_inspect',{'index':0},copy.deepcopy(snap))])
  self.calls.extend([call('doc_export',{'index':0,'path':str(self.p/png)},{'path':str(self.p/png),'warnings':[]}),call('doc_export',{'index':0,'path':str(self.p/ora)},{'path':str(self.p/ora),'warnings':[]})]);receipt(self.p,'finish.json',self.calls);return j
 def finish_editor(self):return prod.action(self.p,'finish-editor',{'job_id':'edit','receipt':'finish.json'})
 def register(self):
  self.output();self.assertEqual(self.finish_editor()['status'],'EDITOR_READY');r=mat.materialize(self.p,'edit');r['id']='v2';w.perform(self.p,'revision',r);return r
 def audit(self,rid='v2'):
  self.all_checks(rid);s=load(self.p);source=next(p for p in s['checks'][rid]['layers']['files'] if p.endswith('layout_layers.ora'));image,layers=read_layers(self.p/source);folder=self.p/'audit';folder.mkdir(exist_ok=True);write_ora(folder/'saved.ora',layers).save(folder/'saved.png');calls=opening(self.p,source);snap=copy.deepcopy(calls[2]['result'])
  for l in snap['layers']:
   calls.append(call('command_run',{'id':'layer.hideLayers','params':{'layer':l['id']}},{}));off=copy.deepcopy(snap);next(x for x in off['layers'] if x['id']==l['id'])['visible']=False;calls.append(call('doc_inspect',{'index':0},off));calls.append(call('command_run',{'id':'layer.showLayers','params':{'layer':l['id']}},{}));calls.append(call('doc_inspect',{'index':0},copy.deepcopy(snap)))
  for file in ['saved.ora','saved.png']:calls.append(call('doc_export',{'index':0,'path':str(folder/file)},{'path':str(folder/file),'warnings':[]}))
  calls.extend(opening(self.p,'audit/saved.ora',1,100));receipt(self.p,'audit.json',calls);return {'revision':rid,'input':source,'ora':'audit/saved.ora','png':'audit/saved.png','receipt':'audit.json'}
 def test_zero_image_budget_allows_editor_and_keeps_candidate_pending(self):
  self.register();s=load(self.p);self.assertEqual(s['calls_used'],self.used);self.assertIsNone(s['accepted_revision']);self.assertEqual(w.qc(s,self.p,'v2')['status'],'BLOCK')
 def test_wrong_baseline_is_blocked(self):
  self.op['layer']='nonexistent'
  with self.assertRaises(WorkflowError):self.plan()
 def test_rectangle_outside_authorization_blocked(self):
  self.op['rect']=[0,0,8,8]
  with self.assertRaises(WorkflowError):self.plan()
 def test_protected_rectangle_blocked(self):
  self.op['rect']=[8,12,2,2]
  with self.assertRaises(WorkflowError):self.plan()
 def test_unknown_import_warning_blocked(self):
  j=self.plan();calls=opening(self.p,j['editor_plan']['input']);calls[0]['result']['warnings']=['missing layer recovered'];receipt(self.p,'begin.json',calls)
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin-editor',{'job_id':'edit','receipt':'begin.json'})
 def test_wrong_active_document_blocked(self):
  j=self.plan();calls=opening(self.p,j['editor_plan']['input']);calls.append(call('doc_open',{'path':str(self.p/'reference.png')},{'index':1,'warnings':[]}));receipt(self.p,'begin.json',calls)
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin-editor',{'job_id':'edit','receipt':'begin.json'})
 def test_duplicate_mapping_blocked(self):
  j=self.plan();calls=opening(self.p,j['editor_plan']['input']);calls[2]['result']['layers'][1]['id']=calls[2]['result']['layers'][0]['id'];receipt(self.p,'begin.json',calls)
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin-editor',{'job_id':'edit','receipt':'begin.json'})
 def test_stale_mapping_during_execution_blocked(self):
  self.output();calls=copy.deepcopy(self.calls);calls[5]['result']['layers'][0]['id']=999;receipt(self.p,'finish.json',calls);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_partial_batch_failure_is_not_registered(self):
  self.output();calls=copy.deepcopy(self.calls);calls[3]=call('command_batch',{'steps':[]},{'completed':1,'failed':1,'results':[]});receipt(self.p,'finish.json',calls);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_outside_raw_edit_cannot_be_hidden_by_hard_lock(self):
  j=self.output();ImageDraw.Draw(self.layers[-2]['image']).point((0,0),fill='red');write_ora(self.p/j['editor_plan']['outputs']['ora'],self.layers).save(self.p/j['editor_plan']['outputs']['png']);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_occluded_non_target_layer_change_blocks(self):
  j=self.output();ImageDraw.Draw(self.layers[-1]['image']).point((0,0),fill='magenta');write_ora(self.p/j['editor_plan']['outputs']['ora'],self.layers).save(self.p/j['editor_plan']['outputs']['png']);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_changed_png_is_refused(self):
  j=self.output();Image.new('RGBA',(64,96),'red').save(self.p/j['editor_plan']['outputs']['png']);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_begin_receipt_tampering_blocks_finish(self):
  self.output();(self.p/'begin.json').write_text('{}',encoding='utf-8');self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_failed_job_cannot_be_replayed(self):
  self.begin_editor();prod.action(self.p,'finish-editor',{'job_id':'edit','error':'unknown partial tool outcome'})
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin-editor',{'job_id':'edit','receipt':'begin.json'})
 def test_full_roundtrip_machine_check_allows_explicit_test_acceptance(self):
  self.register();d=self.audit();self.assertEqual(checks.action(self.p,'verify-editor',d)['status'],'PASS');self.assertEqual(w.qc(load(self.p),self.p,'v2')['status'],'PASS');self.accept('v2');w.perform(self.p,'freeze',{'revision':'v2'});checks.action(self.p,'export',{'id':'d','revision':'v2'})
 def test_audit_warning_blocks_even_when_preview_matches(self):
  self.register();d=self.audit();rec=json.loads((self.p/d['receipt']).read_text(encoding='utf-8'));rec['calls'][0]['result']['warnings']=['missing canvas recovered'];atomic(self.p/d['receipt'],rec);self.assertEqual(checks.action(self.p,'verify-editor',d)['status'],'FAIL');self.assertEqual(w.qc(load(self.p),self.p,'v2')['status'],'BLOCK')
 def test_audit_requires_all_layer_visibility_probes(self):
  self.register();d=self.audit();rec=json.loads((self.p/d['receipt']).read_text(encoding='utf-8'));rec['calls']=[x for x in rec['calls'] if x['tool'] not in ('command_run','doc_inspect') or x['tool']=='doc_inspect' and all(l['visible'] for l in x['result']['layers'])];atomic(self.p/d['receipt'],rec);self.assertEqual(checks.action(self.p,'verify-editor',d)['status'],'FAIL')
 def test_human_cannot_override_editor_machine_check(self):
  self.register()
  with self.assertRaises(WorkflowError):w.perform(self.p,'review',{'revision':'v2','check_id':'editor','status':'PASS','actor':'test','observation':'Not an actual machine audit','evidence_files':[load(self.p)['revisions']['v2']['image']]})
 def test_changed_audit_evidence_invalidates_qc(self):
  self.register();d=self.audit();checks.action(self.p,'verify-editor',d);(self.p/d['receipt']).write_text('{}',encoding='utf-8');self.assertEqual(w.qc(load(self.p),self.p,'v2')['status'],'BLOCK')

 def test_p2_cannot_waive_editor_machine_failure(self):
  self.register();d=self.audit();rec=json.loads((self.p/d['receipt']).read_text(encoding='utf-8'));rec['calls'][0]['result']['warnings']=['missing layer'];atomic(self.p/d['receipt'],rec);checks.action(self.p,'verify-editor',d)
  w.perform(self.p,'issue',{'id':'editor-loss','revision':'v2','check_id':'editor','severity':'P2','expected':'Layers intact','actual':'Missing layer warning','scope':'source layers'})
  with self.assertRaises(WorkflowError):w.perform(self.p,'accept-exception',dict(self.decision(),issue_id='editor-loss',revision='v2'))

 def test_materialized_patch_is_transparent_outside_exact_edit_rectangle(self):
  r=self.register();image=Image.open(self.p/'production/edit/materialized/patch.png').convert('RGBA');self.assertEqual(image.getbbox(),(42,12,50,20))
 def test_export_layer_order_change_blocks_even_if_occluded(self):
  j=self.output();self.layers[-2],self.layers[-1]=self.layers[-1],self.layers[-2];write_ora(self.p/j['editor_plan']['outputs']['ora'],self.layers).save(self.p/j['editor_plan']['outputs']['png']);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_new_non_test_project_requires_editor_backend(self):
  from _workflow import create
  q=self.p/'new-project';create(q,'new-project',False,0);self.assertEqual(load(q)['editor_backend'],'photocraft')
 def test_tool_failure_after_partial_steps_records_failure(self):
  self.output();calls=copy.deepcopy(self.calls);calls[3]['isError']=True;receipt(self.p,'finish.json',calls);self.assertEqual(self.finish_editor()['status'],'FAILED')
 def test_ui_queue_cannot_execute_without_assistant_intent_review(self):
  d={'id':'queued','baseline':'v1','goal':'User queued scope, not execution','operation':self.op};prod.action(self.p,'prepare-editor',d);j=load(self.p)['jobs']['queued'];receipt(self.p,'queued-open.json',opening(self.p,j['editor_plan']['input']))
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin-editor',{'job_id':'queued','receipt':'queued-open.json'})

 def test_http_editor_queue_is_only_a_prepared_task(self):
  import threading,urllib.request
  from review_server import ReviewServer
  server=ReviewServer(('127.0.0.1',0),self.p);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   payload={'action':'queue-editor','expected_seq':load(self.p)['seq'],'data':{'id':'http-editor','baseline':'v1','goal':'User requests a bounded fill','operation':self.op}}
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/action',json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req) as response:result=json.load(response)
   self.assertTrue(result['ok']);state=load(self.p);self.assertEqual(state['jobs']['http-editor']['status'],'waiting_execution');self.assertEqual(state['calls_used'],self.used);self.assertIsNone(state['accepted_revision'])
  finally:server.shutdown();server.server_close();thread.join()

 def test_occluded_fill_cannot_pass_when_composite_goal_is_not_met(self):
  transact(self.p,lambda s,r:s.update(call_budget=3));self.generate('older','v2','v1');self.output();self.assertEqual(self.finish_editor()['status'],'FAILED')
