"""New R0-R6 workflow: explicit source decisions, bounded changes and real review evidence."""
import argparse, copy, json, sys
from pathlib import Path
from PIL import Image
from _workflow import *
from _common import load_project, validate_project


def put_stage(s,root,d):
    sid=d.get('stage'); data=d.get('data')
    if sid not in ('R0','R1','R2') or not isinstance(data,dict): raise WorkflowError('only R0/R1/R2 accept source stages; R3-R6 are derived from actual work')
    upstream={} if sid=='R0' else {('R0' if sid=='R1' else 'R1'):s['stages'].get('R0' if sid=='R1' else 'R1',{}).get('id')}
    for dep in upstream:
        if not stage_fresh(s,root,dep): raise WorkflowError('upstream is missing/stale: '+dep)
    paths=list(d.get('evidence_files',[]))
    if sid=='R0':
        if set(data)-{'observations','references'}: raise WorkflowError('R0 accepts reference facts only, no project blueprint')
        obs=data.get('observations',[])
        if {o.get('module') for o in obs}!=set(range(1,10)): raise WorkflowError('R0 requires all nine modules')
        if len({ident(o.get('id')) for o in obs})!=len(obs): raise WorkflowError('duplicate observation id')
        for o in obs:
            if o.get('certainty') not in ('observed','estimated','unknown') or not o.get('text'): raise WorkflowError('observation needs certainty and text')
            if o['certainty']!='unknown': paths.append(o['evidence_file'])
        refs=data.get('references',[])
        if not refs:raise WorkflowError('R0 needs actual reference images')
        for r in refs:
            if not r.get('role'):raise WorkflowError('reference image role required')
            with Image.open(local(root,r['path'])) as im:im.verify()
            paths.append(r['path'])
        if any(o.get('certainty')!='unknown' and o.get('evidence_file') not in [r['path'] for r in refs] for o in obs):raise WorkflowError('observations must point to registered reference images')
    elif sid=='R1':
        if set(data)-{'purpose','decisions','asset_roles','notes'}: raise WorkflowError('R1 cannot contain a layout blueprint')
        if not data.get('purpose'): raise WorkflowError('R1 purpose is required')
        obs={o['id'] for o in s['stages']['R0']['data']['observations']}
        ds=data.get('decisions',[])
        if {x.get('observation_id') for x in ds}!=obs or len(ds)!=len(obs): raise WorkflowError('every observation needs exactly one adopt/adapt/reject decision')
        if any(x.get('decision') not in ('adopt','adapt','reject') or not x.get('reason') for x in ds): raise WorkflowError('translation needs a reason')
        for a in data.get('asset_roles',[]):
            if a not in s['assets']: raise WorkflowError('unregistered asset role: '+a)
    else:
        if set(data)-{'creative_input','spec','preview','planned_assets','notes'}: raise WorkflowError('unknown R2 field; visual rules belong in requirements')
        c=data.get('creative_input',{}); kind=c.get('kind')
        if kind not in ('text','sketch','mixed'): raise WorkflowError('creative input must be text/sketch/mixed')
        if kind in ('text','mixed') and not c.get('text'): raise WorkflowError('missing user creative text')
        if kind in ('sketch','mixed'): paths.append(c['path'])
        spec=local(root,data['spec']); p,base=load_project(spec); pre,_=validate_project(p,base,'draft')
        if pre['status']=='BLOCK': raise WorkflowError('; '.join(pre['errors']))
        # R2 may reserve assets which will be generated; protected originals cannot be invented.
        planned=set(data.get('planned_assets',[]))
        for e in p['elements']:
            if e.get('source'): paths.append((base/e['source']).relative_to(root).as_posix())
            elif e.get('required',True) and e.get('role') not in ('background','negative_space','group') and (e.get('lock') in ('L0','L1') or e['id'] not in planned):
                raise WorkflowError('missing real/planned asset: '+e['id'])
        paths += [data['spec'],data['preview']]
        with Image.open(local(root,data['preview'])) as im:
            if im.size!=(p['canvas']['width'],p['canvas']['height']): raise WorkflowError('preview dimensions differ from blueprint')
    files=bind(root,paths)
    if not files: raise WorkflowError('stage needs real evidence')
    record={'stage':sid,'data':data,'files':files,'upstream':upstream}
    record['id']=sid+'-'+objhash(record)[:16]
    s['stages'][sid]=record
    return {'stage':sid,'version':record['id'],'approval':'not_a_decision'}


