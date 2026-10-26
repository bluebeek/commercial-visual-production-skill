"""Non-destructive migration inventory and archive. No legacy approval becomes a V3 decision."""
import argparse,json,shutil,sys
from pathlib import Path
from _workflow import *
MAP={'R3.real_assets':['R1','R3'],'R3.type_plan':['R2','R3'],'R3.task_split':['R3'],'R4.target':['R3','R4'],'R0.roles':['R0'],'R0.assets':['R1'],'R0.scope':['R1'],'R1':['R0'],'R2':['R2'],'R3.preview':['R2'],'R3':['R3'],'R4':['R3','R5'],'R5':['R4'],'R6.layers':['R6'],'R6.file_check':['R6'],'R6':['R4']}
def target(cid):return MAP.get(cid,MAP.get(cid.split('.')[0],['R4']))
def migrate(source,destination,apply=False):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.is_relative_to(source) or source.is_relative_to(destination):raise WorkflowError('migration needs a separate destination')
    old=json.loads((source/'review_state.json').read_text(encoding='utf-8'));files={};missing=[];changed=[]
    def visit(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('files','baseline_files','resolution_files') and isinstance(v,dict):
                    for n in v:
                        p=local(source,n,False)
                        if p.is_file():
                            files[n]=sha(p)
                            if isinstance(v[n],str) and v[n]!=files[n]:changed.append(n)
                        else:missing.append(n)
                else:visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
    visit(old)
    result={'source':str(source),'destination':str(destination),'legacy_schema':old.get('schema'),
            'mapped_checks':{k:target(k) for k in old.get('checks',{})},
            'mapped_issues':[dict(i,new_stages=target(i.get('check_id','R4')),new_status='ready_for_review' if i.get('status')=='resolved' else 'unbound_pending') for i in old.get('issues',[])],
            'bound_files':files,'missing_files':sorted(set(missing)),'changed_files':sorted(set(changed)),'approvals_imported':0,'status':'DRY_RUN'}
    if apply:
        if destination.exists():raise WorkflowError('destination must not exist')
        create(destination,'migrated-project',False,4)
        archive=destination/'legacy-source';archive.mkdir()
        shutil.copy2(source/'review_state.json',archive/'review_state.json')
        for n in files:
            out=local(archive,n,False);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(local(source,n),out)
        def imported(s,r):s['migration']=result;return result
        transact(destination,imported);result['status']='IMPORTED_UNBOUND'
    return result
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True,type=Path);a.add_argument('--project',required=True,type=Path);a.add_argument('--apply',action='store_true');o=a.parse_args()
    try:print(dump(migrate(o.source,o.project,o.apply)))
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));sys.exit(2)
