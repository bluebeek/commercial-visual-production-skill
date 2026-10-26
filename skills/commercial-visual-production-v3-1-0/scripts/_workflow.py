"""V3 authoritative project state and integrity helpers. Local records are not authenticated signatures."""
import copy, hashlib, json, os, re, tempfile
from pathlib import Path
from datetime import datetime, timezone
from _storage import project_lock, ConflictError

SCHEMA = 'cvisual.workflow.v3'
STAGES = {'R0':'参考解析','R1':'品牌转译','R2':'创意与蓝图','R3':'视觉生产','R4':'结果核验','R5':'修复与冻结','R6':'交付验收'}
MODULES = ['视觉风格','设计排版','素材处理','色彩系统','字体与文字','光影与材质','空间关系','图形与装饰','视觉机制综合']
ROOT = Path(__file__).resolve().parents[1]
class WorkflowError(ValueError): pass

def now(): return datetime.now(timezone.utc).isoformat()
def dump(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',',':'))
def objhash(obj): return hashlib.sha256(dump(obj).encode()).hexdigest()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ident(v):
    if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',v): raise WorkflowError('invalid stable id')
    return v
def local(root, value, exists=True):
    if not isinstance(value,(str,Path)) or not str(value): raise WorkflowError('missing project path')
    root=Path(root).resolve(); p=(root/value).resolve()
    if not p.is_relative_to(root): raise WorkflowError('path outside project')
    if exists and not p.is_file(): raise WorkflowError('missing file: '+str(value))
    return p
def bind(root, paths):
    return {local(root,p).relative_to(Path(root).resolve()).as_posix():sha(local(root,p)) for p in paths}
def fresh(root, files):
    return isinstance(files,dict) and all(local(root,p,False).is_file() and sha(local(root,p))==h for p,h in files.items())
def atomic(p,obj):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.v3-',suffix='.json')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(dump(obj));f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def load(root):
    p=local(root,'workflow_state.json')
    s=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(s,dict) or s.get('schema')!=SCHEMA: raise WorkflowError('invalid V3 project state')
    return s
def create(root, project_id, test_mode=False, call_budget=4, editor_backend="photocraft"):
    if editor_backend not in ('photocraft',None) or (editor_backend is None and not test_mode):raise WorkflowError('new production projects require PhotoCraft')
    root=Path(root).resolve()
    with project_lock(root):
        if (root/'workflow_state.json').exists(): raise WorkflowError('project already exists')
        if not isinstance(call_budget,int) or call_budget<0: raise WorkflowError('invalid call budget')
        s={'schema':SCHEMA,'workflow_version':'3.1.0','editor_backend':editor_backend,'project_id':ident(project_id),'seq':0,'test_mode':bool(test_mode),
           'call_budget':call_budget,'calls_used':0,'stages':{},'requirements':{},'assets':{},'jobs':{},'revisions':{},'checks':{},'issues':{},
           'decisions':[],'history':[],'working_revision':None,'accepted_revision':None,'master':None,'deliveries':{},'migration':None}
        atomic(root/'workflow_state.json',s)
    return s
def transact(root, fn, expected_seq=None):
    root=Path(root).resolve()
    with project_lock(root):
        s=load(root)
        if expected_seq is not None and s['seq']!=expected_seq: raise ConflictError('页面状态已更新，请刷新后提交')
        before=copy.deepcopy(s); result=fn(s,root)
        s['seq']+=1;s['history'].append({'seq':s['seq'],'at':now(),'action':fn.__name__})
        hist=root/'.workflow-history'/('%08d.json'%before['seq'])
        if not hist.exists(): atomic(hist,before)
        atomic(root/'workflow_state.json',s)
        return result

