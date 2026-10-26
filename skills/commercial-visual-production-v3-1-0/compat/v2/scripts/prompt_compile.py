#!/usr/bin/env python3
"""Compact task prompts, reusable intake and file-validated prompt cache; no AI calls."""
import argparse,hashlib,json,sys,subprocess
from pathlib import Path
from decimal import Decimal
from _common import load_project,validate_project

RULE_FILE=Path(__file__).resolve().parents[1]/'assets/prompt_rules.json'
def text_json(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def hashfile(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def unique(items):return list(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))
def boxtext(e):
 x,y,w,h=e['box']
 def pct(value):
  s=format(Decimal(str(value))*100,'f');return (s.rstrip('0').rstrip('.') if '.' in s else s)+'%'
 return f"{e['id']}：左{pct(x)}、上{pct(y)}、宽{pct(w)}、高{pct(h)}"
def read_brief(p):
 if not p:return {}
 value=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(value,dict):raise ValueError('brief must be an object')
 for key in ('notes','required_effects','forbidden','asset_descriptions','input_images'):
  if key in value and not isinstance(value[key],list):raise ValueError(key+' must be a list')
 for key in ('notes','required_effects','forbidden'):
  if any(not isinstance(x,str) for x in value.get(key,[])):raise ValueError(key+' items must be text')
 return value

def compile_compact(spec,out,task='background',brief_path=None):
 project,root=load_project(spec);preflight,_=validate_project(project,root)
 if preflight['status']=='BLOCK':raise ValueError('invalid blueprint: '+'; '.join(preflight['errors']))
 brief_path=brief_path or (root/'generation_brief.json' if (root/'generation_brief.json').is_file() else None)
 brief=read_brief(brief_path);rules=json.loads(RULE_FILE.read_text(encoding='utf-8'))
 inputs={'spec':hashfile(spec),'compiler':hashfile(__file__),'rules':hashfile(RULE_FILE)}
 if brief_path:inputs['brief']=hashfile(brief_path)
 for e in project['elements']:
  if e.get('source') and (root/e['source']).is_file():inputs['asset:'+e['id']]=hashfile(root/e['source'])
  auth=e.get('edit_authorization',{}).get('evidence_file')
  if auth:inputs['authorization:'+e['id']]=hashfile(root/auth)
 images=[]
 for i,entry in enumerate(brief.get('input_images',[]),1):
  if not isinstance(entry,dict) or not entry.get('role') or not entry.get('description'):raise ValueError('input_images need path, role and description')
  p=(root/entry.get('path','')).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ValueError('input image missing or outside project')
  images.append({'path':str(p),'role':entry['role'],'description':entry['description']})
  inputs['input:'+str(i)]=hashfile(p)
 key=hashlib.sha256(text_json({'inputs':inputs,'task':task,'project_root':str(root)}).encode()).hexdigest()
 out.mkdir(parents=True,exist_ok=True);manifest=out/('.prompt_manifest.'+task+'.json')
 if manifest.is_file():
  try:
   old=json.loads(manifest.read_text(encoding='utf-8'))
   if isinstance(old,dict) and isinstance(old.get('output_hashes'),dict) and old.get('cache_key')==key and all((out/n).is_file() and hashfile(out/n)==h for n,h in old.get('output_hashes',{}).items()) and old.get('output_hashes'):
    return {'status':'COMPILED','input_status':preflight['status'],'cache_hit':True,'files':list(old['output_hashes']),'manifest':str(manifest),'intake_gaps':old.get('intake_gaps',[])}
  except (ValueError,OSError,AttributeError,TypeError):pass
 elements=project['elements'];reserved=[e for e in elements if e.get('lock') in ('L0','L1') or e.get('role') in ('person','coach','product','logo','architecture','headline','subhead','text','negative_space')]
 allowed=[e for e in elements if e.get('role') in ('background','decoration') and e.get('lock','L3') in ('L2','L3')]
 notes=unique(brief.get('notes',[]));positive=unique(project.get('style_rules',[])+brief.get('required_effects',[]))
 forbids=unique(project.get('forbidden_elements',[])+brief.get('forbidden',[]))
 conflicts=set(brief.get('required_effects',[]))&set(forbids)
 if conflicts:raise ValueError('required/forbidden conflict: '+','.join(sorted(conflicts)))
 rows=['任务：'+('仅制作海报背景及允许的辅助视觉。' if task=='background' else '按本轮要求局部修改已有基准图。'),f"目标：{project['canvas']['width']}×{project['canvas']['height']}；主色{project['canvas'].get('background','#FFFFFF')}。"]
 direction=brief.get('goal') or project.get('creative_direction')
 if direction:rows.append('意图：'+str(direction))
 if images:rows.append('实际附图角色：'+'；'.join(f"图{i}：{e['role']}，{e['description']}" for i,e in enumerate(images,1)))
 if positive:rows.append('风格：'+'；'.join(positive))
 if task=='background':
  if allowed:rows.append('生成：'+'；'.join(boxtext(e)+(('，'+str(e['visual_spec'])) if e.get('visual_spec') else '') for e in allowed))
  if reserved:rows.append('预留/保护：'+'；'.join(boxtext(e) for e in reserved)+'。')
 else:
  if not project.get('editable_regions'):raise ValueError('local edit needs explicit editable_regions')
  if not brief.get('change_request'):raise ValueError('local edit needs change_request in brief')
  rows.append('本轮只改：'+str(brief['change_request']))
  rows.append('编辑区：'+text_json(project['editable_regions']))
  rows.append('保护区：'+text_json(project.get('protected_regions',[])))
  if reserved:rows.append('保留对象（明确授权子区除外）：'+'；'.join(boxtext(e) for e in reserved))
 if notes:rows.append('项目注意事项：'+'；'.join(notes))
 descriptions=list(brief.get('asset_descriptions',[]))
 explicit_ids={e.get('id') for e in descriptions if isinstance(e,dict)}
 descriptions += [{'id':e['id'],'description':e['description']} for e in elements if e.get('description') and e['id'] not in explicit_ids]
 for e in descriptions:
  if not isinstance(e,dict) or not e.get('id') or not e.get('description'):raise ValueError('asset_descriptions need id and description')
 if descriptions:rows.append('素材说明：'+'；'.join(str(e['id'])+'：'+str(e['description']) for e in descriptions))
 negatives=unique(rules['base']+rules['background' if task=='background' else 'local_edit']+forbids)
 rows.append('禁止事项：'+'；'.join(negatives))
 rows.append('尺寸和坐标是制作目标，生成后须实测校正；本提示不证明保真、像素硬锁或可编辑分层。')
 name='01_background_prompt.txt' if task=='background' else '02_local_edit_contract.txt'
 files={name:'\n'.join(rows)+'\n'}
 if reserved:files['03_original_asset_contract.txt']='\n'.join(e['id']+' | '+e.get('role','')+' | '+e.get('source','SOURCE_MISSING') for e in reserved if e.get('role')!='negative_space')+'\n'
 for n,s in files.items():(out/n).write_text(s,encoding='utf-8')
 gaps=[]
 described={e['id'] for e in descriptions}
 for e in reserved:
  if e.get('source') and not e.get('description') and e['id'] not in described:gaps.append('复用或补齐素材说明：'+e['id'])
 data={'cache_key':key,'input_hashes':inputs,'output_hashes':{n:hashfile(out/n) for n in files},'input_images':images,'intake_gaps':gaps,'scope':'compiled draft; semantic conflicts and actual tool image mapping still require assistant check'}
 manifest.write_text(text_json(data),encoding='utf-8')
 return {'status':'COMPILED','input_status':preflight['status'],'cache_hit':False,'files':list(files),'manifest':str(manifest),'intake_gaps':gaps}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--brief',type=Path);ap.add_argument('--task',choices=['background','local-edit'],default='background');ap.add_argument('--format',choices=['compact','legacy'],default='compact')
 a=ap.parse_args()
 if a.format=='legacy':return subprocess.call([sys.executable,str(Path(__file__).with_name('_legacy_prompt_compile.py')),'--spec',str(a.spec),'--out',str(a.out)])
 try:print(text_json(compile_compact(a.spec,a.out,a.task,a.brief)));return 0
 except (ValueError,OSError,TypeError,KeyError) as exc:print(text_json({'status':'BLOCK','error':str(exc)}));return 2
if __name__=='__main__':sys.exit(main())
