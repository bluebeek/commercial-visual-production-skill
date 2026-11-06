"""Provider-neutral requests bound to V4 state, latest evidence and shared budget."""
import copy, hashlib, io, json, os
from datetime import datetime
from pathlib import Path
from PIL import Image
from _workflow import WorkflowError, atomic, bind, fresh, load, local, now, objhash, sha, transact
import model_catalog, budget, providers

def validate_capabilities(selection,kind,size,alpha,quality,inputs):
    cap=selection['capabilities'];w,h=size
    if not cap.get('contract') or not cap.get('edit' if inputs else 'generate'):raise WorkflowError('latest model lacks task capability')
    if alpha and not cap.get('alpha'):raise WorkflowError('latest model does not have a verified alpha contract')
    if quality not in cap['quality'] or inputs>cap['max_inputs']:raise WorkflowError('unsupported quality or reference count')
    if cap.get('sizes'):
        if [w,h] not in cap['sizes']:raise WorkflowError('size not supported by current provider contract')
    elif (max(w,h)>cap['max_edge'] or w%cap['multiple'] or h%cap['multiple'] or
          not cap['min_pixels']<=w*h<=cap['max_pixels'] or max(w,h)/min(w,h)>cap['max_aspect']):
        raise WorkflowError('dimensions unsupported; revise R2 explicitly, never resize silently')

def prepare(s,root,d,j,prompt):
    provider=d.get('provider',s.get('generation_provider','openai'))
    if provider not in ('openai','google'):raise WorkflowError('latest requires an identifiable official model; built-in is NOT_VERIFIABLE')
    catalog=local(root,d.get('catalog','model_catalog.json'))
    selection=model_catalog.resolve(catalog,provider,d.get('model_profile','quality'),fixture_allowed=s['test_mode'])
    size=[j['blueprint']['canvas']['width'],j['blueprint']['canvas']['height']]
    quality=d.get('quality','medium' if provider=='openai' else 'standard')
    alpha=bool(d.get('transparent_background',False))
    validate_capabilities(selection,j['kind'],size,alpha,quality,len(j['input_images']))
    request={'schema':'cvisual.generation.request.v1','project_uuid':s['project_uuid'],'job_id':j['id'],
             'model_policy':'latest','provider':provider,'selection':selection,'prompt':prompt,'kind':j['kind'],
             'baseline':j['baseline'],'blueprint_id':j['blueprint_id'],'rules_hash':j['rules_hash'],
             'input_assets':copy.deepcopy(j['input_images']),'output':{'size':size,'alpha':alpha,'quality':quality,'format':'png'},
             'maximum_cost_usd':d.get('maximum_cost_usd'), 'editable_regions':j['editable_regions']}
    if not s['test_mode']:
        quote_path=local(root,d.get('cost_quote'))
        quote=json.loads(quote_path.read_text(encoding='utf-8'))
        expected={'model':selection['model'],'size':size,'alpha':alpha,'quality':quality,
                  'input_hashes':[x['sha256'] for x in j['input_images']]}
        if any(quote.get(k)!=v for k,v in expected.items()) or budget.money(quote.get('maximum_usd'))!=budget.money(d.get('maximum_cost_usd')):
            raise WorkflowError('conservative cost quote does not match this request')
        if quote.get('kind')!='operator_conservative_bound' or len(quote.get('basis',''))<20 or not quote.get('pricing_source','').startswith(('https://developers.openai.com/','https://ai.google.dev/','https://aistudio.google.com/')):
            raise WorkflowError('documented cost basis and official pricing source required')
        request['cost_quote_files']=bind(root,[quote_path.relative_to(root)])
    folder=root/'production'/j['id'];atomic(folder/'request.json',request)
    # A portable manifest is separate from the transient HTTP body and local absolute paths.
    args={'provider':provider,'model':selection['model'],'request_hash':objhash(request)}
    atomic(folder/'tool_args.json',args)
    catalog_data=json.loads(catalog.read_text(encoding='utf-8'));source=local(root,(catalog.parent/catalog_data['source_file']).relative_to(root))
    snapshot=folder/'model_catalog.json';snapshot_source=folder/'model_catalog.source.md'
    snapshot_source.write_bytes(source.read_bytes());catalog_data['source_file']=snapshot_source.name
    atomic(snapshot,catalog_data)
    selection=model_catalog.resolve(snapshot,provider,d.get('model_profile','quality'),fixture_allowed=s['test_mode'])
    request['selection']=selection;atomic(folder/'request.json',request)
    args['request_hash']=objhash(request);atomic(folder/'tool_args.json',args)
    j.update(generation_contract='cvisual.generation.request.v1',execution_kind='official_api',selection=selection,
             request_file=(folder/'request.json').relative_to(root).as_posix(),catalog_file=snapshot.relative_to(root).as_posix(),
             tool_args_hash=objhash(args))
    j['compiled_files'].update(bind(root,[j['request_file'],j['tool_args_file'],snapshot.relative_to(root),snapshot_source.relative_to(root)]))
    j['compiled_files'].update(request.get('cost_quote_files',{}))
    return request

