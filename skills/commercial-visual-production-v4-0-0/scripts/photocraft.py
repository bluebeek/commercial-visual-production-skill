"""PhotoCraft engine plans and evidence checks; the assistant makes MCP calls."""
import copy,json,re
from pathlib import Path
import numpy as np
from PIL import Image
from _workflow import *
from _common import load_project,mask_for_regions,protection_mask
from ora_verify import read_layers

def same(a,b):return a.size==b.size and a.convert('RGBA').tobytes()==b.convert('RGBA').tobytes()
def stack_equal(before,after,changed=None,mask=None,color=None):
 if [x['name'] for x in before]!=[x['name'] for x in after]:raise WorkflowError('PhotoCraft layer order/name changed')
 for old,new in zip(before,after):
  a=np.asarray(old['image']);b=np.asarray(new['image'])
  if a.shape!=b.shape:raise WorkflowError('PhotoCraft layer dimensions changed')
  if old['name']!=changed:
   if np.any(a!=b):raise WorkflowError('non-target source layer changed: '+old['name'])
  else:
   if np.any(a[~mask]!=b[~mask]):raise WorkflowError('target layer changed outside authorized rectangle')
   if color is not None and not np.all(b[mask]==color):raise WorkflowError('rectangle fill did not meet target color')

def read_receipt(root,path,state):
 rec=json.loads(local(root,path).read_text(encoding='utf-8'))
 if rec.get('schema')!='cvisual.photocraft.receipt.v1' or rec.get('backend')!='photocraft' or rec.get('mode')!='engine':raise WorkflowError('missing PhotoCraft engine receipt')
 if rec.get('fixture') and not state['test_mode']:raise WorkflowError('simulated tool receipt forbidden in non-test project')
 calls=rec.get('calls')
 if not isinstance(calls,list) or not calls:raise WorkflowError('actual tool calls required')
 for c in calls:
  if c.get('isError') or not isinstance(c.get('args'),dict):raise WorkflowError('PhotoCraft tool error or incomplete step')
  result=c.get('result')
  if isinstance(result,dict):
   if result.get('failed',0):raise WorkflowError('partial batch failed; earlier steps remain applied')
   for warning in result.get('warnings',[]):
    allowed=c.get('tool') in ('doc_save','doc_export') and Path(c['args'].get('path','')).suffix.lower()=='.png' and re.fullmatch(r'[0-9]+ layer\(s\) flattened; layers, masks and blend modes are not kept',warning)
    if not allowed:raise WorkflowError('PhotoCraft warning blocks qualification: '+warning)
 return rec

def inspect_trace(root,rec,input_path,commands=None):
 """Check current document bindings and every command; never trust an active index alone."""
 input_path=local(root,input_path);opened={};active=None;snapshots={};mappings={};states=[];executed=[];outputs={}
 for c in rec['calls']:
  tool=c['tool'];a=c['args'];r=c.get('result')
  if tool=='doc_open':
   p=local(root,a['path']);idx=r.get('index') if isinstance(r,dict) else None
   if not isinstance(idx,int):raise WorkflowError('open did not return a document index')
   if idx in opened:raise WorkflowError('document index reused without a new session')
   opened[idx]=p;active=idx
  elif tool=='doc_select':
   idx=a.get('index')
   if idx not in opened or not isinstance(r,dict) or r.get('active')!=idx:raise WorkflowError('wrong active PhotoCraft document')
   active=idx
  elif tool=='doc_inspect':
   idx=a.get('index',active)
   if idx not in opened or not isinstance(r,dict) or local(root,r.get('path'))!=opened[idx]:raise WorkflowError('inspection belongs to another document')
   layers=r.get('layers',[]);ids=[l.get('id') for l in layers];names=[l.get('name') for l in layers]
   if len(ids)!=len(set(ids)) or len(names)!=len(set(names)) or not ids:raise WorkflowError('duplicate/missing layer mapping')
   if idx in mappings and mappings[idx]!=list(zip(ids,names)):raise WorkflowError('stale PhotoCraft layer mapping')
   mappings[idx]=list(zip(ids,names));snapshots[idx]=r;states.append((opened[idx],r))
  elif tool in ('command_run','command_batch'):
   if active not in opened or active not in snapshots or opened[active]!=input_path:raise WorkflowError('command not bound to inspected baseline document')
   steps=a.get('steps') if tool=='command_batch' else [{'id':a.get('id'),'params':a.get('params',{})}]
   if not isinstance(steps,list):raise WorkflowError('missing batch steps')
   for step in steps:
    entry={'id':step['id'],'params':step.get('params',{})}
    if commands is None:
     if entry['id'] not in ('layer.hideLayers','layer.showLayers'):raise WorkflowError('audit cannot edit document pixels')
     if entry['params'].get('layer') not in {l['id'] for l in snapshots[active]['layers']}:raise WorkflowError('unknown layer id')
    else:
     if len(executed)>=len(commands) or entry!=commands[len(executed)]:raise WorkflowError('actual editor command differs from compiled plan')
    executed.append(entry)
   snapshots.pop(active,None) # must reobserve before the next command
  elif tool in ('doc_export','doc_save'):
   idx=a.get('index',active)
   if idx not in opened or not isinstance(r,dict):raise WorkflowError('export document unknown')
   p=local(root,a.get('path'));q=local(root,r.get('path'))
   if p!=q:raise WorkflowError('actual output path differs')
   outputs[p]=opened[idx]
  else:raise WorkflowError('unsupported receipt tool: '+str(tool))
 if input_path not in opened.values():raise WorkflowError('actual baseline was not opened')
 if commands is not None and (active not in opened or opened[active]!=input_path):raise WorkflowError('wrong active PhotoCraft document')
 if commands is not None and executed!=commands:raise WorkflowError('editor steps incomplete')
 return states,outputs

