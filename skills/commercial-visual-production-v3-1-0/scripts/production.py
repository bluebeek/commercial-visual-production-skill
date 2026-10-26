"""Compile four generation tasks from V3 state. Only the active assistant calls image_gen."""
import argparse,copy,json,sys
from pathlib import Path
from decimal import Decimal
from PIL import Image
from _workflow import *
from _common import load_project,validate_project,mask_for_regions,protection_mask

KINDS=('background','asset','whole','local-edit')
BASE=['只出现本轮列出的主体、文字与效果，不自行添加人物、产品、道具、Logo、水印或装饰。','遵守明确的主次、遮挡与留白；避免非设计意图的重影、断裂、糊边和色带，保留明确要求的颗粒、笔触等效果。','每张输入图只按指定角色使用，不复制未被采用的品牌、身份或文案。']
TASK_NEG={'background':'只生成背景和指定辅助图形。真实产品、人物、Logo及正式文案由原件合成，预留对应区域，不生成替代物。',
          'asset':'只生成本任务指定的独立素材，禁止出现其他主体或未要求的背景、文字。',
          'whole':'仅渲染明确提供的文案；不改写、不添加、不漏字。保留需后期合成的真实素材位置。',
          'local-edit':'仅改变明确编辑区及允许过渡区。保持其余画面，不顺带重新构图、裁切、缩放、全局调色或改变其他主体和文字。'}

def implementation():return {f:sha(Path(__file__).parent/f) for f in ('production.py','workflow.py','_workflow.py','_common.py','photocraft.py','ora_verify.py')}
def pct(x):return format(Decimal(str(x))*100,'f').rstrip('0').rstrip('.')+'%' if '.' in format(Decimal(str(x))*100,'f') else format(Decimal(str(x))*100,'f')+'%'
def geometry(e):
    x,y,w,h=e['box'];return e['id']+'：左'+pct(x)+'、上'+pct(y)+'、宽'+pct(w)+'、高'+pct(h)
def current_inputs(s,root,spec):
    files={}
    for sid in ('R0','R1','R2'):files.update(s['stages'][sid]['files'])
    for r in active(s):files.update(r['files'])
    for a in s['assets'].values():files.update(a['files'])
    files.update(bind(root,[spec]));p,base=load_project(local(root,spec))
    for e in p['elements']:
        if e.get('source'):files.update(bind(root,[(base/e['source']).relative_to(root).as_posix()]))
    return files

def validate_job(s,root,j,check_budget=True):
    ctx=context(s,root)
    if ctx['status']!='READY' or not approved_blueprint(s,root):raise WorkflowError('generation blocked: missing/stale stages, assets, requirements or blueprint decision')
    if j['rules_hash']!=rules_hash(s) or j['blueprint_id']!=s['stages']['R2']['id']:raise WorkflowError('job uses superseded intent/blueprint')
    if j['implementation']!=implementation():raise WorkflowError('compiler changed; prepare a new job')
    if not fresh(root,j['input_files']) or not fresh(root,j['compiled_files']):raise WorkflowError('job evidence/prompt changed; recompile')
    if j.get('tool_args_file'):
        saved=json.loads(local(root,j['tool_args_file']).read_text(encoding='utf-8'))
        paths=[str(local(root,x['path'])) for x in j.get('input_images',[])]
        if saved.get('referenced_image_paths',[])!=paths:raise WorkflowError('project moved or actual attachment paths changed; prepare a new job')
    if not fresh(root,{p:h for r in active(s) for p,h in r['files'].items()}):raise WorkflowError('requirement source changed')
    if j.get('baseline') and not rev_fresh(s,root,j['baseline'],False):raise WorkflowError('baseline missing/stale')
    if check_budget and s['calls_used']>=s['call_budget']:raise WorkflowError('image call budget exhausted; failures count')
    return True

