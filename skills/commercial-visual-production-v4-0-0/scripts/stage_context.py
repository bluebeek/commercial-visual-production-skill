"""Compact projections from the single V3 state; caches never grant permission."""
import argparse,json,sys
from pathlib import Path
from _workflow import *
from workflow import perform

def build(root,stage='R3',since=None,budget=8000):
    s=load(root);value=context(s,root,stage);cid=objhash(value)
    cache=Path(root)/'.visual-context'/('v3-'+stage+'.json')
    try:
        old=json.loads(cache.read_text(encoding='utf-8'))
        if not isinstance(old,dict) or not isinstance(old.get('value'),dict):old=None
    except (OSError,ValueError):old=None
    out={'context_id':cid,'status':value['status'],'chars':len(dump(value)),'soft_budget_exceeded':len(dump(value))>budget}
    if since==cid:out['kind']='unchanged'
    elif old and since==old.get('id'):out.update(kind='delta',base=since,changed={k:v for k,v in value.items() if old['value'].get(k)!=v},removed=[k for k in old['value'] if k not in value])
    else:out.update(kind='full',context=value)
    atomic(cache,{'id':cid,'value':value});return out

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=['put','build']);a.add_argument('--project',required=True,type=Path);a.add_argument('--stage',required=True,choices=list(STAGES));a.add_argument('--input',type=Path);a.add_argument('--since');a.add_argument('--budget-chars',type=int,default=8000);o=a.parse_args()
    try:
        if o.action=='put':
            if not o.input:a.error('--input required')
            d=json.loads(o.input.read_text(encoding='utf-8'));d['stage']=o.stage;out=perform(o.project,'stage',d)
        else:out=build(o.project,o.stage,o.since,o.budget_chars)
        print(dump(out));return 2 if out.get('status')=='BLOCK' else 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
