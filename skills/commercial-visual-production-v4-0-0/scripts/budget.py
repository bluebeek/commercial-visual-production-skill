"""One local execution owner and one shared, conservative image-attempt ledger."""
import argparse, copy, json, sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from _workflow import WorkflowError, atomic, load, now, sha, transact
from _storage import project_lock

def money(value):
    try:d=Decimal(str(value))
    except InvalidOperation:raise WorkflowError('invalid USD amount')
    if not d.is_finite() or d<0:raise WorkflowError('USD amount must be finite and nonnegative')
    return d

def lock(path):return project_lock(Path(path).resolve().parent/('.budget-lock-'+Path(path).name))

def init(path, calls=0, usd='0', test_mode=False):
    p=Path(path).resolve()
    if type(calls) is not int or calls<0:raise WorkflowError('invalid attempt limit')
    with lock(p):
        if p.exists():raise WorkflowError('budget exists; never reset spent attempts')
        d={'schema':'cvisual.budget.v1','test_mode':bool(test_mode),'calls_limit':calls,'usd_limit':str(money(usd)),
           'owners':{},'attempts':{},'events':[],'created_at':now()};atomic(p,d)
    return d

def read(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    if d.get('schema')!='cvisual.budget.v1':raise WorkflowError('invalid shared budget')
    return d

def bind(project, ledger):
    project=Path(project).resolve();ledger=Path(ledger).resolve()
    if ledger.is_relative_to(project):raise WorkflowError('shared budget must be outside portable project')
    def op(s,r):
        if s.get('execution_lease'):raise WorkflowError('project already bound; release before rebinding')
        with lock(ledger):
            b=read(ledger);pid=s['project_uuid'];owner=b['owners'].get(pid)
            if b['test_mode']!=s['test_mode']:raise WorkflowError('test budget cannot authorize production')
            if owner not in (None,str(r)):raise WorkflowError('project is owned by another execution directory')
            if any(a['project_uuid']==pid and a['status'] in ('reserved','attempted','unknown') for a in b['attempts'].values()):
                raise WorkflowError('unresolved request blocks budget takeover')
            b['owners'][pid]=str(r);b['events'].append({'at':now(),'action':'bind','project_uuid':pid,'root':str(r)});atomic(ledger,b)
        s['execution_lease']={'ledger':str(ledger),'root':str(r)};return {'status':'BOUND','project_uuid':pid}
    return transact(project,op)

def owned(s,root):
    lease=s.get('execution_lease')
    if not lease or lease.get('root')!=str(Path(root).resolve()):raise WorkflowError('no execution ownership; bind or hand off project')
    p=Path(lease['ledger']).resolve()
    if p.is_relative_to(Path(root).resolve()):raise WorkflowError('portable budget copy cannot authorize calls')
    return p

def reserve(s,root,job_id,maximum_usd,selection):
    p=owned(s,root);amount=money(maximum_usd)
    if amount<=0:raise WorkflowError('positive conservative maximum cost required')
    with lock(p):
        b=read(p);pid=s['project_uuid'];key=pid+':'+job_id
        if b['test_mode']!=s['test_mode'] or b['owners'].get(pid)!=str(Path(root).resolve()):raise WorkflowError('wrong budget execution owner')
        if key in b['attempts']:raise WorkflowError('attempt already reserved; no duplicate submit')
        total=sum((money(a['cost_usd'] if a.get('cost_usd') is not None else a['reserved_usd']) for a in b['attempts'].values()),Decimal(0))
        if len(b['attempts'])>=b['calls_limit'] or total+amount>money(b['usd_limit']):raise WorkflowError('shared attempt or USD budget exhausted')
        b['attempts'][key]={'project_uuid':pid,'job_id':job_id,'status':'reserved','reserved_usd':str(amount),'cost_usd':None,
                            'model':selection['model'],'provider':selection['provider'],'at':now()}
        atomic(p,b);return key

def mark(s,root,key,status,request_id=None):
    if status not in ('attempted','returned','failed','unknown'):raise WorkflowError('invalid attempt result')
    p=owned(s,root)
    with lock(p):
        b=read(p);a=b['attempts'][key]
        if a['project_uuid']!=s['project_uuid'] or b['owners'].get(s['project_uuid'])!=str(Path(root).resolve()):raise WorkflowError('wrong attempt owner')
        allowed={'reserved':{'attempted','unknown'},'attempted':{'returned','failed','unknown'}}
        if status not in allowed.get(a['status'],set()):raise WorkflowError('attempt cannot be replayed or rewritten')
        a.update(status=status,request_id=request_id,updated_at=now());atomic(p,b)

def release(project):
    def op(s,r):
        p=owned(s,r)
        if any(j.get('status') in ('running','result_unknown') for j in s['jobs'].values()):raise WorkflowError('running/unknown jobs block handoff')
        with lock(p):
            b=read(p);pid=s['project_uuid']
            if any(a['project_uuid']==pid and a['status'] in ('reserved','attempted','unknown') for a in b['attempts'].values()):raise WorkflowError('unresolved attempts block handoff')
            if b['owners'].get(pid)!=str(r):raise WorkflowError('not execution owner')
            b['owners'][pid]=None;b['events'].append({'at':now(),'action':'release','project_uuid':pid});atomic(p,b)
        s['execution_lease']=None;return {'status':'RELEASED','spent_attempts_preserved':True}
    return transact(project,op)

def reconcile(project,key,status,evidence,cost_usd=None):
    """Explicit operator reconciliation, never a refund or a generated candidate."""
    if status not in ('returned','failed'):raise WorkflowError('reconciliation needs final provider outcome')
    s=load(project);p=owned(s,project);e=Path(evidence).resolve()
    if not e.is_file():raise WorkflowError('provider/billing evidence file required')
    with lock(p):
        b=read(p);a=b['attempts'][key]
        if a['project_uuid']!=s['project_uuid'] or a['status'] not in ('reserved','attempted','unknown','returned','failed'):raise WorkflowError('wrong reconciliation target')
        a.update(status=status,reconciliation={'path':str(e),'sha256':sha(e),'at':now()})
        if cost_usd is not None:a['cost_usd']=str(money(cost_usd))
        atomic(p,b)
    return {'status':'RECONCILED','calls_refunded':0,'candidate_created':False}

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=['init','bind','release','inspect']);a.add_argument('--ledger',type=Path);a.add_argument('--project',type=Path);a.add_argument('--calls',type=int,default=0);a.add_argument('--usd',default='0');a.add_argument('--test-mode',action='store_true');o=a.parse_args()
    try:
        if o.action=='init':r=init(o.ledger,o.calls,o.usd,o.test_mode)
        elif o.action=='bind':r=bind(o.project,o.ledger)
        elif o.action=='release':r=release(o.project)
        else:r=read(o.ledger)
        print(json.dumps(r,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps({'status':'BLOCK','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