def prepare(s,root,d):
    jid=ident(d.get('id'));kind=d.get('kind')
    if jid in s['jobs']:raise WorkflowError('job id immutable')
    if kind not in KINDS:raise WorkflowError('unsupported generation task')
    ctx=context(s,root)
    if ctx['status']!='READY' or not approved_blueprint(s,root):raise WorkflowError('R0-R2/current inputs and real blueprint confirmation required')
    for r in active(s):
        if not fresh(root,r['files']):raise WorkflowError('requirement evidence stale: '+r['id'])
    spec=d.get('spec') or s['stages']['R2']['data']['spec'];project,base=load_project(local(root,spec))
    pre,_=validate_project(project,base,'draft')
    if pre['status']=='BLOCK':raise WorkflowError('; '.join(pre['errors']))
    approved,approved_base=load_project(local(root,s['stages']['R2']['data']['spec']))
    if project['canvas']!=approved['canvas']:raise WorkflowError('canvas changed; update R2')
    # Mask changes and generated source updates are permitted. Layout/lock changes require R2.
    def structure(p):return [{k:e.get(k) for k in ('id','role','box','z','lock','text')} for e in p['elements'] if e.get('provenance')!='raster_patch']
    if structure(project)!=structure(approved):raise WorkflowError('layout/locks/text changed; update R2 before production')
    for e,a in zip([e for e in project['elements'] if e.get('provenance')!='raster_patch'],[e for e in approved['elements'] if e.get('provenance')!='raster_patch']):
        if a.get('lock') in ('L0','L1'):
            if not e.get('source') or not a.get('source') or sha(base/e['source'])!=sha(approved_base/a['source']):raise WorkflowError('protected original changed')
    baseline=d.get('baseline');change=d.get('change_request','')
    patches=[e for e in project['elements'] if e.get('provenance')=='raster_patch']
    if patches:
        if not baseline or baseline not in s['revisions']:raise WorkflowError('patch layers need a registered parent')
        old,_=load_project(local(root,s['revisions'][baseline]['spec']))
        if patches!=[e for e in old['elements'] if e.get('provenance')=='raster_patch']:raise WorkflowError('parent patch layers changed')
    images=d.get('input_images',[])
    if not isinstance(images,list):raise WorkflowError('input_images must be ordered')
    image_records=[]
    for entry in images:
        if not isinstance(entry,dict) or not entry.get('role') or not entry.get('description'):raise WorkflowError('input images need role and description')
        p=local(root,entry['path'])
        with Image.open(p) as im:im.verify()
        image_records.append({'path':p.relative_to(root).as_posix(),'role':entry['role'],'description':entry['description'],'sha256':sha(p)})
    regions=project.get('editable_regions',[])
    if kind=='local-edit':
        if not baseline or baseline!=s['working_revision'] or not rev_fresh(s,root,baseline,False):raise WorkflowError('select the actual working baseline before local edit')
        if not change or not regions:raise WorkflowError('local edit needs change_request and explicit regions')
        r=s['revisions'][baseline]
        if not image_records or image_records[0]['role']!='baseline' or image_records[0]['sha256']!=r['files'][r['image']]:raise WorkflowError('image 1 must be the registered baseline')
        w,h=project['canvas']['width'],project['canvas']['height'];mask=mask_for_regions(regions,w,h)
        if not mask.any() or (mask & protection_mask(project,base,w,h)).any():raise WorkflowError('editable/protected mask conflict')
        with Image.open(local(root,r['image'])) as im:
            if im.size!=(w,h):raise WorkflowError('baseline dimensions differ')
    elif baseline:raise WorkflowError('baseline only applies to local-edit tasks')
    if not isinstance(d.get('goal'),str) or not d['goal'].strip():raise WorkflowError('task goal required')
    feather=d.get('feather',0)
    if not isinstance(feather,int) or not 0<=feather<=200:raise WorkflowError('invalid inner feather')
    notes=d.get('notes',[])
    if not isinstance(notes,list) or any(not isinstance(x,str) for x in notes):raise WorkflowError('notes must be text list')
    rows=['任务：'+{'background':'制作海报背景及指定辅助图形','asset':'制作独立辅助素材','whole':'制作完整海报候选','local-edit':'基于实际图像做限定范围修改'}[kind]+'。','本轮目标：'+d['goal'],
          '用途：'+s['stages']['R1']['data']['purpose'],'画布目标：%s × %s 像素。'%(project['canvas']['width'],project['canvas']['height'])]
    for n,im in enumerate(image_records,1):rows.append('图%d：%s；%s。'%(n,im['role'],im['description']))
    if not image_records:rows.append('本次没有附图；以下构图与风格说明来自项目已确认的文字要求。')
    rows.append('构图：'+'；'.join(geometry(e) for e in project['elements'] if e.get('provenance')!='raster_patch'))
    coverage={};rules=copy.deepcopy(active(s))
    for r in rules:
        coverage[r['id']]={'production':r['method'],'check':'req:'+r['id']}
        if r['method'] in ('prompt','both'):rows.append('保持要求 ['+r['id']+']：'+r['text'])
    for a in s['assets'].values():rows.append('素材 '+a['id']+'：'+a['description']+'；必须保留：'+'、'.join(a['must_keep'])+'；允许处理：'+'、'.join(a['allowed_changes']))
    if kind=='local-edit':
        rows.append('本轮只改：'+change)
        rectangles=[r for r in regions if 'rect' in r]
        for reg in rectangles:
            x0,y0,x1,y1=reg['rect'];rows.append('允许区 '+reg.get('id','')+'：左'+pct(x0)+'、上'+pct(y0)+'、右'+pct(x1)+'、下'+pct(y1)+'。')
        points=[p for reg in regions if 'polygon' in reg for p in reg['polygon']]
        if points:
            xs,ys=zip(*points)
            rows.append('对象局部选区大致位于：左'+pct(min(xs))+'、上'+pct(min(ys))+'、右'+pct(max(xs))+'、下'+pct(max(ys))+'。只处理本轮描述的对象局部，精确边界由后续合成选区控制。')
        retained=[x for x in s['revisions'][baseline]['requirements'] if x['id'] in {a['id'] for a in rules}]
        if retained:rows.append('除本轮列出的修改外，其他当前有效要求及已完成内容保持。')
    if notes:rows.append('本项目注意：'+'；'.join(dict.fromkeys(notes)))
    negative=TASK_NEG[kind]
    if kind=='local-edit' and d.get('allow_global_adjustment'):
        negative='仅在明确授权区域执行本轮要求的整体处理。其余主体、文字、构图和未经授权的属性保持。'
    rows.append('禁止事项：'+'；'.join(BASE+[negative]))
    rows.append('输出：'+('真实透明背景素材；透明通道实际核验。' if d.get('transparent_background') else '保持指定画布比例；不额外加边框。'))
    prompt='\n'.join(rows)+'\n'
    args={'prompt':prompt,'transparent_background':bool(d.get('transparent_background',False))}
    if image_records:args['referenced_image_paths']=[str(local(root,x['path'])) for x in image_records]
    folder=root/'production'/jid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'prompt.txt').write_text(prompt,encoding='utf-8');atomic(folder/'tool_args.json',args);atomic(folder/'composition_plan.json',{'editable_regions':regions if kind=='local-edit' else [],'feather':feather})
    files=current_inputs(s,root,spec)
    for im in image_records:files.update(bind(root,[im['path']]))
    if baseline:files.update(s['revisions'][baseline]['files'])
    j={'id':jid,'kind':kind,'status':'waiting_execution','goal':d['goal'],'change_request':change,'baseline':baseline,'spec':spec,
       'blueprint':project,'blueprint_id':s['stages']['R2']['id'],'requirements':rules,'rules_hash':rules_hash(s),'coverage':coverage,
       'input_images':image_records,'input_files':files,'compiled_files':bind(root,[(folder/'prompt.txt').relative_to(root),(folder/'tool_args.json').relative_to(root),(folder/'composition_plan.json').relative_to(root)]),
       'tool_args_file':(folder/'tool_args.json').relative_to(root).as_posix(),'tool_args_hash':objhash(args),'implementation':implementation(),
       'editable_regions':regions if kind=='local-edit' else [],'feather':feather,'notes':notes,'allow_global_adjustment':bool(d.get('allow_global_adjustment',False)),'output_files':{},'at':now()}
    s['jobs'][jid]=j
    return {'status':'WAITING_EXECUTION','job_id':jid,'tool_args_file':j['tool_args_file'],'coverage':coverage,'prompt_chars':len(prompt),'notice':'not generated; assistant must inspect referenced images and invoke built-in image_gen'}

