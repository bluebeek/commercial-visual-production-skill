import copy,json,sys,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import model_catalog,budget
from _workflow import WorkflowError,create,load,atomic
from test_generation_v4 import NOTES,GOOGLE

class Catalog(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.p=self.root/'catalog.json';self.clock=datetime(2026,11,6,tzinfo=timezone.utc)
 def tearDown(self):self.temp.cleanup()
 def refresh(self,text=NOTES,provider='openai'):return model_catalog.refresh(provider,self.p,lambda u:text,self.clock)
 def test_latest_selected_by_release_date_not_number(self):
  text=NOTES+'\n### Nov 1\nReleased gpt-image-99.0-sunburst.\n';self.refresh(text)
  self.assertEqual(model_catalog.resolve(self.p,'openai',clock=self.clock)['model'],'gpt-image-2.6-sunburst')
 def test_new_release_not_adapted_blocks_not_falls_back(self):
  self.refresh('## November, 2026\n### Nov 5\nReleased gpt-image-2.7-sunburst.\n'+NOTES.split('\n',1)[1])
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai',clock=self.clock)
 def test_unknown_or_stale_source_blocks(self):
  self.refresh()
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai',clock=self.clock+timedelta(hours=1))
  self.p.with_suffix('.source.md').write_text('different source')
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai',clock=self.clock)
 def test_capability_tamper_blocks(self):
  d=self.refresh();d['models'][0]['capabilities']['max_inputs']=1000;atomic(self.p,d)
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai','speed',clock=self.clock)
 def test_simulation_cannot_authorize_real_model(self):
  d=self.refresh();d['fixture']=True;atomic(self.p,d)
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai',clock=self.clock)
 def test_google_latest_single_model_not_filled_with_old_pro(self):
  self.refresh(GOOGLE+'\n## September 1, 2026\nReleased gemini-3-pro-image.\n','google')
  d=model_catalog.resolve(self.p,'google',clock=self.clock);self.assertEqual(d['model'],'gemini-nano-banana-2.1')
 def test_missing_release_and_future_release_block(self):
  with self.assertRaises(WorkflowError):self.refresh('model gpt-image-2.6-sunburst without a dated release')
  with self.assertRaises(WorkflowError):self.refresh('## November, 2026\n### Nov 9\nReleased gpt-image-2.6-sunburst.')
 def test_catalog_models_must_match_source(self):
  d=self.refresh();d['models'].reverse();atomic(self.p,d)
  with self.assertRaises(WorkflowError):model_catalog.resolve(self.p,'openai',clock=self.clock)
 def test_deprecation_in_same_day_is_not_new_release(self):
  text=GOOGLE+'\n* **Deprecation announcement**: gemini-3.1-flash-image is deprecated; migrate to gemini-nano-banana-2.1.\n'
  self.refresh(text,'google')
  self.assertEqual(model_catalog.resolve(self.p,'google',clock=self.clock)['model'],'gemini-nano-banana-2.1')
 def test_previous_model_mentioned_as_update_is_not_new_release(self):
  text=GOOGLE.replace('for images.','for images. An update to gemini-3.1-flash-image.')
  self.refresh(text,'google')
  self.assertEqual(model_catalog.resolve(self.p,'google',clock=self.clock)['model'],'gemini-nano-banana-2.1')

class Budget(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.p=self.root/'one';self.q=self.root/'two';self.ledger=self.root/'shared.json'
  create(self.p,'one',True,10,editor_backend=None);create(self.q,'two',True,10,editor_backend=None)
  budget.init(self.ledger,1,'1',True);budget.bind(self.p,self.ledger);budget.bind(self.q,self.ledger)
 def tearDown(self):self.temp.cleanup()
 def reserve(self,p,j='job',cost='1'):return budget.reserve(load(p),p,j,cost,{'model':'fixture-model','provider':'openai'})
 def test_attempt_limit_is_shared_across_projects(self):
  self.reserve(self.p)
  with self.assertRaises(WorkflowError):self.reserve(self.q)
 def test_failed_attempt_does_not_refund(self):
  key=self.reserve(self.p);s=load(self.p);budget.mark(s,self.p,key,'attempted');budget.mark(s,self.p,key,'failed')
  with self.assertRaises(WorkflowError):self.reserve(self.q)
 def test_zero_cost_and_nonfinite_not_accepted(self):
  for n in ('0','NaN','Infinity','-1'):
   with self.assertRaises(WorkflowError):self.reserve(self.p,cost=n)
 def test_double_reservation_and_ledger_reset_block(self):
  self.reserve(self.p)
  with self.assertRaises(WorkflowError):self.reserve(self.p)
  with self.assertRaises(WorkflowError):budget.init(self.ledger,10,'10',True)
 def test_shared_ledger_must_not_be_project_local(self):
  with self.assertRaises(WorkflowError):budget.bind(self.root/'third',self.p/'copy.json')
 def test_unknown_attempt_blocks_release(self):
  key=self.reserve(self.p);s=load(self.p);budget.mark(s,self.p,key,'attempted');budget.mark(s,self.p,key,'unknown')
  with self.assertRaises(WorkflowError):budget.release(self.p)
 def test_budget_test_production_isolation(self):
  prod=self.root/'prod';create(prod,'production')
  with self.assertRaises(WorkflowError):budget.bind(prod,self.ledger)
