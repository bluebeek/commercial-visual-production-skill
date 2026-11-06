import json,threading,urllib.request,urllib.error
from pathlib import Path
from test_workflow_v3 import Fixture,w,prod,checks,load,WorkflowError
from review_server import ReviewServer
from migrate_v2 import migrate

class Integration(Fixture):
 def request(self,server,action=None,data=None,seq=None):
  url='http://127.0.0.1:'+str(server.server_port)
  if action is None:return json.load(urllib.request.urlopen(url+'/api/state'))
  payload={'action':action,'data':data or {},'expected_seq':load(self.p)['seq'] if seq is None else seq}
  req=urllib.request.Request(url+'/api/action',json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  return json.load(urllib.request.urlopen(req))
 def test_http_run_really_creates_bound_reports(self):
  self.generate();server=ReviewServer(('127.0.0.1',0),self.p);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   before=list((self.p/'checks').rglob('*.json')) if (self.p/'checks').exists() else []
   self.assertEqual(before,[]);out=self.request(server,'run-checks',{'revision':'v1'});self.assertTrue(out['ok']);self.assertTrue(list((self.p/'checks').rglob('layer_export_report.json')))
   with self.assertRaises(urllib.error.HTTPError) as err:self.request(server,'select',{'revision':'v1'},seq=0)
   self.assertEqual(err.exception.code,409)
  finally:server.shutdown();server.server_close();thread.join()
 def test_http_generation_only_queues_and_cannot_accept_unreviewed(self):
  server=ReviewServer(('127.0.0.1',0),self.p);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   self.request(server,'queue-generation',{'id':'queued','kind':'background','goal':'use effective project requirements'})
   s=load(self.p);self.assertEqual(s['jobs']['queued']['status'],'waiting_execution');self.assertEqual(s['calls_used'],0);self.assertIsNone(s['accepted_revision'])
   self.assertEqual(self.request(server)['stage_names']['R0'],'参考解析')
  finally:server.shutdown();server.server_close();thread.join()
 def test_migration_copies_evidence_without_carrying_approval(self):
  old={'schema':'cvisual.review.state.v2','checks':{'R1.palette':{'status':'approved','files':{'reference.png':'old hash'}}},'issues':[{'id':'ISS-1','check_id':'R4.target','status':'resolved'}]}
  (self.p/'review_state.json').write_text(json.dumps(old),encoding='utf-8');dest=self.p.parent/(self.p.name+'-migrated')
  try:
   dry=migrate(self.p,dest);self.assertFalse(dest.exists());self.assertEqual(dry['approvals_imported'],0)
   result=migrate(self.p,dest,True);self.assertEqual(result['status'],'IMPORTED_UNBOUND');self.assertEqual(load(dest)['decisions'],[]);self.assertEqual(load(dest)['migration']['mapped_issues'][0]['new_status'],'ready_for_review')
   self.assertEqual((dest/'legacy-source/reference.png').read_bytes(),(self.p/'reference.png').read_bytes());self.assertEqual(json.loads((self.p/'review_state.json').read_text()),old)
  finally:
   if dest.exists():
    import shutil;shutil.rmtree(dest)
 def test_p2_specific_exception_and_new_revision_invalidation(self):
  self.generate();self.all_checks('v1');r=load(self.p)['revisions']['v1'];w.perform(self.p,'review',{'revision':'v1','check_id':'design','status':'FAIL','actor':'test','observation':'TEST minor cosmetic imperfection remains','evidence_files':[r['image']]})
  w.perform(self.p,'issue',{'id':'minor','revision':'v1','severity':'P2','scope':'background','check_id':'design','expected':'smoother tiny region','actual':'small cosmetic blemish'})
  self.assertEqual(w.qc(load(self.p),self.p,'v1')['status'],'BLOCK')
  w.perform(self.p,'accept-exception',dict(self.decision(),issue_id='minor',revision='v1'));self.assertEqual(w.qc(load(self.p),self.p,'v1')['status'],'PASS')
  self.generate('j2','v2','v1');self.all_checks('v2');self.assertEqual(w.qc(load(self.p),self.p,'v2')['status'],'BLOCK')
 def test_external_requirement_file_change_blocks_freeze(self):
  (self.p/'extra.txt').write_text('source',encoding='utf-8')
  w.perform(self.p,'requirement',{'id':'grain','scope':'background','property':'texture','text':'fine grain','verification':'visual','evidence_files':['extra.txt'],'source':{'kind':'test','quote':'fine grain'}})
  self.generate();self.all_checks('v1');self.accept('v1');(self.p/'extra.txt').write_text('different',encoding='utf-8')
  with self.assertRaises(WorkflowError):w.perform(self.p,'freeze',{'revision':'v1'})
 def test_pre_call_semantic_review_is_mandatory(self):
  j=self.prepare();args=json.loads((self.p/j['tool_args_file']).read_text(encoding='utf-8'))
  with self.assertRaises(WorkflowError):prod.action(self.p,'begin',{'job_id':j['id'],'tool_args':args})
 def test_unsupported_task_has_no_partial_authoritative_state(self):
  before=load(self.p)
  with self.assertRaises(WorkflowError):prod.action(self.p,'prepare',{'id':'bad','kind':'unsupported','goal':'test'})
  self.assertEqual(load(self.p),before)
