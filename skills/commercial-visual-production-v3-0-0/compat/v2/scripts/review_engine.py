#!/usr/bin/env python3
"""Evidence-bound human review; declared reviewers are not authenticated signatures."""
from __future__ import annotations
import argparse,json,sys,uuid
from pathlib import Path
from datetime import datetime,timezone
from _evidence import digest,verify_report
from _storage import ConflictError,project_lock,write_unlocked

ROOT=Path(__file__).resolve().parents[1]
DEFINITIONS=ROOT/'assets/review_modules.json'
STATE_FILE='review_state.json'
SCHEMA='cvisual.review.state.v2'
AUTO_TOOLS={'R2.preflight':'preflight','R4.lock':'locked_edit','R5.geometry':'layout_audit','R6.color':'pixel_audit','R6.layers':'layer_export'}
MODES={'full':None,'local-edit':{'R0','R4','R5','R6'},'delivery':{'R0','R6'}}
class ReviewError(ValueError):pass
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def definitions():
 raw=json.loads(DEFINITIONS.read_text(encoding='utf-8'));mods=raw['modules']
 checks={c['id']:dict(c,stage=m['id']) for m in mods for c in m['checks']}
 if len(checks)!=sum(len(m['checks']) for m in mods):raise ReviewError('duplicate check id')
 if any(t not in checks for c in checks.values() for t in c.get('affects',[])):raise ReviewError('invalid dependency')
 return raw,mods,checks
def path_for(project):return Path(project).resolve()/STATE_FILE
def event(s,kind,details):
 s['seq']+=1;s['modified_at']=now();s['history'].append({'seq':s['seq'],'at':now(),'event':kind,'details':details})
def new_state(name,mode='full'):
 if mode not in MODES:raise ReviewError('invalid task_mode')
 _,_,checks=definitions()
 return {'schema':SCHEMA,'project_id':uuid.uuid4().hex,'definitions_sha256':digest(DEFINITIONS),'project_name':name,'task_mode':mode,
         'created_at':now(),'modified_at':now(),'seq':0,'checks':{
          c:{'status':'pending','revision':0,'evidence':'','files':{},'note':'','reviewed_at':None,'auto':None} for c in checks},
         'issues':[],'signoffs':{},'history':[],'active_revision':None,'baseline':None,'_loaded_seq':None}
def write_state(project,state):
 with project_lock(project):write_unlocked(project,state)
def load(project,create=False,name=None,mode='full'):
 f=path_for(project)
 if not f.exists():
  if not create:raise ReviewError('项目未初始化')
  with project_lock(project):
   if not f.exists():write_unlocked(project,new_state(name or Path(project).name,mode))
 try:s=json.loads(f.read_text(encoding='utf-8'))
 except (ValueError,OSError) as exc:raise ReviewError('状态文件损坏；请从 .review-history 恢复快照') from exc
 if s.get('schema')!=SCHEMA:raise ReviewError('旧状态需要显式迁移：review_engine.py migrate --project ...；旧批准将保留历史并重新核验')
 _,_,checks=definitions()
 if set(s.get('checks',{}))!=set(checks) or s.get('definitions_sha256')!=digest(DEFINITIONS):raise ReviewError('审核定义已变更，请显式迁移后重新核验')
 s['_loaded_seq']=s['seq'];return s
def evidence_files(project,paths):
 if not isinstance(paths,list) or not paths:raise ReviewError('请提供至少一个项目内的真实证据文件 evidence_files')
 root=Path(project).resolve();out={}
 for name in paths:
  if not isinstance(name,str):raise ReviewError('证据路径必须为字符串')
  p=(root/name).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ReviewError('证据不存在或不在项目内：'+name)
  out[p.relative_to(root).as_posix()]=digest(p)
 return out
def fresh_files(project,records):
 root=Path(project).resolve()
 if not isinstance(records,dict) or not records:return False
 return all((root/name).resolve().is_relative_to(root) and (root/name).is_file() and digest(root/name)==sha for name,sha in records.items())