def begin(s,root,d):
    j=s['jobs'][d['job_id']]
    if j['status']!='waiting_execution':raise WorkflowError('job already attempted; never silently retry')
    validate_job(s,root,j)
    actual=d.get('tool_args')
    expected=json.loads(local(root,j['tool_args_file']).read_text(encoding='utf-8'))
    if actual!=expected or objhash(actual)!=j['tool_args_hash']:raise WorkflowError('actual prompt/images/order differ from compiled job')
    if j['input_images'] and d.get('inspected_images')!=[x['sha256'] for x in j['input_images']]:raise WorkflowError('inspect all actual reference images before calling')
    review=d.get('intent_review',{})
    if not isinstance(review,dict) or review.get('unresolved')!=[] or set(review.get('covered_requirement_ids',[]))!=set(j['coverage']) or len(review.get('observation','').strip())<5:raise WorkflowError('assistant must review intent coverage, contradictory text and actual image roles before execution')
    j.update(status='running',submitted_args=actual,intent_review=review,started_at=now());s['calls_used']+=1
    return {'status':'RUNNING','job_id':j['id'],'tool':'image_gen.imagegen','args':actual,'calls_used':s['calls_used']}

def finish(s,root,d):
    j=s['jobs'][d['job_id']]
    if j['status']!='running':raise WorkflowError('job is not running')
    if d.get('error'):
        j.update(status='failed',error=str(d['error']),finished_at=now());return {'status':'FAILED','job_id':j['id']}
    p=local(root,d['output'])
    with Image.open(p) as im:
        size=list(im.size);mode=im.mode
        if size!=[j['blueprint']['canvas']['width'],j['blueprint']['canvas']['height']]:
            j.update(status='failed',error='actual output dimensions mismatch; no automatic resizing',output_files=bind(root,[d['output']]),finished_at=now())
            return {'status':'FAILED','actual_size':size}
        if j.get('submitted_args',{}).get('transparent_background') and ('A' not in im.getbands() or im.getchannel('A').getextrema()[0]==255):
            j.update(status='failed',error='no genuine transparent pixels',output_files=bind(root,[d['output']]),finished_at=now());return {'status':'FAILED','error':j['error']}
    j.update(status='generated',output=d['output'],output_files=bind(root,[d['output']]),actual_size=size,actual_mode=mode,tool_metadata=d.get('tool_metadata',{}),finished_at=now())
    return {'status':'GENERATED','job_id':j['id'],'output':d['output'],'quality':'unreviewed','backend_model':'not exposed'}