def prepare_editor(s,root,d):
 from production import current_inputs,implementation
 from checks import inspect_layers
 jid=ident(d.get('id'));baseline=d.get('baseline')
 if jid in s['jobs'] or baseline!=s['working_revision'] or not rev_fresh(s,root,baseline,False):raise WorkflowError('editor needs a unique id and selected unchanged baseline')
 if context(s,root)['status']!='READY' or not approved_blueprint(s,root):raise WorkflowError('current approved intent required')
 r=s['revisions'][baseline];p,base=load_project(local(root,r['spec']));w=p['canvas']['width'];h=p['canvas']['height']
 op=d.get('operation',{});rect=op.get('rect',[]);target=op.get('layer');color=op.get('color','')
 if op.get('type')!='rectangle_fill' or len(rect)!=4 or any(type(v)!=int for v in rect) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):raise WorkflowError('only an explicit integer rectangle fill is supported')
 x,y,rw,rh=rect
 if x<0 or y<0 or rw<1 or rh<1 or x+rw>w or y+rh>h:raise WorkflowError('rectangle outside canvas')
 if target not in {e['id'] for e in p['elements']}:raise WorkflowError('target source layer missing')
 mask=np.zeros((h,w),dtype=bool);mask[y:y+rh,x:x+rw]=True
 allowed=mask_for_regions(p.get('editable_regions',[]),w,h)
 if np.any(mask&~allowed) or np.any(mask&protection_mask(p,base,w,h)):raise WorkflowError('editor rectangle exceeds authorization or protected pixels')
 review=d.get('intent_review',{})
 if review and (review.get('unresolved')!=[] or set(review.get('covered_requirement_ids',[]))!={r['id'] for r in active(s)} or len(review.get('observation','').strip())<5):raise WorkflowError('editor intent coverage review required')
 folder=root/'production'/jid;folder.mkdir(parents=True,exist_ok=False)
 inspect_layers(root,r,folder/'input')
 input_path=(folder/'input/layout_layers.ora').relative_to(root).as_posix()
 plan={'backend':'photocraft','mode':'engine','input':input_path,'baseline':baseline,'operation':op,'goal':d.get('goal'),'outputs':{'png':(folder/'raw.png').relative_to(root).as_posix(),'ora':(folder/'raw.ora').relative_to(root).as_posix()}}
 if not plan['goal']:raise WorkflowError('actual edit goal required')
 atomic(folder/'editor_plan.json',plan)
 files=current_inputs(s,root,r['spec']);files.update(r['files']);files.update(bind(root,[input_path]))
 j={'id':jid,'kind':'editor-local','execution_kind':'photocraft','status':'waiting_execution','goal':plan['goal'],'change_request':plan['goal'],'baseline':baseline,'spec':r['spec'],'blueprint':p,'blueprint_id':s['stages']['R2']['id'],'requirements':copy.deepcopy(active(s)),'rules_hash':rules_hash(s),'coverage':{r['id']:{'production':r['method'],'check':'req:'+r['id']} for r in active(s)},'input_files':files,'compiled_files':bind(root,[(folder/'editor_plan.json').relative_to(root)]),'implementation':implementation(),'editable_regions':[{'id':'editor-rectangle','rect':[x/w,y/h,(x+rw)/w,(y+rh)/h]}],'application_regions':[{'id':'editor-rectangle','rect':[x/w,y/h,(x+rw)/w,(y+rh)/h]}],'feather':0,'input_images':[],'output_files':{},'editor_plan':plan,'intent_review':review,'at':now()}
 s['jobs'][jid]=j;s['editor_backend']='photocraft'
 return {'status':'WAITING_EXECUTION','job_id':jid,'plan':plan,'image_calls_added':0}