def active(s): return [r for r in s['requirements'].values() if r['status']=='active']
def rules_hash(s): return objhash(sorted(active(s),key=lambda x:x['id']))
def stage_fresh(s,root,sid):
    st=s['stages'].get(sid)
    if not st or st.get('invalidated') or not fresh(root,st['files']): return False
    return all(s['stages'].get(dep,{}).get('id')==v and stage_fresh(s,root,dep) for dep,v in st['upstream'].items())
def decision(s,kind,subject):
    return next((d for d in reversed(s['decisions']) if d['kind']==kind and d['subject']==subject and not d.get('revoked')),None)
def user_evidence(s,root,data):
    actor=data.get('actor')
    if actor not in ('user','test'): raise WorkflowError('requires an actual user decision; use test only in test projects')
    if (actor=='test') != bool(s['test_mode']): raise WorkflowError('test decisions cannot become commercial approvals')
    if not isinstance(data.get('reason'),str) or len(data['reason'].strip())<3: raise WorkflowError('decision needs concrete reason/source')
    files=bind(root,data.get('evidence_files',[]))
    if not files: raise WorkflowError('decision evidence file required')
    return {'actor':actor,'reason':data['reason'],'files':files,'at':now(),'test_only':s['test_mode']}
def approved_blueprint(s,root):
    st=s['stages'].get('R2',{})
    d=decision(s,'blueprint',st.get('id'))
    return bool(stage_fresh(s,root,'R2') and d and fresh(root,d['files']))
def rev_fresh(s,root,rid, current_rules=True):
    r=s['revisions'].get(rid)
    if not r or not fresh(root,r['files']): return False
    if current_rules and r['rules_hash']!=rules_hash(s): return False
    return True

def context(s,root,stage='R3'):
    missing=[sid for sid in ('R0','R1','R2') if sid not in s['stages']]
    stale=[sid for sid in ('R0','R1','R2') if sid in s['stages'] and not stage_fresh(s,root,sid)]
    stale_assets=[a['id'] for a in s['assets'].values() if not fresh(root,a['files'])]
    unknown=[r['id'] for r in s['requirements'].values() if r['status']=='unknown' and r.get('critical',True)]
    rules=active(s)
    stale_rules=[r['id'] for r in rules if not fresh(root,r['files']) or (r['source']['kind']=='translation' and not any(x['observation_id']==r['source'].get('observation_id') and x['decision'] in ('adopt','adapt') for x in s['stages'].get('R1',{}).get('data',{}).get('decisions',[])))]
    test_sources=[] if s['test_mode'] else (
        ['asset:'+aid for aid,a in s['assets'].items() if a.get('description_source')=='test']+
        ['requirement:'+r['id'] for r in s['requirements'].values() if r['status'] in ('active','unknown') and r['source']['kind']=='test'])
    out={'schema':SCHEMA,'project_id':s['project_id'],'project_root':str(Path(root).resolve()),'target':stage,
         'status':'BLOCK' if missing or stale or stale_assets or stale_rules or unknown or test_sources else 'READY',
         'missing_stages':missing,'stale_stages':stale,'stale_assets':stale_assets,'stale_requirements':stale_rules,'unknown_requirements':unknown,'test_sources':test_sources,
         'requirements':rules,'blueprint_accepted':approved_blueprint(s,root),
         'stages':{k:{'id':v['id'],'data':v['data'],'files':v['files']} for k,v in s['stages'].items() if k in (['R0'] if stage=='R0' else ['R0','R1'] if stage=='R1' else ['R1','R2'])},
         'working_revision':s['working_revision'],'accepted_revision':s['accepted_revision'],
         'issues':[i for i in s['issues'].values() if i['status'] not in ('verified_closed','accepted_exception')],
         'calls':{'used':s['calls_used'],'budget':s['call_budget']},'test_only':s['test_mode']}
    if s['working_revision']:
        r=s['revisions'][s['working_revision']]
        out['baseline']={k:r[k] for k in ('id','parent','image','change_request','requirements')}
        out['baseline']['fresh']=rev_fresh(s,root,r['id'],False)
    return out