def prepare_composition(s,root,d):
    jid=ident(d.get('id'));baseline=d.get('baseline');source=s['jobs'].get(d.get('source_job'))
    if jid in s['jobs'] or baseline!=s['working_revision'] or not rev_fresh(s,root,baseline,False):raise WorkflowError('composition repair needs a unique id and selected real baseline')
    r=s['revisions'][baseline]
    if not source or source['status']!='generated' or r['job_id']!=source['id'] or not source.get('baseline') or source.get('execution_kind')=='native_composition':raise WorkflowError('choose the actual generation task which produced this local candidate')
    if context(s,root)['status']!='READY' or not approved_blueprint(s,root) or not fresh(root,source['output_files']) or r['rules_hash']!=rules_hash(s):raise WorkflowError('composition source/context stale')
    regions=d.get('application_regions');feather=d.get('feather',0)
    if not regions or not isinstance(feather,int) or not 0<=feather<=200 or not d.get('goal'):raise WorkflowError('composition repair needs explicit application regions, feather and goal')
    w,h=source['blueprint']['canvas']['width'],source['blueprint']['canvas']['height']
    allowed=mask_for_regions(source['editable_regions'],w,h);application=mask_for_regions(regions,w,h)
    if not application.any() or (application&~allowed).any():raise WorkflowError('composition region cannot expand original generation permission')
    restore=source['baseline']
    if r['parent']!=restore or not rev_fresh(s,root,restore,False):raise WorkflowError('restoration base must be the candidate parent with unchanged files')
    folder=root/'production'/jid;folder.mkdir(parents=True,exist_ok=False)
    plan={'goal':d['goal'],'baseline':baseline,'restoration_base':restore,'source_job':source['id'],'application_regions':regions,'feather':feather}
    atomic(folder/'composition_plan.json',plan)
    files=current_inputs(s,root,source['spec']);files.update(r['files']);files.update(s['revisions'][restore]['files']);files.update(source['output_files'])
    j={'id':jid,'kind':'compose-repair','execution_kind':'native_composition','status':'source_ready','goal':d['goal'],'change_request':d['goal'],
       'source_job':source['id'],'baseline':baseline,'restoration_base':restore,'spec':source['spec'],'blueprint':source['blueprint'],'blueprint_id':s['stages']['R2']['id'],
       'requirements':copy.deepcopy(active(s)),'rules_hash':rules_hash(s),'coverage':source['coverage'],'input_files':files,
       'compiled_files':bind(root,[(folder/'composition_plan.json').relative_to(root)]),'implementation':implementation(),
       'editable_regions':source['editable_regions'],'application_regions':regions,'feather':feather,'input_images':[],
       'output':source['output'],'output_files':source['output_files'],'at':now()}
    s['jobs'][jid]=j
    return {'status':'SOURCE_READY','job_id':jid,'image_calls_added':0,'source_job':source['id']}



