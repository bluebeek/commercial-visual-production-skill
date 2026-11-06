"""Official image HTTP contracts. One POST, no redirects or automatic retries."""
import base64, json, mimetypes, urllib.request, urllib.error, uuid
from pathlib import Path
from _workflow import WorkflowError, local

ENDPOINTS={'openai':'https://api.openai.com/v1/images/', 'google':'https://generativelanguage.googleapis.com/v1beta/interactions'}
ENV_KEYS={'openai':'OPENAI_API_KEY','google':'GEMINI_API_KEY'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise WorkflowError('API redirect refused; request not replayed')

def post(url,headers,body,timeout=300):
    request=urllib.request.Request(url,body,headers,method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout) as r:
            data=r.read(80_000_001)
            if len(data)>80_000_000:raise WorkflowError('provider response exceeds size limit')
            return {'status_code':r.status,'request_id':r.headers.get('x-request-id'), 'body':json.loads(data)}
    except urllib.error.HTTPError as e:
        # Deliberately do not persist raw error bodies or authorization headers.
        return {'status_code':e.code,'request_id':e.headers.get('x-request-id'),'body':{}}

def multipart(fields,images):
    boundary='cvisual-'+uuid.uuid4().hex;parts=[]
    for name,value in fields.items():
        parts.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"\r\n\r\n'+str(value)+'\r\n').encode())
    for index,(mime,data) in enumerate(images):
        ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime]
        parts.extend([('--'+boundary+'\r\nContent-Disposition: form-data; name="image[]"; filename="reference-'+str(index)+'.'+ext+'"\r\nContent-Type: '+mime+'\r\n\r\n').encode(),data,b'\r\n'])
    parts.append(('--'+boundary+'--\r\n').encode());return b''.join(parts),'multipart/form-data; boundary='+boundary

def compile_request(request,root):
    provider=request['provider'];cap=request['selection']['capabilities'];w,h=request['output']['size']
    images=[]
    for item in request['input_assets']:
        p=local(root,item['path']);mime=mimetypes.guess_type(p.name)[0]
        if mime not in ('image/png','image/jpeg','image/webp') or p.stat().st_size>=50_000_000:raise WorkflowError('unsupported reference format or file size')
        images.append((mime,p.read_bytes()))
    if provider=='openai':
        fields={'model':request['selection']['model'],'prompt':request['prompt'],'size':f'{w}x{h}',
                'quality':request['output']['quality'],'output_format':'png','background':'transparent' if request['output']['alpha'] else 'opaque','n':1}
        if images:body,ctype=multipart(fields,images);url=ENDPOINTS['openai']+'edits'
        else:body=json.dumps(fields,ensure_ascii=False).encode();ctype='application/json';url=ENDPOINTS['openai']+'generations'
    elif provider=='google':
        inputs=[{'type':'text','text':request['prompt']}]+[{'type':'image','mime_type':m,'data':base64.b64encode(b).decode()} for m,b in images]
        args={'model':request['selection']['model'],'input':inputs,
              'response_format':{'type':'image','aspect_ratio':cap['aspect_ratio'],'image_size':cap['image_size']}}
        body=json.dumps(args,ensure_ascii=False).encode();ctype='application/json';url=ENDPOINTS['google']
    else:raise WorkflowError('no official adapter for provider')
    return url,ctype,body

def decode(provider,response):
    data=response['body']
    if provider=='openai':
        items=data.get('data',[])
        if len(items)!=1 or not items[0].get('b64_json'):raise WorkflowError('expected one final base64 image')
        encoded=items[0]['b64_json']
    else:
        # Select final model output only. Never adopt a reasoning/preview image.
        images=[]
        if data.get('output_image'):images=[data['output_image']]
        else:
            for step in data.get('steps',[]):
                if step.get('type')=='model_output':images.extend(c for c in step.get('content',[]) if c.get('type')=='image')
            if not images:images=[c for c in data.get('outputs',[]) if c.get('type')=='image']
        if len(images)!=1 or not images[0].get('data'):raise WorkflowError('expected one final Google image')
        encoded=images[0]['data']
    try:blob=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError):raise WorkflowError('invalid image encoding')
    if not blob or len(blob)>50_000_000:raise WorkflowError('invalid output size')
    return blob,{'reported_model':data.get('model') or data.get('model_version') or 'NOT_EXPOSED',
                 'request_id':response.get('request_id') or data.get('id'),'usage':data.get('usage') or 'NOT_EXPOSED'}
