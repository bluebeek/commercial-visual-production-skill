#!/usr/bin/env python3
"""Read-only impact inventory: no snapshot writes and no report reruns."""
import argparse,copy,json,sys
from pathlib import Path
import review_engine as engine
from _evidence import digest,tool_fingerprint,verify_report,TOOLS

def inspect_report(file,root):
 obj=json.loads(file.read_text(encoding='utf-8'))
 if not isinstance(obj,dict) or obj.get('schema')!='cvisual.audit.v2' or obj.get('tool') not in TOOLS:return None
 tool=obj['tool'];expected=tool_fingerprint(tool);actual=obj.get('implementation',{})
 changed=[n for n in sorted(set(expected)|set(actual)) if expected.get(n)!=actual.get(n)]
 source_changes=[]
 for group in ('inputs','outputs'):
  for label,rec in obj.get(group,{}).items():
   try:
    p=(file.parent/rec['path']).resolve()
    if not p.is_relative_to(root) or not p.is_file() or digest(p)!=rec.get('sha256'):source_changes.append(group+':'+label)
   except (TypeError,KeyError,OSError):source_changes.append(group+':'+label)
 try:verify_report(file,tool,root);valid=True;reason=None
 except ValueError as exc:valid=False;reason=str(exc)
 return {'path':str(file),'tool':tool,'recorded_status':obj.get('status'),'valid':valid,'changed_implementations':changed,'changed_bound_files':source_changes,'reason':reason}

def inspect_tree(root):
 root=Path(root).resolve();reports=[];states=[];errors=[]
 for file in root.rglob('*.json'):
  if any(part in {'node_modules','.git','__pycache__','.review-history'} for part in file.parts):continue
  try:
   if file.name=='review_state.json':
    before=digest(file)
    try:
     state=engine.load(file.parent);preview=copy.deepcopy(state);engine.refresh(preview,file.parent)
     changed=[k for k,v in state['checks'].items() if v['status']!=preview['checks'][k]['status']]
     states.append({'path':str(file),'schema':state.get('schema'),'signoffs':list(state.get('signoffs',{})),'would_change_checks':changed,'file_unchanged':digest(file)==before})
    except (ValueError,OSError) as exc:states.append({'path':str(file),'error':str(exc),'file_unchanged':digest(file)==before})
   elif file.name in {'preflight.json','layout_audit.json','pixel_audit.json','layer_export_report.json','locked_edit.report.json','locked.report.json'} or file.name.endswith('.report.json'):
    row=inspect_report(file,root)
    if row:reports.append(row)
  except (ValueError,TypeError,OSError) as exc:errors.append({'path':str(file),'error':str(exc)})
 return {'root':str(root),'reports':reports,'states':states,'errors':errors,'counts':{'reports':len(reports),'invalid_reports':sum(not r['valid'] for r in reports),'states':len(states)}}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,action='append',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 rows=[inspect_tree(p) for p in a.root];a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps({'mode':'read-only','roots':rows},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'mode':'read-only','out':str(a.out),'counts':[r['counts'] for r in rows]},ensure_ascii=False));return 0
if __name__=='__main__':sys.exit(main())