def prepare_source_edit(s,root,d):
    jid=ident(d.get('id'));baseline=d.get('baseline')
    if jid in s['jobs'] or baseline!=s['working_revision'] or not rev_fresh(s,root,baseline,False):raise WorkflowError('source edit needs a selected unchanged baseline and unique job id')
    if context(s,root)['status']!='READY' or not approved_blueprint(s,root):raise WorkflowError('source edit needs current approved blueprint/intent')
    spec=d.get('spec') or s['stages']['R2']['data']['spec'];p,base=load_project(local(root,spec));approved,aroot=load_project(local(root,s['stages']['R2']['data']['spec']))
    before,broot=load_project(local(root,s['revisions'][baseline]['spec']));pre,_=validate_project(p,base,'production')
    if pre['status']!='PASS' or p['canvas']!=approved['canvas'] or p['canvas']!=before['canvas']:raise WorkflowError('native source edit needs a complete same-size recipe')
    stable=lambda e:{k:v for k,v in e.items() if k not in ('source','edit_authorization')}
    if [stable(e) for e in p['elements']]!=[stable(e) for e in approved['elements']]:raise WorkflowError('native recipe must match approved R2 structure')
    known={e['id']:e for e in before['elements']};changed=[]
    for e in p['elements']:
        old=known.get(e['id'])
        if not old or stable(old)!=stable(e):raise WorkflowError('source edit cannot silently change layout or layer structure')
        if e.get('source') and (not old.get('source') or sha(base/e['source'])!=sha(broot/old['source'])):changed.append(e['id'])
    if not changed or set(changed)!=set(d.get('layer_updates',[])):raise WorkflowError('list exactly the source layers actually replaced')
    regions=p.get('editable_regions',[]);w,h=p['canvas']['width'],p['canvas']['height'];mask=mask_for_regions(regions,w,h)
    if not regions or not mask.any() or (mask&protection_mask(p,base,w,h)).any():raise WorkflowError('source edits need explicit scope and protected-object subregion authorization')
    if not d.get('goal'):raise WorkflowError('native task needs actual user change goal')
    intent=d.get('intent_review',{})
    if intent.get('unresolved')!=[] or set(intent.get('covered_requirement_ids',[]))!={r['id'] for r in active(s)} or len(intent.get('observation','').strip())<5:raise WorkflowError('native changes also require current intent/coverage review')
    folder=root/'production'/jid;folder.mkdir(parents=True,exist_ok=False);atomic(folder/'source_plan.json',d)
    files=current_inputs(s,root,spec);files.update(s['revisions'][baseline]['files'])
    j={'id':jid,'kind':'source-edit','execution_kind':'native_source','status':'source_ready','goal':d['goal'],'change_request':d['goal'],'baseline':baseline,
       'spec':spec,'blueprint':p,'blueprint_id':s['stages']['R2']['id'],'requirements':copy.deepcopy(active(s)),'rules_hash':rules_hash(s),
       'coverage':{r['id']:{'production':r['method'],'check':'req:'+r['id']} for r in active(s)},'input_files':files,'compiled_files':bind(root,[(folder/'source_plan.json').relative_to(root)]),
       'implementation':implementation(),'editable_regions':regions,'output_files':{},'input_images':[],'layer_updates':changed,'intent_review':intent,'at':now()}
    s['jobs'][jid]=j
    return {'status':'SOURCE_READY','job_id':jid,'image_calls_added':0,'layer_updates':changed}

def cancel_job(s,root,d):
    j=s['jobs'][d['job_id']]
    if j['status']!='waiting_execution' or not d.get('reason'):raise WorkflowError('only unattempted queued jobs can be cancelled with a reason')
    j.update(status='cancelled',reason=d['reason'],at=now())
    return {'status':'CANCELLED','image_calls_added':0,'job_id':j['id']}

def action(root,verb,data,expected_seq=None):
    from photocraft import prepare_editor,begin_editor,finish_editor
    functions={'prepare-editor':prepare_editor,'begin-editor':begin_editor,'finish-editor':finish_editor,'prepare-source':prepare_source_edit,'cancel':cancel_job,'prepare-compose':prepare_composition,'prepare':prepare,'begin':begin,'finish':finish}
    def operation(s,r):return functions[verb](s,r,data)
    operation.__name__='production-'+verb
    return transact(root,operation,expected_seq)

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','prepare-compose','prepare-source','begin','finish','cancel','prepare-editor','begin-editor','finish-editor']);a.add_argument('--project',required=True,type=Path);a.add_argument('--input',required=True,type=Path);o=a.parse_args()
    try:print(dump(action(o.project,o.action,json.loads(o.input.read_text(encoding='utf-8')))));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(dump({'status':'BLOCK','error':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
