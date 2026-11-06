"""Resolve latest image releases from official dated notes; never generate an image."""
import argparse, hashlib, json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from _workflow import WorkflowError, atomic, objhash

SOURCES = {
    'openai': 'https://developers.openai.com/api/docs/changelog.md',
    'google': 'https://ai.google.dev/gemini-api/docs/changelog',
}
HOSTS = {'developers.openai.com', 'ai.google.dev', 'aistudio.google.com'}
MONTHS = {m:i for i,m in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}
MODEL_RE = re.compile(r'\b(?:gpt-image-\d+(?:\.\d+)*-(?:sunburst|flare)|gemini-(?:nano-banana-[\d.]+|[\d.]+-(?:flash(?:-lite)?|pro)-image))\b')

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme!='https' or urlsplit(newurl).hostname not in HOSTS:
            raise WorkflowError('documentation redirected outside official hosts')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url):
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in HOSTS:
        raise WorkflowError('only official documentation may resolve latest models')
    req=urllib.request.Request(url,headers={'Accept':'text/markdown','User-Agent':'cvisual-v4-catalog/1'})
    with urllib.request.build_opener(OfficialRedirect()).open(req,timeout=20) as r:
        data=r.read(4_000_001)
    if len(data)>4_000_000:raise WorkflowError('documentation exceeds size limit')
    return data.decode('utf-8')

def releases(provider, text):
    """Only dated release entries qualify, not a numeric/lexical model-name sort."""
    rows=[]; year=None; day=None; block=[]
    def flush():
        content='\n'.join(block)
        if day:
            models=set()
            for paragraph in re.split(r'\n\s*\n',content):
                if re.search(r'\breleased?\b|\blaunch(?:ed)?\b|\bintroducing\b|generally available',paragraph,re.I) and not re.search(r'deprecat|shutdown',paragraph,re.I):
                    launch=re.split(r'\b(?:an update to|successor to|replaces|compared (?:with|to)|migration from)\b',paragraph,flags=re.I)[0]
                    models.update(MODEL_RE.findall(launch))
            for model in sorted(models):
                if model.startswith('gpt-')==(provider=='openai'):
                    rows.append({'id':model,'released_at':day})
    for line in text.splitlines():
        month=re.match(r'^##\s+([A-Za-z]+),\s+(\d{4})\s*$',line)
        full=re.match(r'^##\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\b',line)
        short=re.match(r'^###\s+([A-Za-z]{3})\s+(\d{1,2})\s*$',line)
        if month:
            flush();block=[];day=None;year=int(month[2]);continue
        if full or (short and year):
            flush();block=[];m=(full or short)
            y=int(m[3]) if full else year
            day=datetime(y,MONTHS[m[1][:3]],int(m[2]),tzinfo=timezone.utc).date().isoformat();continue
        block.append(line)
    flush()
    if not rows:raise WorkflowError('no dated image release found; latest is UNKNOWN')
    latest=max(x['released_at'] for x in rows)
    return [x for x in rows if x['released_at']==latest]

def capabilities(provider, model):
    # New model families need an explicit adapter review, never inherit parameters silently.
    if provider=='openai' and re.fullmatch(r'gpt-image-2\.6-(sunburst|flare)',model):
        return {'contract':'openai-images-raster-v1','generate':True,'edit':True,'alpha':True,
                'quality':['low','medium','high','xhigh','max'],'max_inputs':16,
                'max_edge':3840,'min_pixels':655360,'max_pixels':8294400,'multiple':16,'max_aspect':3}
    if provider=='google' and model=='gemini-nano-banana-2.1':
        return {'contract':'google-interactions-raster-v1','generate':True,'edit':True,'alpha':False,
                'quality':['standard'],'max_inputs':14,'sizes':[[1024,1024]],'aspect_ratio':'1:1','image_size':'1K'}
    return {'contract':None,'unverified_reason':'latest release discovered; adapter capabilities require review'}

def refresh(provider, out, fetcher=fetch, clock=None):
    if provider not in SOURCES:raise WorkflowError('unsupported image provider')
    text=fetcher(SOURCES[provider]); entries=releases(provider,text)
    when=clock or datetime.now(timezone.utc)
    if any(x['released_at']>when.date().isoformat() for x in entries):raise WorkflowError('future release date; check clock/source')
    out=Path(out);source=out.with_suffix('.source.md')
    source.parent.mkdir(parents=True,exist_ok=True);source.write_text(text,encoding='utf-8')
    data={'schema':'cvisual.catalog.v1','provider':provider,'checked_at':when.isoformat(),
          'source_url':SOURCES[provider],'source_file':source.name,
          'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'models':[{**x,'capabilities':capabilities(provider,x['id'])} for x in entries]}
    atomic(out,data);return data

def resolve(path, provider, profile='quality', clock=None, fixture_allowed=False):
    p=Path(path);d=json.loads(p.read_text(encoding='utf-8'))
    if d.get('schema')!='cvisual.catalog.v1' or d.get('provider')!=provider:raise WorkflowError('wrong model catalog')
    if d.get('fixture') and not fixture_allowed:raise WorkflowError('simulated catalog cannot authorize production')
    if d.get('source_url')!=SOURCES.get(provider):raise WorkflowError('unknown catalog source')
    src=(p.parent/d['source_file']).resolve()
    if not src.is_relative_to(p.parent.resolve()) or hashlib.sha256(src.read_bytes()).hexdigest()!=d['source_sha256']:
        raise WorkflowError('catalog source changed')
    when=clock or datetime.now(timezone.utc)
    age=(when-datetime.fromisoformat(d['checked_at'])).total_seconds()
    if not 0<=age<=1800:raise WorkflowError('latest catalog expired; refresh official notes')
    candidates=releases(provider,src.read_text(encoding='utf-8'))
    if [(x['id'],x['released_at']) for x in candidates]!=[(x['id'],x['released_at']) for x in d['models']]:
        raise WorkflowError('catalog differs from dated source')
    if profile not in ('quality','speed'):raise WorkflowError('unknown model profile')
    models=d['models'];suffix='sunburst' if profile=='quality' else 'flare'
    chosen=next((x for x in models if x['id'].endswith(suffix)),None) if provider=='openai' else (models[0] if len(models)==1 else None)
    if not chosen:raise WorkflowError('latest model choice ambiguous or unavailable; no old-generation fallback')
    cap=capabilities(provider,chosen['id'])
    if chosen.get('capabilities')!=cap or not cap.get('contract'):raise WorkflowError('latest model adapter not verified')
    return {'policy':'latest','provider':provider,'profile':profile,'model':chosen['id'],
            'released_at':chosen['released_at'],'checked_at':d['checked_at'],'capabilities':cap,
            'catalog_hash':objhash(d),'source_url':d['source_url'],'fixture':bool(d.get('fixture'))}

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=['refresh','resolve']);a.add_argument('--provider',choices=list(SOURCES),required=True);a.add_argument('--catalog',type=Path,required=True);a.add_argument('--profile',default='quality');o=a.parse_args()
    try:
        r=refresh(o.provider,o.catalog) if o.action=='refresh' else resolve(o.catalog,o.provider,o.profile)
        print(json.dumps(r,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError) as e:print(json.dumps({'status':'BLOCK','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
