import copy, json, shutil, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from test_workflow_v3 import Fixture,load,WorkflowError,atomic,w
import portable,budget

class Portability(Fixture):
 def setUp(self):
  super().setUp();self.outer=tempfile.TemporaryDirectory();self.out=Path(self.outer.name)
 def tearDown(self):self.outer.cleanup();super().tearDown()
 def test_read_v3_does_not_mutate_or_import_approval(self):
  s=load(self.p);s['schema']='cvisual.workflow.v3';atomic(self.p/'workflow_state.json',s)
  before=(self.p/'workflow_state.json').read_bytes()
  self.assertEqual(portable.inspect(self.p)['schema'],'cvisual.workflow.v3')
  dry=portable.migrate_v3(self.p,self.out/'copy');self.assertEqual(dry['approvals_imported'],0);self.assertFalse((self.out/'copy').exists())
  portable.migrate_v3(self.p,self.out/'copy',True);state=load(self.out/'copy')
  self.assertEqual(state['decisions'],[]);self.assertEqual(state['stages'],{});self.assertEqual(state['migration']['objects']['requirements'],2)
  self.assertEqual((self.p/'workflow_state.json').read_bytes(),before)
  self.assertEqual((self.out/'copy/legacy/v3/workflow_state.json').read_bytes(),before)
 def test_old_executor_refuses_new_schema(self):
  v3=Path(__file__).resolve().parents[2]/'commercial-visual-production-v3-1-0/scripts'
  if not v3.exists():self.skipTest('baseline executor not bundled in isolated native package')
  r=subprocess.run([sys.executable,str(v3/'workflow.py'),'status','--project',str(self.p)],capture_output=True,text=True,encoding='utf-8')
  self.assertNotEqual(r.returncode,0);self.assertIn('invalid V3',r.stdout)
 def test_snapshot_preserves_rules_branches_sources_and_cancels_queued(self):
  self.generate();self.generate('j2','v2','v1');self.prepare('waiting')
  before=load(self.p);archive=self.out/'transfer.zip';portable.export_project(self.p,archive)
  portable.import_project(archive,self.out/'中文 with spaces');after=load(self.out/'中文 with spaces')
  for key in ('requirements','revisions','decisions','working_revision','calls_used','project_uuid'):self.assertEqual(before[key],after[key])
  self.assertEqual(after['jobs']['waiting']['status'],'cancelled');self.assertIsNone(after['execution_lease'])
 def test_shared_ledger_and_execution_owner_not_copied(self):
  ledger=self.out/'ledger.json';budget.init(ledger,0,'0',True);budget.bind(self.p,ledger)
  archive=self.out/'transfer.zip';portable.export_project(self.p,archive);portable.import_project(archive,self.out/'new')
  budget.bind(self.out/'new',ledger)
  with self.assertRaises(WorkflowError):budget.bind(self.p,ledger)
  self.assertEqual(len(budget.read(ledger)['attempts']),0)
 def test_import_does_not_reuse_machine_checks_or_frozen_master(self):
  self.generate();self.all_checks('v1');self.accept('v1');w.perform(self.p,'freeze',{'revision':'v1'})
  archive=self.out/'transfer.zip';portable.export_project(self.p,archive);portable.import_project(archive,self.out/'new')
  state=load(self.out/'new');self.assertIsNone(state['master']);self.assertEqual(state['checks'],{})
  self.assertTrue(state['host_reverification_required']);self.assertEqual(state['accepted_revision'],'v1')
  self.assertTrue(list((self.out/'new/.portable-import').rglob('source-state.json')))
 def test_active_requests_block_export(self):
  j=self.prepare();self.begin(j)
  with self.assertRaises(WorkflowError):portable.export_project(self.p,self.out/'blocked.zip')
 def test_credentials_cannot_enter_snapshot(self):
  (self.p/'.env').write_text('private configuration')
  with self.assertRaises(WorkflowError):portable.export_project(self.p,self.out/'blocked.zip')
 def test_secret_in_ordinary_json_blocks_export(self):
  atomic(self.p/'extra.json',{'OPENAI_API_KEY':'sk-'+('x'*30)})
  with self.assertRaises(WorkflowError):portable.export_project(self.p,self.out/'blocked.zip')
 def test_hash_tamper_blocks_import(self):
  archive=self.out/'transfer.zip';portable.export_project(self.p,archive)
  with zipfile.ZipFile(archive) as z:parts={n:z.read(n) for n in z.namelist()}
  parts['source.txt']=b'changed';bad=self.out/'bad.zip'
  with zipfile.ZipFile(bad,'w') as z:
   for n,b in parts.items():z.writestr(n,b)
  with self.assertRaises(WorkflowError):portable.import_project(bad,self.out/'new')
  self.assertFalse((self.out/'new').exists())
 def test_traversal_case_collision_and_duplicate_blocks_import(self):
  for index,names in enumerate((['../outside'],['/absolute'],['a\\b'],['C:/escape'],['a.json','A.json'])):
   bad=self.out/f'bad-{index}.zip'
   with zipfile.ZipFile(bad,'w') as z:
    for n in names:z.writestr(n,b'{}')
   with self.assertRaises(WorkflowError):portable.import_project(bad,self.out/f'new-{index}')
 def test_overwrite_destination_refused(self):
  archive=self.out/'transfer.zip';portable.export_project(self.p,archive);dest=self.out/'new';dest.mkdir()
  with self.assertRaises(WorkflowError):portable.import_project(archive,dest)