def asset(s,root,d):
    aid=ident(d.get('id'))
    if aid in s['assets']: raise WorkflowError('asset ids are immutable; register a new version')
    for key in ('path','role','description','description_source'):
        if not isinstance(d.get(key),str) or not d[key].strip(): raise WorkflowError('asset needs '+key)
    if d['description_source'] not in ('user','observed','test'): raise WorkflowError('invalid description source')
    if d['description_source']=='test' and not s['test_mode']: raise WorkflowError('test asset descriptions require a test project')
    rec={k:d.get(k,[]) for k in ('must_keep','allowed_changes')}
    rec.update({k:d[k] for k in ('id','path','role','description','description_source')});rec['files']=bind(root,[d['path']])
    s['assets'][aid]=rec
    return rec


def requirement(s,root,d):
    rid=ident(d.get('id'))
    if rid in s['requirements']: raise WorkflowError('requirement id already exists; use a new id and supersedes')
    for key in ('scope','property','text','verification'):
        if not isinstance(d.get(key),str) or not d[key].strip(): raise WorkflowError('requirement needs '+key)
    source=d.get('source',{})
    if source.get('kind') not in ('user','brand','translation','test') or not source.get('quote'): raise WorkflowError('requirement must retain actual source wording')
    if source['kind']=='test' and not s['test_mode']: raise WorkflowError('test requirements require a test project')
    files=bind(root,d.get('evidence_files',[]))
    if not files: raise WorkflowError('requirement needs source evidence')
    if source.get('kind')=='translation':
        oid=source.get('observation_id')
        found=next((x for x in s['stages'].get('R1',{}).get('data',{}).get('decisions',[]) if x['observation_id']==oid),None)
        if not found or found['decision']=='reject': raise WorkflowError('reference was not adopted/adapted in R1')
        observed=next((o for o in s['stages'].get('R0',{}).get('data',{}).get('observations',[]) if o['id']==oid),None)
        if observed and observed['certainty']=='unknown' and d.get('status','active')=='active':raise WorkflowError('unknown reference observation cannot become an active requirement without new actual evidence')
    status=d.get('status','active')
    if status not in ('active','rejected','unknown'): raise WorkflowError('invalid requirement status')
    method=d.get('method','prompt')
    if method not in ('prompt','composite','both'): raise WorkflowError('method must be prompt/composite/both')
    replaces=d.get('supersedes',[])
    if not isinstance(replaces,list): raise WorkflowError('supersedes must be a list')
    for oldid in replaces:
        old=s['requirements'].get(oldid)
        if not old or old['status']!='active' or (old['scope'],old['property'])!=(d['scope'],d['property']): raise WorkflowError('replacement must target active rules of the same scope/property')
        if old['source']['kind']=='brand' and source['kind'] not in ('brand','test'):
            raise WorkflowError('specific external brand conflict needs updated brand evidence')
    collisions=[x['id'] for x in active(s) if (x['scope'],x['property'])==(d['scope'],d['property']) and x['id'] not in replaces]
    if status=='active' and collisions: raise WorkflowError('unresolved competing requirement: '+','.join(collisions))
    for oldid in replaces:s['requirements'][oldid]['status']='superseded'
    rec={k:d[k] for k in ('id','scope','property','text','verification')}
    rec.update(source=source,files=files,status=status,method=method,supersedes=replaces,critical=d.get('critical',True),impact_stage=d.get('impact_stage','R3'))
    if rec['impact_stage'] not in ('R1','R2','R3'): raise WorkflowError('invalid impact stage')
    s['requirements'][rid]=rec
    if rec['impact_stage'] in ('R1','R2'):
        for sid in ('R1','R2') if rec['impact_stage']=='R1' else ('R2',):
            if sid in s['stages']:s['stages'][sid]['invalidated']=True
    affected=[r['id'] for r in s['revisions'].values() if any(x['scope'] in (d['scope'],'project','canvas') for x in r['requirements']) or d['scope'] in ('project','canvas')]
    return {'requirement':rec,'recheck_revisions':affected,'replaced':replaces}


def confirm_blueprint(s,root,d):
    if not stage_fresh(s,root,'R2') or context(s,root)['status']!='READY': raise WorkflowError('blueprint or critical planning evidence missing/stale/unknown')
    rec=user_evidence(s,root,d);rec.update(kind='blueprint',subject=s['stages']['R2']['id'])
    rec['files'].update(s['stages']['R2']['files']);s['decisions'].append(rec)
    return rec