def related(cid,checks):
 out=set();stack=list(checks[cid].get('affects',[]))
 while stack:
  c=stack.pop()
  if c not in out and c!=cid:out.add(c);stack.extend(checks[c].get('affects',[]))
 return sorted(out)
def invalidate(s,cid,checks):
 for target in related(cid,checks):
  if s['checks'][target]['status'] in ('approved','na'):
   s['checks'][target]['status']='stale';s['checks'][target]['reviewed_at']=None
 _,mods,_=definitions();ids=[m['id'] for m in mods];stage=checks[cid]['stage']
 for sid in ids[ids.index(stage):]:s['signoffs'].pop(sid,None)
def open_issues(s,cid=None):return [i for i in s['issues'] if i['status']=='open' and (cid is None or i['check_id']==cid)]
def applicable(s,cid):
 _,_,checks=definitions();mode=s.get('task_mode','full')
 return (MODES[mode] is None or checks[cid]['stage'] in MODES[mode]) and not(mode=='local-edit' and cid=='R5.fidelity')
def inspect_one(project,cid,definition):
 root=Path(project).resolve();art=root/'artifacts'
 names=[definition['auto_report']]+definition.get('auto_alternates',[])
 path=next((art/n for n in names if (art/n).is_file()),art/names[0])
 result={'status':'UNKNOWN','sha256':None,'path':None,'checked_at':now(),'message':'缺少检测报告'}
 if not path.is_file():return result
 if not path.resolve().is_relative_to(root):return dict(result,status='BLOCK',message='报告路径越界')
 result.update(sha256=digest(path),path=path.relative_to(root).as_posix())
 try:
  obj=verify_report(path,AUTO_TOOLS[cid],root)
  status=obj['status'];result['status']='PASS' if status in definition.get('pass_values',['PASS']) else ('BLOCK' if status in ('BLOCK','INCOMPLETE') else 'UNKNOWN')
  result['message']='报告状态：'+status
 except ValueError as exc:result.update(status='BLOCK',message=str(exc))
 return result
def refresh(s,project):
 _,_,checks=definitions();changed=[]
 baseline=s.get('baseline')
 if baseline and not fresh_files(project,baseline['files']):
  if not baseline.get('stale'):
   baseline['stale']=True;s['signoffs'].clear()
   for c in s['checks'].values():
    if c['status'] in ('approved','na'):c['status']='stale'
   changed.append('baseline')
 revision=s.get('active_revision')
 if revision and not fresh_files(project,revision['files']):
  if not revision.get('stale'):
   revision['stale']=True
   s['checks']['R4.target']['status']='stale';invalidate(s,'R4.target',checks)
   changed.append('active_revision')
 for issue in s['issues']:
  if issue['status']=='resolved' and not fresh_files(project,issue.get('resolution_files',{})):
   issue['previous_resolution']={'fixed_revision':issue.get('fixed_revision'),'resolution':issue.get('resolution'),'files':issue.get('resolution_files',{})}
   issue['status']='open';issue['reopened_at']=now()
   cid=issue['check_id'];s['checks'][cid]['status']='rejected';invalidate(s,cid,checks);changed.append(issue['id'])
 for cid,rec in s['checks'].items():
  if rec['status'] not in ('approved','na'):continue
  reason=None
  if rec['status']=='approved' and not fresh_files(project,rec.get('files',{})):reason='人工证据文件已改变或丢失'
  if checks[cid].get('auto_report') and rec['status']=='approved':
   actual=inspect_one(project,cid,checks[cid]);previous=rec.get('auto')
   if actual['status']!='PASS' or not previous or actual['sha256']!=previous['sha256']:reason=actual['message']
   rec['auto']=actual
  if reason:
   rec['status']='stale';rec['note']=reason;rec['reviewed_at']=None;invalidate(s,cid,checks);changed.append(cid)
 if changed:event(s,'evidence_invalidated',{'checks':changed})
 return changed