def validate(s,root,j,require_fresh=True):
    request=json.loads(local(root,j['request_file']).read_text(encoding='utf-8'))
    clock=None if require_fresh else datetime.fromisoformat(j['selection']['checked_at'])
    selection=model_catalog.resolve(local(root,j['catalog_file']),j['selection']['provider'],j['selection']['profile'],clock=clock,fixture_allowed=s['test_mode'])
    if selection!=j['selection'] or request['selection']!=selection:raise WorkflowError('latest selection changed; recompile')
    if request['project_uuid']!=s['project_uuid'] or request['job_id']!=j['id'] or request['rules_hash']!=j['rules_hash'] or request['blueprint_id']!=j['blueprint_id']:
        raise WorkflowError('request belongs to another project/intent')
    if request['input_assets']!=j['input_images'] or request['baseline']!=j['baseline'] or request['editable_regions']!=j['editable_regions']:
        raise WorkflowError('request assets/baseline/scope mismatch')
    validate_capabilities(selection,j['kind'],request['output']['size'],request['output']['alpha'],request['output']['quality'],len(request['input_assets']))
    return request

def begin(s,root,j):
    request=validate(s,root,j)
    j['attempt_key']=budget.reserve(s,root,j['id'],request['maximum_cost_usd'],j['selection'])
    return {'status':'RUNNING','job_id':j['id'],'execution_kind':'official_api','request_file':j['request_file'],
            'model':j['selection']['model'],'calls_used':s['calls_used']}

def execute(project,job_id,intent_review,inspected_images,transport=None,fetcher=None):
    """Re-fetch official notes BEFORE reservation. A network call is never retried here."""
    import production
    root=Path(project).resolve();s=load(root);j=s['jobs'][job_id]
    if j.get('execution_kind')!='official_api' or j['status']!='waiting_execution':raise WorkflowError('only unattempted official API tasks execute')
    if s['test_mode'] and transport is None:raise WorkflowError('test projects cannot call a real image service')
    if not s['test_mode'] and transport is not None:raise WorkflowError('simulated transport forbidden in production')
    request=validate(s,root,j)
    if not s['test_mode']:
        provider=request['provider'];key=os.environ.get(providers.ENV_KEYS[provider])
        if not key:raise WorkflowError('provider credential not configured; no image call made')
        # Refresh in a separate location so source snapshots of older jobs remain immutable.
        latest_path=root/'production'/job_id/'preflight-catalog.json'
        model_catalog.refresh(provider,latest_path,fetcher or model_catalog.fetch)
        latest=model_catalog.resolve(latest_path,provider,request['selection']['profile'])
        if (latest['model'],latest['released_at'],latest['capabilities'])!=(j['selection']['model'],j['selection']['released_at'],j['selection']['capabilities']):
            raise WorkflowError('new official release/capability detected; prepare a new task')
    else:key='fixture-not-a-secret'
    if any((root/'production'/job_id/n).exists() for n in ('raw.png','receipt.json')):
        raise WorkflowError('execution output location is not new; reconcile existing files first')
    url,ctype,body=providers.compile_request(request,root)
    args=json.loads(local(root,j['tool_args_file']).read_text(encoding='utf-8'))
    production.action(root,'begin',{'job_id':job_id,'tool_args':args,'intent_review':intent_review,'inspected_images':inspected_images})
    s=load(root);j=s['jobs'][job_id]
    budget.mark(s,root,j['attempt_key'],'attempted')
    headers={'Content-Type':ctype}
    headers['Authorization' if request['provider']=='openai' else 'x-goog-api-key']=('Bearer '+key) if request['provider']=='openai' else key
    try:
        response=(transport or providers.post)(url,headers,body)
    except Exception:
        # A timeout/transport failure does not establish whether the provider accepted it.
        budget.mark(s,root,j['attempt_key'],'unknown')
        def unknown(state,r):
            state['jobs'][job_id].update(status='result_unknown',error='transport outcome UNKNOWN; reconcile before retry',finished_at=now())
            return {'status':'UNKNOWN','job_id':job_id,'attempt_key':j['attempt_key']}
        return transact(root,unknown)
    status=response.get('status_code',0)
    if not 200<=status<300:
        outcome='unknown' if status>=500 or status in (0,408) else 'failed'
        budget.mark(s,root,j['attempt_key'],outcome,response.get('request_id'))
        if outcome=='unknown':
            def unknown_http(state,r):
                state['jobs'][job_id].update(status='result_unknown',error='provider HTTP '+str(status)+'; processing outcome UNKNOWN',finished_at=now())
                return {'status':'UNKNOWN','http_status':status,'job_id':job_id}
            return transact(root,unknown_http)
        return production.action(root,'finish',{'job_id':job_id,'error':'provider HTTP '+str(status)})
    budget.mark(s,root,j['attempt_key'],'returned',response.get('request_id'))
    folder=root/'production'/job_id
    try:
        blob,meta=providers.decode(request['provider'],response)
        with Image.open(io.BytesIO(blob)) as im:
            im.load()
            if im.format!='PNG':raise WorkflowError('provider did not return PNG')
        output=folder/'raw.png';output.write_bytes(blob)
        receipt={'schema':'cvisual.generation.receipt.v1','request_hash':objhash(request),'output_sha256':sha(output),
                 'requested_model':request['selection']['model'],'fixture':s['test_mode'],'http_status':status,**meta}
        atomic(folder/'receipt.json',receipt)
        return production.action(root,'finish',{'job_id':job_id,'output':output.relative_to(root).as_posix(),
                                                'tool_metadata':receipt,'receipt_file':(folder/'receipt.json').relative_to(root).as_posix()})
    except (ValueError,OSError,KeyError,TypeError):
        return production.action(root,'finish',{'job_id':job_id,'error':'provider response received but image/receipt validation failed'})