def begin_editor(s,root,d):
 from production import validate_job
 j=s['jobs'][d['job_id']]
 if j['kind']!='editor-local' or j['status']!='waiting_execution':raise WorkflowError('editor job already attempted; do not replay')
 validate_job(s,root,j,False)
 review=d.get('intent_review') or j.get('intent_review',{})
 if review.get('unresolved')!=[] or set(review.get('covered_requirement_ids',[]))!=set(j['coverage']) or len(review.get('observation','').strip())<5:raise WorkflowError('assistant intent review required before editor execution')
 rec=read_receipt(root,d['receipt'],s)
 states,_=inspect_trace(root,rec,j['editor_plan']['input'],[])
 if not states or states[-1][0]!=local(root,j['editor_plan']['input']):raise WorkflowError('fresh baseline inspection required')
 snap=states[-1][1]
 image,layers=read_layers(local(root,j['editor_plan']['input']))
 if snap.get('width')!=image.width or snap.get('height')!=image.height or snap.get('depth')!=8 or snap.get('mode')!='Rgb' or [x['name'] for x in snap['layers']]!=[x['name'] for x in layers]:raise WorkflowError('PhotoCraft import differs from baseline')
 for l in snap['layers']:
  if l.get('kind')!='Pixel' or not l.get('visible') or l.get('opacity')!=1 or l.get('blend')!='Normal':raise WorkflowError('unsupported imported layer properties')
 op=j['editor_plan']['operation'];lid=next(l['id'] for l in snap['layers'] if l['name']==op['layer']);x,y,w,h=op['rect']
 commands=[{'id':'layer.select','params':{'layer':lid}},{'id':'select.rect','params':{'x':x,'y':y,'width':w,'height':h,'antiAlias':False,'feather':0}},{'id':'edit.fill','params':{'contents':'color','color':op['color'],'opacity':100,'mode':'normal'}}]
 j.update(status='running',intent_review=review,editor_commands=commands,editor_import_receipt=d['receipt'],editor_import_files=bind(root,[d['receipt']]),editor_snapshot=snap,started_at=now())
 return {'status':'RUNNING','job_id':j['id'],'commands':commands,'outputs':j['editor_plan']['outputs'],'image_calls_added':0}

def finish_editor(s,root,d):
 from production import validate_job
 j=s['jobs'][d['job_id']]
 if j['kind']!='editor-local' or j['status']!='running':raise WorkflowError('editor job not running')
 if d.get('error'):
  j.update(status='failed',error=str(d['error']),finished_at=now());return {'status':'FAILED','job_id':j['id'],'image_calls_added':0}
 try:
  validate_job(s,root,j,False)
  if not fresh(root,j['editor_import_files']):raise WorkflowError('begin receipt changed')
  rec=read_receipt(root,d['receipt'],s);states,outputs=inspect_trace(root,rec,j['editor_plan']['input'],j['editor_commands'])
  first=next(snapshot for p,snapshot in states if p==local(root,j['editor_plan']['input']))
  if first!=j['editor_snapshot']:raise WorkflowError('begun document mapping changed')
  files=j['editor_plan']['outputs'];png=local(root,files['png']);ora=local(root,files['ora']);original=local(root,j['editor_plan']['input'])
  if outputs.get(png)!=original or outputs.get(ora)!=original:raise WorkflowError('exports belong to wrong document')
  before,old=read_layers(original);after,new=read_layers(ora)
  op=j['editor_plan']['operation'];x,y,w,h=op['rect'];mask=np.zeros((before.height,before.width),dtype=bool);mask[y:y+h,x:x+w]=True
  color=[int(op['color'][i:i+2],16) for i in (1,3,5)]+[255]
  stack_equal(old,new,op['layer'],mask,color)
  with Image.open(png) as im:
   if not same(after,im):raise WorkflowError('editor PNG differs from ORA')
  a=np.asarray(before);b=np.asarray(after)
  if a.shape!=b.shape or np.any(a[~mask]!=b[~mask]):raise WorkflowError('raw edit changed pixels outside rectangle')
  if not np.all(b[mask]==color):raise WorkflowError('planned fill is hidden by higher layers or not visible in final composite')
  output_files={**bind(root,[files['png'],files['ora'],d['receipt']]),**j['editor_import_files']}
  j.update(status='editor_ready',output=files['png'],output_files=output_files,tool_metadata={'backend':'photocraft','mode':'engine','fixture':bool(rec.get('fixture')),'receipt':d['receipt'],'backend_version':rec.get('backend_version','NOT_EXPOSED')},finished_at=now())
  return {'status':'EDITOR_READY','job_id':j['id'],'image_calls_added':0,'raw_outside_changed':0,'non_target_layers_unchanged':True}
 except (ValueError,OSError,KeyError,TypeError) as e:
  j.update(status='failed',error=str(e),finished_at=now(),failure_receipt=d.get('receipt'))
  return {'status':'FAILED','job_id':j['id'],'error':str(e),'image_calls_added':0}