def inspect_automated(s,project):
 refresh(s,project);_,_,checks=definitions();rows=[]
 for cid,d in checks.items():
  if d.get('auto_report'):
   rec=s['checks'][cid];actual=inspect_one(project,cid,d)
   old=rec.get('auto')
   if rec['status']=='approved' and (actual['status']!='PASS' or not old or old['sha256']!=actual['sha256']):
    rec['status']='stale';invalidate(s,cid,checks)
   rec['auto']=actual;rows.append({'check_id':cid,**actual})
 event(s,'auto_inspect',{'checks':len(rows)});return rows
def require_auto(s,project,cid,d):
 if not d.get('auto_report'):return
 old=s['checks'][cid].get('auto');actual=inspect_one(project,cid,d)
 if not old or actual['status']!='PASS' or old.get('sha256')!=actual['sha256']:raise ReviewError('自动证据无效，请重新运行检测并读取报告：'+actual['message'])
 current=s.get('active_revision')
 if current and cid in ('R4.lock','R5.geometry','R6.color','R6.layers'):
  obj=verify_report(Path(project)/actual['path'],AUTO_TOOLS[cid],project)
  file_shas=set(current['files'].values())
  roles=obj['outputs'] if cid=='R4.lock' else obj['inputs']
  key='locked' if cid=='R4.lock' else 'approved' if cid=='R6.layers' else 'image'
  if roles.get(key,{}).get('sha256') not in file_shas:raise ReviewError('检测报告不对应当前登记的成品版本')
  if cid=='R6.layers' and obj.get('approved_composite_match') is not True:raise ReviewError('图层包尚未与批准母版比较；请 export_layers.py --approved <当前成品>')
def require_revision(s):
 r=s.get('active_revision')
 if not r or r.get('stale'):raise ReviewError('请先登记当前成品版本 revision 和实际文件；版本失效时需登记新版本')
 return r
