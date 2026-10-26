#!/usr/bin/env python3
"""File-backed stage handoffs. Compression/transport only, never audit approval."""
import argparse,hashlib,json,os,sys,tempfile
from pathlib import Path
from _storage import project_lock

FIELDS={
 'R0':{'observations','references'},
 'R1':{'brand_rules','asset_roles','purpose','decisions'},
 'R2':{'canvas','elements','constraints','copy','style_rules','protected_regions','editable_regions'},
 'R3':{'candidate','layers','tasks','generation_prompt_file'},
 'R4':{'issues','checks','observed_file'},
 'R5':{'repairs','baseline','approved_master'},
 'R6':{'deliverables','acceptance'}}
DEPS={'R0':[],'R1':['R0'],'R2':['R1'],'R3':['R1','R2'],'R4':['R1','R2','R3'],'R5':['R1','R2','R3','R4'],'R6':['R1','R3','R4','R5']}
SCHEMA='cvisual.context.packet.v2'
LEGACY_SCHEMA='cvisual.context.packet.v1'

def dumps(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def local(root,name):
 p=(root/name).resolve()
 if not p.is_relative_to(root):raise ValueError('path outside project: '+str(name))
 return p

def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.context-',suffix='.json')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(dumps(obj))
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def packet_id(obj):
 return hashlib.sha256(dumps({k:v for k,v in obj.items() if k!='details'}).encode()).hexdigest()

def put_packet(root,stage,body):
 root=Path(root).resolve()
 if not isinstance(body,dict):raise ValueError('packet must be an object')
 extra=set(body)-{'summary','data','critical','evidence_files','details'}
 if extra:raise ValueError('unknown packet fields: '+','.join(sorted(extra)))
 data=body.get('data',{})
 if not isinstance(data,dict) or set(data)-FIELDS[stage]:raise ValueError('unsupported stage data fields')
 critical=body.get('critical',[])
 if not isinstance(critical,list):raise ValueError('critical must be a list')
 summary=body.get('summary','')
 if not isinstance(summary,str):raise ValueError('summary must be text')
 paths=body.get('evidence_files',[])
 if not isinstance(paths,list):raise ValueError('evidence_files must be a list')
 bound={}
 for name in paths:
  if not isinstance(name,str):raise ValueError('evidence path must be text')
  p=local(root,name)
  if not p.is_file():raise ValueError('missing evidence: '+name)
  bound[p.relative_to(root).as_posix()]=sha(p)
 record={'schema':SCHEMA,'stage':stage,'summary':summary,'data':data,'critical':critical,'files':bound,'details':body.get('details')}
 target=local(root,'.visual-context/stages/'+stage+'.json')
 with project_lock(root):
  record['upstream']={}
  for sid in DEPS[stage]:
   source=local(root,'.visual-context/stages/'+sid+'.json')
   record['upstream'][sid]=packet_id(json.loads(source.read_text(encoding='utf-8'))) if source.is_file() else None
  atomic(target,record)
 return {'status':'STORED','stage':stage,'path':str(target),'approval':'not_a_review_decision'}

def build_context(root,stage,since=None,budget=8000):
 root=Path(root).resolve()
 folder=local(root,'.visual-context/stages')
 packets={};stale=[]
 # Critical constraints from every available ancestor travel even if its narrative is omitted.
 for sid in list(FIELDS)[:list(FIELDS).index(stage)+1]:
  p=folder/(sid+'.json')
  if not p.exists():continue
  obj=json.loads(p.read_text(encoding='utf-8'))
  if obj.get('schema') not in (SCHEMA,LEGACY_SCHEMA) or obj.get('stage')!=sid:raise ValueError('invalid context packet '+sid)
  for name,h in obj.get('files',{}).items():
   f=local(root,name)
   if not f.is_file() or sha(f)!=h:stale.append({'stage':sid,'file':name})
  packets[sid]=obj
 for sid,obj in packets.items():
  if 'upstream' not in obj:continue
  for dep,old_id in obj['upstream'].items():
   actual=packet_id(packets[dep]) if dep in packets else None
   if actual!=old_id:stale.append({'stage':sid,'upstream_stage':dep})
 if stale:
  affected={row['stage'] for row in stale}
  while True:
   added={sid for sid in packets if set(DEPS[sid]) & affected}-affected
   if not added:break
   affected.update(added)
  return {'status':'STALE','changed_sources':stale,'refresh_stages':[sid for sid in packets if sid in affected],'action':'refresh affected packets; no cached approval'},2
 selected=list(dict.fromkeys(DEPS[stage]+([stage] if stage in packets else [])))
 critical=[];seen=set()
 for obj in packets.values():
  for item in obj['critical']:
   k=dumps(item)
   if k not in seen:seen.add(k);critical.append(item)
 context={'project_root':str(root),'target':stage,'unbound_packets':[sid for sid,obj in packets.items() if 'upstream' not in obj],'missing_packets':[sid for sid in DEPS[stage] if sid not in packets],
          'critical':critical,'stages':{sid:{'summary':packets[sid]['summary'],'data':packets[sid]['data'],'evidence_files':packets[sid]['files']} for sid in selected if sid in packets}}
 state=local(root,'review_state.json')
 if state.is_file():
  from review_engine import snapshot,review_brief
  context['review']=review_brief(snapshot(root))
 context['notice']='handoff only; missing_packets must be resolved from actual project, never interpreted as approved'
 fingerprint=hashlib.sha256((dumps(context)+sha(__file__)).encode()).hexdigest()
 cache=local(root,'.visual-context/cache/'+stage+'.json')
 try:
  old=json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else None
  if not isinstance(old,dict) or not isinstance(old.get('context'),dict):old=None
 except (ValueError,OSError):old=None
 chars=len(dumps(context))
 result={'status':'READY','context_id':fingerprint,'chars':chars,'soft_budget_exceeded':chars>budget}
 if since==fingerprint:result['kind']='unchanged'
 elif old and since==old['context_id']:
  previous=old['context'];result.update(kind='delta',base=since,changed={k:v for k,v in context.items() if previous.get(k)!=v},removed=[k for k in previous if k not in context])
 else:result.update(kind='full',context=context)
 atomic(cache,{'context_id':fingerprint,'context':context})
 if chars>budget:result['budget_note']='critical constraints retained; reduce narrative/details at source, never truncate rules or exact copy'
 return result,0

def main():
 ap=argparse.ArgumentParser();ap.add_argument('command',choices=['put','build'])
 ap.add_argument('--project',type=Path,required=True);ap.add_argument('--stage',choices=list(FIELDS),required=True)
 ap.add_argument('--input',type=Path);ap.add_argument('--since');ap.add_argument('--budget-chars',type=int,default=8000)
 args=ap.parse_args();root=args.project.resolve()
 try:
  if args.command=='put':
   if not args.input:ap.error('put needs --input')
   result=put_packet(root,args.stage,json.loads(args.input.read_text(encoding='utf-8')));code=0
  else:
   if args.budget_chars<1:raise ValueError('budget must be positive')
   result,code=build_context(root,args.stage,args.since,args.budget_chars)
  print(dumps(result));return code
 except (ValueError,OSError,KeyError,TypeError) as exc:print(dumps({'status':'BLOCK','error':str(exc)}));return 2
if __name__=='__main__':sys.exit(main())