def verify_editor(s,root,d):
 """Bind an actual PhotoCraft round trip to a checked candidate; no invented GUI result."""
 from checks import implementation
 rid=d['revision'];r=s['revisions'][rid];s['editor_backend']='photocraft'
 if not rev_fresh(s,root,rid):raise WorkflowError('candidate changed')
 layercheck=s['checks'][rid].get('layers',{})
 if layercheck.get('status')!='PASS' or layercheck.get('implementation')!=implementation('layers') or layercheck.get('rules_hash')!=rules_hash(s) or not fresh(root,layercheck.get('files',{})):raise WorkflowError('current layer checks required')
 folder=root/'editor-checks'/rid/('%08d'%(s['seq']+1));folder.mkdir(parents=True,exist_ok=False)
 def record(status,detail,files):
  rec={'status':status,'detail':detail,'revision':rid,'rules_hash':rules_hash(s),'files':{**r['files'],**files},'implementation':implementation('editor'),'actor':'machine','at':now()}
  report=folder/'editor.json';atomic(report,rec);rec['files'].update(bind(root,[report.relative_to(root)]));s['checks'][rid]['editor']=rec
  return {'revision':rid,'status':status,'detail':detail}
 try:
  source=local(root,d['input']);relative=source.relative_to(root).as_posix()
  if relative not in layercheck['files'] or sha(source)!=layercheck['files'][relative]:raise WorkflowError('editor input not bound to current layer check')
  rec=read_receipt(root,d['receipt'],s);states,outputs=inspect_trace(root,rec,d['input'])
  baseline,layers=read_layers(source);roundtrip,new=read_layers(local(root,d['ora']));stack_equal(layers,new)
  if not same(baseline,roundtrip):raise WorkflowError('editor roundtrip composite changed')
  with Image.open(local(root,d['png'])) as im:
   if not same(baseline,im):raise WorkflowError('editor exported PNG changed')
  if outputs.get(local(root,d['ora']))!=source or outputs.get(local(root,d['png']))!=source:raise WorkflowError('roundtrip exports not from checked source')
  reopens=[snapshot for p,snapshot in states if p==local(root,d['ora'])]
  if not reopens:raise WorkflowError('roundtrip must actually be reopened and inspected')
  for st in [snapshot for p,snapshot in states if p in (source,local(root,d['ora']))]:
   if st.get('width')!=baseline.width or st.get('height')!=baseline.height or st.get('depth')!=8 or st.get('mode')!='Rgb' or [l['name'] for l in st['layers']]!=[l['name'] for l in layers]:raise WorkflowError('actual imported structure differs')
  original_states=[snapshot for p,snapshot in states if p==source]
  for name in [x['name'] for x in layers]:
   hidden=[i for i,st in enumerate(original_states) if next(l for l in st['layers'] if l['name']==name)['visible'] is False]
   if not hidden or not any(all(l['visible'] for l in st['layers']) for st in original_states[max(hidden)+1:]):raise WorkflowError('missing hide/restore evidence: '+name)
  native='NOT_TESTED'
  files=bind(root,[d[k] for k in ('input','ora','png','receipt')])
  if d.get('native') or d.get('native_png'):
   native_path=local(root,d['native']);native_png=local(root,d['native_png']);native_ora=local(root,d['native_ora'])
   ns=[st for p,st in states if p==native_path]
   if not ns or [l['name'] for l in ns[-1]['layers']]!=[l['name'] for l in layers] or outputs.get(native_path)!=source or outputs.get(native_png)!=native_path or outputs.get(native_ora)!=native_path:raise WorkflowError('native document not reopened/inspected')
   with Image.open(native_png) as im:
    if not same(baseline,im):raise WorkflowError('native reopen composite changed')
   _,native_layers=read_layers(native_ora);stack_equal(layers,native_layers)
   files.update(bind(root,[d['native'],d['native_png'],d['native_ora']]));native='PASS'
  return record('PASS',{'backend':'photocraft','mode':'engine','layers':[x['name'] for x in layers],'per_layer_rgba_match':True,'roundtrip_rgba_match':True,'native_reopen':native,'gui':'NOT_TESTED','backend_version':rec.get('backend_version','NOT_EXPOSED'),'fixture':bool(rec.get('fixture'))},files)
 except (ValueError,OSError,KeyError,TypeError) as e:
  return record('FAIL',{'error':str(e),'backend':'photocraft','gui':'NOT_TESTED'},bind(root,[d['receipt']]) if d.get('receipt') and local(root,d['receipt'],False).is_file() else {})