def apply(s,project,action,data):
 _,mods,checks=definitions();refresh(s,project)
 cid=data.get('check_id');stage=data.get('stage')
 if action=='inspect':return {'reports':inspect_automated(s,project)}
 if action=='revision':
  name=str(data.get('revision','')).strip()
  if len(name)<2:raise ReviewError('请填写版本号')
  files=evidence_files(project,data.get('evidence_files'))
  if not any(Path(p).suffix.lower() in ('.png','.jpg','.jpeg','.webp','.tif','.tiff') for p in files):raise ReviewError('版本登记须包含实际成品图片')
  # A revision label is immutable across the full recorded history, not only the active image.
  for entry in s.get('history',[]):
   if entry.get('event')=='revision_registered':
    previous=entry.get('details',{})
    if previous.get('revision')==name and previous.get('files')!=files:
     raise ReviewError('历史版本号已绑定其他文件或内容；请使用新版本号')
  old=s.get('active_revision')
  if old and old['id']==name and old['files']!=files:raise ReviewError('同一版本号不可换图；请使用新版本号')
  if old and (old['id']!=name or old['files']!=files):
   s['checks']['R4.target']['status']='stale';invalidate(s,'R4.target',checks)
  s['active_revision']={'id':name,'files':files,'at':now(),'stale':False}
  event(s,'revision_registered',{'revision':name,'files':files});return {'revision':name}
 if action=='baseline':
  if s.get('task_mode')!='local-edit':raise ReviewError('baseline import only applies to local-edit mode')
  files=evidence_files(project,data.get('evidence_files'))
  reason=str(data.get('evidence','')).strip()
  if len(reason)<5:raise ReviewError('请记录已确认基准的批准依据')
  if not any(Path(p).suffix.lower() in ('.png','.jpg','.jpeg','.webp') for p in files):raise ReviewError('基准记录须包含图片')
  if not any(Path(p).suffix.lower() in ('.md','.txt','.json','.pdf') for p in files):raise ReviewError('基准记录须包含批准依据文件')
  s['baseline']={'files':files,'evidence':reason,'at':now(),'stale':False};s['signoffs'].clear()
  for c in s['checks'].values():
   if c['status'] in ('approved','na'):c['status']='stale'
  event(s,'baseline_imported',{'files':files});return {'baseline':'recorded; not an authenticated signature'}
 if action in ('approve','reject','unknown','na','reopen'):
  if cid not in checks or not applicable(s,cid):raise ReviewError('检查项不存在或不适用于当前任务模式')
  rec=s['checks'][cid];prior=rec['status']
  if action=='approve':
   if open_issues(s,cid):raise ReviewError('先提交真实修复证据并解决问题，再复核')
   text=str(data.get('evidence','')).strip()
   if len(text)<4:raise ReviewError('请填写具体验收说明')
   files=evidence_files(project,data.get('evidence_files'))
   if checks[cid]['stage'] in ('R4','R5','R6'):
    rev=require_revision(s)
    if not set(files.values())&set(rev['files'].values()):raise ReviewError('验收文件必须包含当前登记的成品图片')
   require_auto(s,project,cid,checks[cid])
   if prior=='approved' and rec['evidence']==text and rec['files']==files:return {'check':cid,'status':'approved','unchanged':True}
   rec.update(status='approved',evidence=text,files=files,note='',reviewer=str(data.get('reviewer','local reviewer (declared)')))
  elif action=='reject':
   text=str(data.get('issue','')).strip();sev=data.get('severity','P1')
   if len(text)<5 or sev not in ('P0','P1','P2'):raise ReviewError('请填写具体问题和有效等级')
   s['issues'].append({'id':'ISS-'+str(s['seq']+1).zfill(4),'check_id':cid,'severity':sev,'text':text,'status':'open','created_at':now(),
                        'baseline_files':dict(rec.get('files',{})),'baseline_revision':(s.get('active_revision') or {}).get('id'),'resolution':None,'fixed_revision':None})
   rec.update(status='rejected',note=text)
  elif action in ('unknown','na'):
   text=str(data.get('issue','')).strip()
   if len(text)<4:raise ReviewError('请填写具体原因')
   if action=='na' and not checks[cid].get('allow_na'):raise ReviewError('此项不支持不适用')
   rec.update(status=action,note=text)
  else:rec.update(status='pending',note='重新核验')
  rec['revision']+=1;rec['reviewed_at']=now()
  invalidate(s,cid,checks);event(s,'check_'+action,{'check_id':cid,'before':prior,'after':rec['status'],'files':rec.get('files',{})})
  return {'check':cid,'status':rec['status'],'affected_checks':related(cid,checks)}
 if action=='resolve':
  issue=next((i for i in s['issues'] if i['id']==data.get('issue_id') and i['status']=='open'),None)
  if not issue:raise ReviewError('未找到待解决问题')
  version=str(data.get('fixed_revision','')).strip();text=str(data.get('resolution','')).strip()
  if len(version)<2 or len(text)<5:raise ReviewError('必须提供新版本号与实际修复说明')
  files=evidence_files(project,data.get('evidence_files'))
  if checks[issue['check_id']]['stage'] in ('R4','R5','R6'):
   rev=require_revision(s)
   if version!=rev['id'] or version==issue.get('baseline_revision') or not set(files.values())&set(rev['files'].values()):
    raise ReviewError('成品问题须登记新的成品版本，并将该版本的图片作为修复证据')
  if issue.get('baseline_files') and set(files.values()).issubset(set(issue['baseline_files'].values())):raise ReviewError('修复证据未变化，不能把旧版当作已修复')
  issue.update(status='resolved',fixed_revision=version,resolution=text,resolution_files=files,resolved_at=now())
  if not open_issues(s,issue['check_id']):s['checks'][issue['check_id']]['status']='pending'
  event(s,'issue_resolved',{'issue_id':issue['id'],'fixed_revision':version,'files':files});return {'issue_id':issue['id'],'check_status':'pending'}
 if action=='signoff':
  ids=[m['id'] for m in mods if any(applicable(s,c['id']) for c in m['checks'])]
  if stage not in ids:raise ReviewError('该模块不适用于当前模式')
  if s['task_mode']=='local-edit' and (not s.get('baseline') or s['baseline'].get('stale')):raise ReviewError('局部修改须先导入实际基准及批准依据；不会伪造前序签核')
  previous=ids[:ids.index(stage)]
  if any(p not in s['signoffs'] for p in previous):raise ReviewError('前序适用模块尚未有效签核')
  for sid in previous+[stage]:
   for c in next(m for m in mods if m['id']==sid)['checks']:
    if not applicable(s,c['id']):continue
    rec=s['checks'][c['id']]
    if rec['status'] not in ('approved','na') or open_issues(s,c['id']):raise ReviewError('检查项未通过：'+c['id'])
    if rec['status']=='approved':
     if not fresh_files(project,rec['files']):raise ReviewError('证据已失效：'+c['id'])
     require_auto(s,project,c['id'],checks[c['id']])
  active=[c['id'] for c in next(m for m in mods if m['id']==stage)['checks'] if applicable(s,c['id'])]
  s['signoffs'][stage]={'at':now(),'check_revisions':{c:s['checks'][c]['revision'] for c in active},'reviewer':str(data.get('reviewer','local reviewer (declared)'))}
  event(s,'module_signoff',{'stage':stage});return {'stage':stage,'status':'PASS'}
 if action=='revoke_signoff':
  ids=[m['id'] for m in mods]
  if stage not in ids:raise ReviewError('unknown stage')
  for sid in ids[ids.index(stage):]:s['signoffs'].pop(sid,None)
  event(s,'revoke_signoff',{'stage':stage});return {'stage':stage,'status':'reopened'}
 raise ReviewError('unknown action')

