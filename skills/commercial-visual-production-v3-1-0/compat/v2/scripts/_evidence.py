"""Versioned local evidence bindings. Integrity is not proof of authorship."""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

VERSION='2.2.0'
SCHEMA='cvisual.audit.v2'
SCRIPT_ROOT=Path(__file__).resolve().parent
TOOLS={
 'preflight':('blueprint.py',{'blueprint'}, {'guide','preview','editable_mask','protected_mask'}),
 'locked_edit':('locked_edit.py',{'blueprint','baseline','candidate'},{'locked'}),
 'layout_audit':('layout_audit.py',{'blueprint','observed','image'},set()),
 'pixel_audit':('pixel_audit.py',{'blueprint','image'},set()),
 'layer_export':('export_layers.py',{'blueprint'},{'merged','ora'}),
}
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def file_record(path,base):
 p=Path(path).resolve()
 if not p.is_file():raise ValueError(f'证据文件不存在：{p}')
 try:name=os.path.relpath(p,Path(base).resolve())
 except ValueError:name=str(p)  # Standalone diagnostics can span Windows drives; review still requires project-local evidence.
 return {'path':name,'sha256':digest(p)}

# Only computation/evidence dependencies invalidate a report. _compact changes display only.
TOOL_DEPENDENCIES={
 'preflight':('blueprint.py','_common.py','_evidence.py','_images.py','export_layers.py'),
 'locked_edit':('locked_edit.py','_common.py','_evidence.py','_images.py'),
 'layout_audit':('layout_audit.py','_common.py','_evidence.py'),
 'pixel_audit':('pixel_audit.py','_common.py','_evidence.py','_images.py'),
 'layer_export':('export_layers.py','_common.py','_evidence.py','_images.py'),
}
def tool_fingerprint(tool):
 return {name:digest(SCRIPT_ROOT/name) for name in TOOL_DEPENDENCIES[tool]}

def save_report(path,tool,result,inputs,outputs=None):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 data=dict(result)
 data.update(schema=SCHEMA,tool=tool,tool_version=VERSION,
             created_at=datetime.now(timezone.utc).isoformat(),
             implementation=tool_fingerprint(tool),
             inputs={k:file_record(v,p.parent) for k,v in inputs.items()},
             outputs={k:file_record(v,p.parent) for k,v in (outputs or {}).items()})
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 return data

def project_inputs(project,root,spec):
 result={'blueprint':Path(spec)}
 for e in project.get('elements',[]):
  if e.get('source') and (root/e['source']).is_file():result['asset:'+e['id']]=root/e['source']
  if e.get('edit_authorization',{}).get('evidence_file'):
   result['authorization:'+e['id']]=root/e['edit_authorization']['evidence_file']
 return result

def verify_report(path,tool,project_root):
 """Rehash inputs AND outputs, require expected tool/schema/metrics."""
 p=Path(path).resolve();root=Path(project_root).resolve()
 try:
  obj=json.loads(p.read_text(encoding='utf-8'))
  if not isinstance(obj,dict):raise ValueError('报告顶层必须是JSON对象')
  if obj.get('schema')!=SCHEMA or obj.get('tool')!=tool:raise ValueError('报告schema或工具类型不匹配；请用新版工具重新检测')
  if obj.get('tool_version')!=VERSION or obj.get('implementation')!=tool_fingerprint(tool):raise ValueError('工具版本已变化，请重新检测')
  _,required_in,required_out=TOOLS[tool]
  for group,required in [('inputs',required_in),('outputs',required_out)]:
   items=obj.get(group)
   if not isinstance(items,dict) or not required.issubset(items):raise ValueError(f'报告缺少{group}工件绑定')
   for label,rec in items.items():
    if not isinstance(rec,dict) or not isinstance(rec.get('path'),str):raise ValueError(f'{group}.{label}不是文件记录')
    f=(p.parent/rec['path']).resolve()
    if not f.is_relative_to(root):raise ValueError(f'证据必须位于当前项目内：{label}')
    if not f.is_file() or digest(f)!=rec.get('sha256'):raise ValueError(f'证据已改变或丢失：{label}')
  status=obj.get('status')
  if status not in {'PASS','BLOCK','UNKNOWN','DRAFT_ONLY','RENDERABLE','INCOMPLETE'}:raise ValueError('报告状态无效')
  if tool=='locked_edit' and status=='PASS':
   if any(obj.get(k)!=0 for k in ['changed_outside_editable','changed_in_protected']):raise ValueError('硬锁指标无效')
   if not isinstance(obj.get('editable_pixels'),int) or obj['editable_pixels']<=0:raise ValueError('缺少有效编辑区')
  if tool=='layer_export' and status=='RENDERABLE' and obj.get('missing_required_assets')!=[]:raise ValueError('图层素材不完整')
  if tool=='pixel_audit' and status=='PASS':
   if not obj.get('checks') or any(c.get('status')!='PASS' or c.get('nonopaque_pixels',0)!=0 for c in obj['checks']):raise ValueError('颜色检查缺少有效不透明样本')
  if tool=='layout_audit' and status=='PASS' and (obj.get('failures')!=0 or obj.get('unknowns')!=0):raise ValueError('布局指标无效')
  return obj
 except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
  raise ValueError(str(exc)) from exc