def validate_receipt(s,root,j,data):
    path=local(root,data['receipt_file']);receipt=json.loads(path.read_text(encoding='utf-8'))
    request=validate(s,root,j,require_fresh=False)
    b=budget.read(budget.owned(s,root));attempt=b['attempts'][j['attempt_key']]
    if attempt['status']!='returned':raise WorkflowError('provider outcome not confirmed returned')
    if receipt.get('fixture')!=s['test_mode'] or receipt.get('schema')!='cvisual.generation.receipt.v1':raise WorkflowError('wrong receipt source')
    if receipt.get('request_hash')!=objhash(request) or receipt.get('output_sha256')!=sha(local(root,data['output'])) or receipt.get('requested_model')!=j['selection']['model']:
        raise WorkflowError('receipt/output/model mismatch')
    reported=receipt.get('reported_model','NOT_EXPOSED');requested=j['selection']['model']
    if reported!='NOT_EXPOSED' and reported!=requested and not reported.startswith(requested+'-20'):
        raise WorkflowError('provider reported a different model; do not adopt')
    if receipt!=data.get('tool_metadata'):raise WorkflowError('receipt metadata mismatch')
    j['receipt_file']=path.relative_to(root).as_posix();j['receipt_files']=bind(root,[j['receipt_file']])

def recover(project,job_id,response_file,evidence_file,failed=False):
    """Reconcile one interrupted attempt from retained provider evidence; no POST."""
    import production
    root=Path(project).resolve();s=load(root);j=s['jobs'][job_id]
    if j.get('execution_kind')!='official_api' or j['status'] not in ('running','result_unknown'):
        raise WorkflowError('only an interrupted official API job can be recovered')
    evidence=local(root,evidence_file)
    response_path=None if failed else local(root,response_file)
    if not evidence.stat().st_size:raise WorkflowError('actual provider outcome evidence required')
    budget.reconcile(root,j['attempt_key'],'failed' if failed else 'returned',evidence)
    def restore(state,r):
        state['jobs'][job_id]['status']='running';state['jobs'][job_id]['recovery_files']=bind(r,[evidence_file]+([] if failed else [response_file]))
        return {'status':'RECOVERING_NO_NETWORK'}
    transact(root,restore)
    if failed:return production.action(root,'finish',{'job_id':job_id,'error':'provider failure reconciled from retained evidence'})
    request=validate(load(root),root,j,require_fresh=False)
    try:
        response=json.loads(response_path.read_text(encoding='utf-8'))
        if not 200<=response.get('status_code',0)<300:raise WorkflowError('recovery response not successful')
        blob,meta=providers.decode(request['provider'],response)
        with Image.open(io.BytesIO(blob)) as im:
            im.load()
            if im.format!='PNG':raise WorkflowError('recovered image is not PNG')
        folder=root/'production'/job_id;out=folder/'raw.png'
        if out.exists() and out.read_bytes()!=blob:raise WorkflowError('existing raw output differs; do not overwrite')
        out.write_bytes(blob)
        receipt={'schema':'cvisual.generation.receipt.v1','request_hash':objhash(request),'output_sha256':sha(out),
                 'requested_model':request['selection']['model'],'fixture':s['test_mode'],'http_status':response['status_code'],**meta}
        rp=folder/'receipt.json'
        if rp.exists() and json.loads(rp.read_text(encoding='utf-8'))!=receipt:raise WorkflowError('existing receipt differs')
        atomic(rp,receipt)
        return production.action(root,'finish',{'job_id':job_id,'output':out.relative_to(root).as_posix(),'tool_metadata':receipt,'receipt_file':rp.relative_to(root).as_posix()})
    except (ValueError,OSError,KeyError,TypeError):
        return production.action(root,'finish',{'job_id':job_id,'error':'recovery image/evidence invalid; no candidate adopted'})