def module_statuses(s):
 _,mods,_=definitions();out=[]
 for m in mods:
  ids=[c['id'] for c in m['checks'] if applicable(s,c['id'])];items=[s['checks'][c]['status'] for c in ids]
  if not ids:status='SKIPPED'
  elif 'rejected' in items or any(open_issues(s,c) for c in ids):status='BLOCK'
  elif any(i not in ('approved','na') for i in items):status='PENDING'
  elif m['id'] in s['signoffs']:status='PASS'
  else:status='READY'
  out.append({'id':m['id'],'name':m['name'],'status':status,'approved_checks':sum(i in ('approved','na') for i in items),'total_checks':len(ids),'open_issues':sum(len(open_issues(s,c)) for c in ids)})
 return out
def make_ticket(s,check_id=None,stage=None):
 _,mods,checks=definitions()
 ids=[check_id] if check_id else [c['id'] for m in mods if not stage or stage==m['id'] for c in m['checks'] if applicable(s,c['id']) and (s['checks'][c['id']]['status'] in ('rejected','stale','unknown') or open_issues(s,c['id']))]
 rows=['# 定向修复工单','',f'项目：{s["project_name"]}',f'创建时间：{now()}','', '仅处理以下范围；未列入的已确认内容保持原样。工单不自动调用图像生成。','']
 for cid in ids:
  if cid not in checks:continue
  d=checks[cid];rec=s['checks'][cid]
  rows+=['## '+cid+' · '+d['name'],'需要处理：'+('；'.join(i['text'] for i in open_issues(s,cid)) or rec.get('note') or '补齐实际证据并重新核验'),
         '验收要求：'+d['evidence'],'重新核验下游：'+(', '.join(related(cid,checks)) or '无'),'提交新版本号、真实修复文件和证据，再请求人工复核。','']
 return '\n'.join(rows)
def snapshot(project):
 with project_lock(project):
  s=load(project)
  if refresh(s,project):write_unlocked(project,s)
  return s
def transact(project,action,data,expected_seq=None):
 with project_lock(project):
  s=load(project)
  if expected_seq is not None and expected_seq!=s['seq']:raise ConflictError('页面版本已过期，请刷新；草稿已保留')
  before=s['seq']
  try:result=apply(s,project,action,data)
  except ReviewError:
   if s['seq']!=before:write_unlocked(project,s)
   raise
  write_unlocked(project,s);return result