def revision(s,root,d):
    rid=ident(d.get('id'))
    if rid in s['revisions']: raise WorkflowError('revision id is immutable')
    job=s['jobs'].get(d.get('job_id'))
    if not job or job['status'] not in ('generated','source_ready','materialized'): raise WorkflowError('revision needs an actually completed generation job')
    from production import validate_job
    validate_job(s,root,job,check_budget=False)
    if not fresh(root,job['output_files']): raise WorkflowError('generated output changed')
    material_path=local(root,d['materialization']); material=json.loads(material_path.read_text(encoding='utf-8'))
    if material.get('schema')!='cvisual.materialization.v3' or material.get('job_id')!=job['id'] or not fresh(root,material.get('input_files',{})) or not fresh(root,material.get('output_files',{})):raise WorkflowError('materialization provenance missing/stale')
    if material.get('implementation')!={'materialize.py':sha(Path(__file__).with_name('materialize.py')),'locked_edit.py':sha(Path(__file__).with_name('locked_edit.py'))}:raise WorkflowError('materialization implementation changed')
    if any(d.get(k)!=material.get(k) for k in ('image','spec','parent','layer_updates')):raise WorkflowError('candidate differs from actual materialization record')
    parent=job.get('baseline')
    if d.get('parent')!=parent: raise WorkflowError('revision parent must equal job baseline')
    image=local(root,d['image']);spec=local(root,d['spec']);p,base=load_project(spec)
    pre,_=validate_project(p,base,'production')
    if pre['status']!='PASS': raise WorkflowError('candidate source layers incomplete')
    if p['canvas']!=job['blueprint']['canvas']: raise WorkflowError('candidate canvas differs from production plan')
    with Image.open(image) as im:
        if im.size!=(p['canvas']['width'],p['canvas']['height']): raise WorkflowError('candidate dimensions mismatch')
    files=bind(root,[d['image'],d['spec'],d['materialization']]+[(base/e['source']).relative_to(root).as_posix() for e in p['elements'] if e.get('source')])
    rec={'id':rid,'parent':parent,'image':d['image'],'spec':d['spec'],'job_id':job['id'],'files':files,'at':now(),
         'requirements':copy.deepcopy(job['requirements']),'rules_hash':job['rules_hash'],'blueprint_id':job['blueprint_id'],
         'change_request':job['change_request'],'editable_regions':job['editable_regions'],'layer_updates':d.get('layer_updates',[]),'status':'candidate'}
    if parent and not rec['layer_updates']:raise WorkflowError('repair must identify updated source/patch layers')
    s['revisions'][rid]=rec;s['working_revision']=rid;s['checks'][rid]={}
    if job.get('execution_kind') in ('native_composition','native_source'):job['status']='materialized';job['materialized_revision']=rid
    return {'revision':rid,'parent':parent,'acceptance':'pending'}


def review(s,root,d):
    rid=d.get('revision');r=s['revisions'].get(rid)
    if not rev_fresh(s,root,rid): raise WorkflowError('revision/effective requirements stale')
    cid=d.get('check_id');allowed={'target','history','seams','design'}|{'req:'+x['id'] for x in active(s)}
    if cid not in allowed: raise WorkflowError('manual review cannot replace file/layer/pixel checks')
    if d.get('actor') not in ('agent','user','test') or (d.get('actor')=='test' and not s['test_mode']): raise WorkflowError('invalid reviewer')
    status=d.get('status')
    if status not in ('PASS','FAIL','UNKNOWN'): raise WorkflowError('invalid check status')
    if not isinstance(d.get('observation'),str) or len(d['observation'].strip())<5:raise WorkflowError('actual image observation required')
    files=bind(root,d.get('evidence_files',[]))
    if r['files'][r['image']] not in files.values():raise WorkflowError('review must include the actual current image')
    s['checks'][rid][cid]={'status':status,'actor':d['actor'],'observation':d['observation'],'files':files,'rules_hash':rules_hash(s),'at':now()}
    return s['checks'][rid][cid]


def required_checks(s,r):
    extra=[]
    if any(x['verification']=='geometry' for x in active(s)):extra.append('geometry')
    job=s['jobs'].get(r.get('job_id'),{})
    if job.get('blueprint',{}).get('color_checks'):extra.append('color')
    return extra+ ['files','layers','design','target','history','seams']+(['non_target'] if r['parent'] else [])+['req:'+x['id'] for x in active(s)]
