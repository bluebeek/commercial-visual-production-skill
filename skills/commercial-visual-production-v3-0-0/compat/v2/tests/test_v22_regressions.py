"""Observable regression cases for the demonstrated V2.1 failures."""
import json,sys,tempfile,subprocess,shutil,unittest,threading
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import review_engine as e
import review_server as web
from _evidence import digest,verify_report
from _common import validate_project,evaluate_constraint
from _storage import ConflictError
from urllib.request import urlopen,Request
from urllib.error import HTTPError

class V22Regressions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
  self.art=self.p/'artifacts';self.art.mkdir()
  self.brief=self.p/'brief.md';self.brief.write_text('UNIT TEST FIXTURE ONLY: approved dimensions and sources',encoding='utf-8')
  Image.new('RGB',(64,96),(0,94,173)).save(self.p/'source.png')
  self.final=self.art/'final.png';shutil.copyfile(self.p/'source.png',self.final)
  self.spec={'canvas':{'width':64,'height':96,'background':'#FFFFFF'},'elements':[{'id':'bg','role':'background','box':[0,0,1,1],'z':0,'source':'source.png','required':True}], 'color_management':{'working_space':'sRGB','assume_untagged_srgb':True}}
  self.bp=self.p/'blueprint.json';self.write(self.bp,self.spec)
  self.s=e.load(self.p,create=True)
  e.apply(self.s,self.p,'revision',{'revision':'v01','evidence_files':['artifacts/final.png']})
  self.defs,self.mods,self.checks=e.definitions()
 def tearDown(self):self.tmp.cleanup()
 def write(self,p,obj):p.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
 def run_script(self,name,*args):
  return subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/name),*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=30)
 def approve(self,cid):return e.apply(self.s,self.p,'approve',{'check_id':cid,'evidence':'UNIT TEST actual files reviewed','evidence_files':['brief.md','artifacts/final.png']})
 def preflight(self):
  r=self.run_script('blueprint.py','--spec',self.bp,'--mode','production','--out',self.art)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  e.apply(self.s,self.p,'inspect',{})
 def test_F01_ancestor_changed_blocks_later_signoff_without_inspect(self):
  self.preflight()
  for m in self.mods[:3]:
   for c in m['checks']:self.approve(c['id'])
   e.apply(self.s,self.p,'signoff',{'stage':m['id']})
  report=self.art/'preflight.json';data=json.loads(report.read_text(encoding='utf-8'));data['status']='BLOCK';self.write(report,data)
  with self.assertRaises(e.ReviewError):e.apply(self.s,self.p,'signoff',{'stage':'R3'})
  self.assertNotIn('R2',self.s['signoffs'])
  self.assertEqual(self.s['checks']['R2.preflight']['status'],'stale')
 def test_F02_minimal_report_and_nonexistent_evidence_rejected(self):
  self.write(self.art/'preflight.json',{'status':'PASS'})
  e.apply(self.s,self.p,'inspect',{})
  with self.assertRaises(e.ReviewError):self.approve('R2.preflight')
  with self.assertRaises(e.ReviewError):e.apply(self.s,self.p,'approve',{'check_id':'R0.roles','evidence':'nonexistent file','evidence_files':['missing.png']})
 def test_F02_output_and_input_changes_invalidate_bound_report(self):
  self.preflight();self.approve('R2.preflight')
  Image.new('RGB',(64,96),'red').save(self.art/'layout_preview.png')
  e.refresh(self.s,self.p)
  self.assertEqual(self.s['checks']['R2.preflight']['status'],'stale')
  self.preflight();self.approve('R2.preflight')
  Image.new('RGB',(64,96),'green').save(self.p/'source.png')
  with self.assertRaises(ValueError):verify_report(self.art/'preflight.json','preflight',self.p)
 def test_F03_candidate_rejection_invalidates_brand_and_identity(self):
  for cid in ['R4.target','R6.brand_copy','R6.identity_product']:self.approve(cid)
  e.apply(self.s,self.p,'reject',{'check_id':'R4.target','issue':'whole candidate must be recreated','severity':'P0'})
  for cid in ['R6.brand_copy','R6.identity_product']:self.assertEqual(self.s['checks'][cid]['status'],'stale')
 def test_resolve_requires_new_registered_image_and_fresh_fix(self):
  self.approve('R6.brand_copy')
  e.apply(self.s,self.p,'reject',{'check_id':'R6.brand_copy','issue':'unit test incorrect title','severity':'P1'})
  issue=self.s['issues'][-1]['id']
  data={'issue_id':issue,'fixed_revision':'v02','resolution':'unit test corrected title','evidence_files':['artifacts/final.png']}
  with self.assertRaises(e.ReviewError):e.apply(self.s,self.p,'resolve',data)
  Image.new('RGB',(64,96),'orange').save(self.final)
  e.apply(self.s,self.p,'revision',{'revision':'v02','evidence_files':['artifacts/final.png']})
  e.apply(self.s,self.p,'resolve',data)
  self.assertEqual(self.s['checks']['R6.brand_copy']['status'],'pending')
  Image.new('RGB',(64,96),'red').save(self.final)
  with self.assertRaises(e.ReviewError):self.approve('R6.brand_copy')
  self.assertEqual(self.s['issues'][-1]['status'],'open')
  e.apply(self.s,self.p,'revision',{'revision':'v03','evidence_files':['artifacts/final.png']})
  e.apply(self.s,self.p,'resolve',dict(data,fixed_revision='v03'))
  self.approve('R6.brand_copy')
  self.assertEqual(self.s['checks']['R6.brand_copy']['status'],'approved')
 def test_transform_is_rejected_instead_of_silently_ignored(self):
  self.spec['elements'][0]['rotation']=15
  result,_=validate_project(self.spec,self.p,'production')
  self.assertEqual(result['status'],'BLOCK')
 def test_full_pipeline_bound_reports_signoff_and_final_change(self):
  self.spec['color_checks']=[{'id':'brand','rect':[0,0,1,1],'expected_hex':'#005EAD','tolerance':0,'min_match_ratio':1}]
  self.write(self.bp,self.spec);self.preflight()
  observations={'source':'unit test actual solid background','annotation_method':'manual','image_sha256':digest(self.final),'boxes':{'bg':[0,0,1,1]}}
  self.write(self.p/'observed.json',observations)
  commands=[('layout_audit.py',['--spec',self.bp,'--observed',self.p/'observed.json','--image',self.final,'--out',self.art/'layout_audit.json']),('pixel_audit.py',['--image',self.final,'--spec',self.bp,'--out',self.art/'pixel_audit.json']),('export_layers.py',['--spec',self.bp,'--out',self.art/'layers','--approved',self.final])]
  for script,args in commands:
   run=self.run_script(script,*args);self.assertEqual(run.returncode,0,run.stdout+run.stderr)
  e.apply(self.s,self.p,'inspect',{})
  for module in self.mods:
   for check in module['checks']:
    if check['id']=='R4.lock':e.apply(self.s,self.p,'na',{'check_id':check['id'],'issue':'unit test new composition, no local edit'})
    else:self.approve(check['id'])
   e.apply(self.s,self.p,'signoff',{'stage':module['id']})
  self.assertEqual(len(self.s['signoffs']),7)
  Image.new('RGB',(64,96),'red').save(self.final)
  e.refresh(self.s,self.p)
  self.assertNotIn('R6',self.s['signoffs']);self.assertEqual(self.s['checks']['R6.identity_product']['status'],'stale')
 def test_revision_change_invalidates_final_checks_and_reuses_no_version(self):
  self.approve('R6.identity_product')
  Image.new('RGB',(64,96),'red').save(self.final)
  e.refresh(self.s,self.p)
  self.assertEqual(self.s['checks']['R6.identity_product']['status'],'stale')
  with self.assertRaises(e.ReviewError):e.apply(self.s,self.p,'revision',{'revision':'v01','evidence_files':['artifacts/final.png']})
  e.apply(self.s,self.p,'revision',{'revision':'v02','evidence_files':['artifacts/final.png']})
 def test_F04_background_export_matches_preview_and_approved_image(self):
  r=self.run_script('export_layers.py','--spec',self.bp,'--out',self.art/'layers','--approved',self.final)
  self.assertEqual(r.returncode,0,r.stderr)
  report=json.loads((self.art/'layers/layer_export_report.json').read_text(encoding='utf-8'))
  self.assertIn('bg',report['included_layers']);self.assertTrue(report['approved_composite_match'])
  with Image.open(self.art/'layers/merged_preview.png') as out:self.assertEqual(out.getpixel((0,0))[:3],(0,94,173))
  self.preflight()
  with Image.open(self.art/'layout_preview.png') as preview,Image.open(self.art/'layers/merged_preview.png') as exported:self.assertEqual(preview.convert('RGBA').tobytes(),exported.convert('RGBA').tobytes())
 def test_F04_wrong_approved_composite_blocks(self):
  Image.new('RGB',(64,96),'red').save(self.final)
  r=self.run_script('export_layers.py','--spec',self.bp,'--out',self.art/'layers','--approved',self.final)
  self.assertEqual(r.returncode,2)
 def locked_spec(self,authorized=False):
  self.spec['elements']=[{'id':'face','role':'person','source':'source.png','box':[0,0,1,1],'lock':'L0','required':True}]
  self.spec['editable_regions']=[{'id':'edit','rect':[.25,.25,.75,.75]}]
  if authorized:
   (self.p/'authorization.md').write_text('UNIT TEST ONLY: approved local subregion edit',encoding='utf-8')
   self.spec['elements'][0]['edit_authorization']={'reason':'unit test approved patch','evidence_file':'authorization.md','regions':[{'rect':[.25,.25,.75,.75]}]}
  self.write(self.bp,self.spec)
  Image.new('RGBA',(64,96),(200,0,0,255)).save(self.p/'candidate.png')
 def test_F05_L0_inside_editable_mask_blocks(self):
  self.locked_spec()
  r=self.run_script('locked_edit.py','--spec',self.bp,'--baseline',self.final,'--candidate',self.p/'candidate.png','--out',self.art/'locked.png')
  self.assertNotEqual(r.returncode,0);self.assertFalse((self.art/'locked.png').exists())
 def test_authorized_subregion_and_feather_preserve_every_outside_pixel(self):
  self.locked_spec(True)
  for feather in [0,5]:
   out=self.art/f'locked-{feather}.png'
   r=self.run_script('locked_edit.py','--spec',self.bp,'--baseline',self.final,'--candidate',self.p/'candidate.png','--out',out,'--feather',feather)
   self.assertEqual(r.returncode,0,r.stderr)
   with Image.open(out) as image,Image.open(self.final) as before:
    actual=np.array(image.convert('RGBA'));expected=np.array(before.convert('RGBA'))
   mask=np.zeros((96,64),dtype=bool);mask[24:72,16:48]=True
   self.assertTrue(np.array_equal(actual[~mask],expected[~mask]));self.assertTrue(np.any(actual[mask]!=expected[mask]))
 def test_F06_draft_and_production_distinguish_missing_L0_asset(self):
  self.spec['elements']=[{'id':'person','role':'person','box':[0,0,.2,.2],'lock':'L0'}]
  draft,_=validate_project(self.spec,self.p,'draft');production,_=validate_project(self.spec,self.p,'production')
  self.assertEqual(draft['status'],'DRAFT_ONLY');self.assertEqual(production['status'],'BLOCK')
 def test_F07_transparent_brand_color_is_not_pass(self):
  self.spec['color_checks']=[{'id':'brand','rect':[0,0,1,1],'expected_hex':'#005EAD','tolerance':0,'min_match_ratio':1}]
  self.write(self.bp,self.spec)
  Image.new('RGBA',(64,96),(0,94,173,0)).save(self.final)
  r=self.run_script('pixel_audit.py','--image',self.final,'--spec',self.bp,'--out',self.art/'pixel_audit.json')
  self.assertEqual(r.returncode,2)
  report=json.loads((self.art/'pixel_audit.json').read_text(encoding='utf-8'));self.assertGreater(report['checks'][0]['nonopaque_pixels'],0)
 def test_untagged_color_requires_explicit_assumption(self):
  self.spec.pop('color_management');self.spec['color_checks']=[{'id':'brand','rect':[0,0,1,1],'expected_hex':'#005EAD'}]
  self.write(self.bp,self.spec)
  r=self.run_script('pixel_audit.py','--image',self.final,'--spec',self.bp,'--out',self.art/'pixel_audit.json')
  self.assertEqual(r.returncode,3)
 def test_F08_documented_aliases_work(self):
  boxes={'a':[.1,.1,.1,.1],'b':[0,0,1,1]}
  self.assertTrue(evaluate_constraint({'type':'contained_in','a':'a','b':'b'},boxes)[0])
  self.assertTrue(evaluate_constraint({'type':'area_ratio_min','a':'a','b':'b','ratio':.001},boxes)[0])
 def test_F09_array_report_returns_block_not_exception(self):
  self.write(self.art/'preflight.json',[])
  e.apply(self.s,self.p,'inspect',{})
  self.assertEqual(self.s['checks']['R2.preflight']['auto']['status'],'BLOCK')
 def test_F10_interleaved_writes_detect_conflict(self):
  a=e.load(self.p);b=e.load(self.p)
  data={'evidence':'UNIT TEST actual evidence','evidence_files':['brief.md']}
  e.apply(a,self.p,'approve',dict(data,check_id='R0.roles'));e.write_state(self.p,a)
  e.apply(b,self.p,'approve',dict(data,check_id='R0.assets'))
  with self.assertRaises(ConflictError):e.write_state(self.p,b)
  self.assertEqual(e.load(self.p)['checks']['R0.roles']['status'],'approved')
 def test_two_cli_transactions_preserve_both_approvals(self):
  procs=[]
  for cid in ['R0.roles','R0.assets']:
   args=[sys.executable,'-X','utf8',str(ROOT/'scripts/review_engine.py'),'approve','--project',str(self.p),'--check-id',cid,'--evidence','unit test fixture evidence','--evidence-files','brief.md']
   procs.append(subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE))
  for proc in procs:
   stdout,stderr=proc.communicate(timeout=20);self.assertEqual(proc.returncode,0,stderr.decode('utf-8'))
  final=e.load(self.p)
  for cid in ['R0.roles','R0.assets']:self.assertEqual(final['checks'][cid]['status'],'approved')
 def test_F11_unbound_observation_is_rejected(self):
  observations={'source':'copied boxes','boxes':{'bg':[0,0,1,1]}}
  self.write(self.p/'observed.json',observations)
  r=self.run_script('layout_audit.py','--spec',self.bp,'--observed',self.p/'observed.json','--image',self.final,'--out',self.art/'layout_audit.json')
  self.assertNotEqual(r.returncode,0)
  observations.update(image_sha256=digest(self.final),annotation_method='manual')
  self.write(self.p/'observed.json',observations)
  r=self.run_script('layout_audit.py','--spec',self.bp,'--observed',self.p/'observed.json','--image',self.final,'--out',self.art/'layout_audit.json')
  self.assertEqual(r.returncode,0,r.stderr)
 def test_local_edit_skips_only_inapplicable_modules_requires_baseline(self):
  self.s['task_mode']='local-edit'
  status={m['id']:m['status'] for m in e.module_statuses(self.s)}
  self.assertEqual(status['R1'],'SKIPPED');self.assertEqual(status['R3'],'SKIPPED')
  for c in self.mods[0]['checks']:self.approve(c['id'])
  with self.assertRaises(e.ReviewError):e.apply(self.s,self.p,'signoff',{'stage':'R0'})
  e.apply(self.s,self.p,'baseline',{'evidence':'unit test baseline approval record','evidence_files':['brief.md','artifacts/final.png']})
  for c in self.mods[0]['checks']:self.approve(c['id'])
  e.apply(self.s,self.p,'signoff',{'stage':'R0'})
  self.assertNotIn('R1',self.s['signoffs'])
 def test_migration_preserves_history_clears_unbound_approvals(self):
  old={'schema':'cvisual.review.state.v1','project_name':'legacy','seq':7,'history':[{'seq':7,'event':'legacy approval'}], 'checks':{'R0.roles':{'status':'approved','revision':1,'evidence':'legacy'}},'issues':[],'signoffs':{'R0':{'at':'old'}}}
  self.write(self.p/'review_state.json',old)
  e.migrate(self.p);s=e.load(self.p)
  self.assertTrue((self.p/'review_state.before-v2-migration.json').is_file());self.assertEqual(s['checks']['R0.roles']['status'],'stale');self.assertEqual(s['signoffs'],{})
  self.assertEqual(s['history'][0]['event'],'legacy approval')
 def test_HTTP_conflict_and_read_refresh(self):
  server=web.ReviewServer(('127.0.0.1',0),web.Handler,self.p)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   url=f'http://127.0.0.1:{server.server_port}'
   body=json.dumps({'action':'unknown','expected_seq':-1,'data':{'check_id':'R0.roles','issue':'unit test missing source'}}).encode()
   with self.assertRaises(HTTPError) as exc:urlopen(Request(url+'/api/action',body,{'Content-Type':'application/json','Origin':url}))
   self.assertEqual(exc.exception.code,409)
   for bad in ['/api/file?path=../../outside.png','/api/file?path=review_state.json']:
    with self.assertRaises(HTTPError):urlopen(url+bad)
  finally:server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main()