def migrate(project):
 with project_lock(project):
  path=path_for(project);old=json.loads(path.read_text(encoding='utf-8'))
  backup=path.with_name('review_state.before-v2-migration.json')
  if backup.exists():raise ReviewError('迁移备份已存在，请检查后再执行')
  backup.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
  s=new_state(old.get('project_name',Path(project).name),old.get('task_mode','full'))
  s['history']=old.get('history',[]);s['seq']=old.get('seq',0);s['issues']=old.get('issues',[])
  s['_loaded_seq']=old.get('seq',0)
  for cid,rec in old.get('checks',{}).items():
   if cid in s['checks']:
    s['checks'][cid].update(rec)
    if rec.get('status') in ('approved','na'):s['checks'][cid]['status']='stale'
    s['checks'][cid]['auto']=None;s['checks'][cid]['files']={}
  event(s,'migration',{'backup':backup.name,'all_prior_signoffs':'cleared; evidence must be rebound'})
  write_unlocked(project,s)
 return {'migrated':True,'backup':str(backup)}
def review_brief(s,stage=None,check_id=None):
 _,mods,checks=definitions()
 if stage and stage not in {m['id'] for m in mods}:raise ReviewError('unknown stage')
 if check_id and check_id not in checks:raise ReviewError('unknown check')
 ids=[c for c in checks if applicable(s,c) and (not stage or checks[c]['stage']==stage) and (not check_id or c==check_id)]
 selected=set(ids)
 result={'mode':s['task_mode'],'seq':s['seq'],'modules':[m for m in module_statuses(s) if not stage or m['id']==stage],
         'active_revision':None,'issues':[],'attention':[]}
 r=s.get('active_revision')
 if r:result['active_revision']={'id':r['id'],'stale':r.get('stale',False)}
 for issue in s['issues']:
  if issue['status']=='open' and issue['check_id'] in selected:
   result['issues'].append({k:issue.get(k) for k in ('id','check_id','severity','text','status')})
 for cid in ids:
  rec=s['checks'][cid]
  if stage or check_id or rec['status'] in ('rejected','stale','unknown'):
   result['attention'].append({'id':cid,'status':rec['status'],'note':rec.get('note','')})
 return result

def cli():
 p=argparse.ArgumentParser()
 p.add_argument('command',choices=['init','status','inspect','approve','reject','unknown','na','reopen','resolve','signoff','revoke_signoff','ticket','export','revision','baseline','migrate'])
 p.add_argument('--project',required=True,type=Path);p.add_argument('--mode',choices=list(MODES),default='full')
 for name in ['name','check-id','stage','evidence','issue','issue-id','resolution','fixed-revision','revision','reviewer']:p.add_argument('--'+name)
 p.add_argument('--severity',default='P1');p.add_argument('--evidence-files',nargs='+');p.add_argument('--expected-seq',type=int);p.add_argument('--out',type=Path)
 p.add_argument('--full-output',action='store_true',help='Print full legacy status/state')
 a=p.parse_args()
 try:
  if a.command=='init':s=load(a.project,True,a.name,a.mode);result={'created':str(path_for(a.project)),'mode':s['task_mode']}
  elif a.command=='migrate':result=migrate(a.project)
  elif a.command in ('status','ticket','export'):
   s=snapshot(a.project)
   result=({'modules':module_statuses(s),'open_issues':open_issues(s)} if a.full_output else review_brief(s,a.stage,a.check_id)) if a.command=='status' else make_ticket(s,a.check_id,a.stage) if a.command=='ticket' else ({k:v for k,v in s.items() if not k.startswith('_')} if a.full_output or a.out else review_brief(s,a.stage,a.check_id))
  else:result=transact(a.project,a.command,vars(a),a.expected_seq)
  if a.command=='inspect' and not a.full_output:
   result={'reports':[{k:r.get(k) for k in ('check_id','status','path','message')} for r in result['reports']]}
  value=result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2 if a.full_output else None)
  if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(value,encoding='utf-8')
  else:print(value)
  return 0
 except (ReviewError,ConflictError,ValueError,OSError) as exc:print('BLOCK:',exc,file=sys.stderr);return 2
if __name__=='__main__':sys.exit(cli())