def qc(s,root,rid):
    r=s['revisions'].get(rid)
    if not r:return {'status':'BLOCK','missing':['revision']}
    missing=[]
    if context(s,root)['status']!='READY' or not rev_fresh(s,root,rid) or r['blueprint_id']!=s['stages'].get('R2',{}).get('id') or not approved_blueprint(s,root):missing.append('current inputs/blueprint')
    from checks import implementation
    exceptions={i['check_id'] for i in s['issues'].values() if i['status']=='accepted_exception' and i.get('exception_revision')==rid and fresh(root,i.get('exception_files',{}))}
    for cid in required_checks(s,r):
        c=s['checks'].get(rid,{}).get(cid,{})
        if (c.get('status')!='PASS' and not (cid in exceptions and c.get('status')=='FAIL')) or c.get('rules_hash')!=rules_hash(s) or not fresh(root,c.get('files',{})):missing.append(cid)
        elif c.get('actor')=='machine' and c.get('implementation')!=implementation(cid):missing.append(cid+':implementation changed')
    for issue in s['issues'].values():
        if issue['status']=='superseded' and issue.get('replacement_requirement') in {x['id'] for x in active(s)} and fresh(root,issue.get('replacement_files',{})):continue
        if issue['status']=='accepted_exception' and issue.get('exception_revision')==rid and fresh(root,issue.get('exception_files',{})):continue
        if issue['status']=='verified_closed' and issue.get('verified_revision')==rid and fresh(root,issue.get('verified_files',{})):continue
        # Unrelated branches remain historical. Descendants must retain closure/recheck it.
        chain=set();cur=rid
        while cur:chain.add(cur);cur=s['revisions'][cur]['parent']
        if issue['revision'] in chain:missing.append('issue:'+issue['id'])
    return {'status':'PASS' if not missing else 'BLOCK','missing':missing}


def issue(s,root,d):
    iid=ident(d.get('id'));rid=d.get('revision')
    if iid in s['issues'] or rid not in s['revisions']:raise WorkflowError('invalid issue id/revision')
    for key in ('expected','actual','scope','check_id'):
        if not d.get(key):raise WorkflowError('issue needs '+key)
    if d.get('severity') not in ('P0','P1','P2'):raise WorkflowError('invalid severity')
    allowed=set(required_checks(s,s['revisions'][rid]))
    if d['check_id'] not in allowed:raise WorkflowError('issue check does not exist')
    rec={k:d[k] for k in ('id','revision','expected','actual','scope','check_id','severity')}
    rec.update(status='open',files=bind(root,[s['revisions'][rid]['image']]),attempts=[])
    s['issues'][iid]=rec;return rec


def repair(s,root,d):
    i=s['issues'][d['issue_id']];job=s['jobs'][d['job_id']]
    if i['status'] not in ('open','reopened','fixing') or job.get('baseline')!=d.get('baseline') or job.get('baseline') not in s['revisions']:raise WorkflowError('repair needs a valid baseline/job')
    chain=set();cur=job['baseline']
    while cur:chain.add(cur);cur=s['revisions'][cur]['parent']
    if i['revision'] not in chain:raise WorkflowError('repair baseline is unrelated to issue')
    i.update(status='fixing',repair_job=job['id']);i['attempts'].append({'job_id':job['id'],'at':now()});return i

def submit_repair(s,root,d):
    i=s['issues'][d['issue_id']];r=s['revisions'][d['revision']]
    if i['status']!='fixing' or r['job_id']!=i['repair_job'] or r['id']==i['revision']:raise WorkflowError('submit a new actual repair revision')
    i.update(status='ready_for_review',fixed_revision=r['id']);return i

def close_issue(s,root,d):
    i=s['issues'][d['issue_id']];rid=d['revision'];r=s['revisions'][rid]
    if i['status'] not in ('ready_for_review','verified_closed') or (i['status']=='ready_for_review' and i.get('fixed_revision')!=rid):raise WorkflowError('repair not ready for this revision')
    ids={i['check_id'],'target','history','seams'}|({'non_target'} if r['parent'] else set())
    for cid in ids:
        c=s['checks'][rid].get(cid,{})
        if c.get('status')!='PASS' or c.get('rules_hash')!=rules_hash(s) or not fresh(root,c.get('files',{})):raise WorkflowError('repair review missing/stale: '+cid)
    i.update(status='verified_closed',verified_revision=rid,verified_files=copy.deepcopy(r['files']));return i

def accept_exception(s,root,d):
    i=s['issues'][d['issue_id']];rid=d['revision']
    if i['severity']!='P2' or i['check_id'] in ('files','layers','non_target') or i['check_id'].startswith('req:') and s['requirements'][i['check_id'][4:]].get('critical',True):raise WorkflowError('only noncritical P2 issues can be accepted')
    rec=user_evidence(s,root,d);rec['files'].update(s['revisions'][rid]['files'])
    i.update(status='accepted_exception',exception_revision=rid,exception_files=rec['files'],exception=rec)
    return i

def accept(s,root,d):
    rid=d['revision'];q=qc(s,root,rid)
    if q['status']!='PASS':raise WorkflowError('QC incomplete: '+','.join(q['missing']))
    rec=user_evidence(s,root,d);rec.update(kind='candidate',subject=rid);rec['files'].update(s['revisions'][rid]['files'])
    s['decisions'].append(rec);s['accepted_revision']=rid;s['working_revision']=rid;return rec

def freeze(s,root,d):
    rid=d['revision'];dec=decision(s,'candidate',rid)
    if s['accepted_revision']!=rid or not dec or not fresh(root,dec['files']) or qc(s,root,rid)['status']!='PASS':raise WorkflowError('freeze needs accepted, fully verified current candidate')
    s['master']={'revision':rid,'files':{**s['revisions'][rid]['files'],**dec['files']},'rules_hash':rules_hash(s),'at':now()};return s['master']

def select_revision(s,root,d):
    rid=d['revision']
    if not rev_fresh(s,root,rid,False):raise WorkflowError('historical image files changed/missing')
    if d.get('restore_requirements',True):
        chosen=s['revisions'][rid]['requirements'];ids={r['id'] for r in chosen}
        for r in active(s):
            if r['id'] not in ids:r['status']='superseded'
        for r in chosen:s['requirements'][r['id']]=copy.deepcopy(r)
    s['working_revision']=rid
    return {'working_revision':rid,'accepted_revision':s['accepted_revision'],'approval':'unchanged'}

def revoke(s,root,d):
    found=False
    for dec in s['decisions']:
        if dec['kind']==d['kind'] and dec['subject']==d['subject']:dec['revoked']=True;found=True
    if not found:raise WorkflowError('decision not found')
    if d['kind']=='candidate' and s['accepted_revision']==d['subject']:s['accepted_revision']=None;s['master']=None
    return {'revoked':d['subject']}


def supersede_issue(s,root,d):
    i=s['issues'][d['issue_id']];new=s['requirements'].get(d.get('replacement_requirement'))
    oldid=i['check_id'][4:] if i['check_id'].startswith('req:') else None
    if not oldid or not new or new['status']!='active' or oldid not in new['supersedes'] or s['requirements'][oldid]['status']!='superseded':raise WorkflowError('issue must belong to a requirement explicitly replaced in the same scope')
    if new['source']['kind']=='test' and not s['test_mode']:raise WorkflowError('test source cannot retire commercial issue')
    if not fresh(root,new['files']):raise WorkflowError('replacement source stale')
    i.update(status='superseded',replacement_requirement=new['id'],replacement_files=dict(new['files']),reason='previous requirement explicitly replaced; this is not a repair claim',at=now())
    return i

ACTIONS={'supersede-issue':supersede_issue,'stage':put_stage,'asset':asset,'requirement':requirement,'confirm-blueprint':confirm_blueprint,'revision':revision,'review':review,
         'issue':issue,'repair':repair,'submit-repair':submit_repair,'close-issue':close_issue,'accept-exception':accept_exception,'accept':accept,'freeze':freeze,'select':select_revision,'revoke':revoke}
def perform(root,action,data,expected_seq=None):
    if action not in ACTIONS:raise WorkflowError('unsupported action')
    def operation(s,r):return ACTIONS[action](s,r,data)
    operation.__name__=action
    return transact(root,operation,expected_seq)

def summary(root):
    s=load(root);out=context(s,root)
    out.update(seq=s['seq'],stage_names=STAGES,jobs=[{k:j.get(k) for k in ('id','kind','status','baseline','change_request')} for j in s['jobs'].values()],
               revisions=[{k:r.get(k) for k in ('id','parent','image','spec','change_request')} for r in s['revisions'].values()],master=s['master'],deliveries=s['deliveries'])
    if s['working_revision']:out['qc']=qc(s,root,s['working_revision'])
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['init','status','export']+list(ACTIONS));ap.add_argument('--project',required=True,type=Path);ap.add_argument('--input',type=Path);ap.add_argument('--project-id',default='visual-project');ap.add_argument('--test-mode',action='store_true');ap.add_argument('--call-budget',type=int,default=4);ap.add_argument('--expected-seq',type=int)
    a=ap.parse_args()
    try:
        if a.action=='init':out=create(a.project,a.project_id,a.test_mode,a.call_budget);out={'schema':out['schema'],'project_id':out['project_id']}
        elif a.action=='status':out=summary(a.project)
        elif a.action=='export':out=load(a.project)
        else:
            if not a.input:ap.error('--input is required')
            out=perform(a.project,a.action,json.loads(a.input.read_text(encoding='utf-8')),a.expected_seq)
        print(dump(out));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
