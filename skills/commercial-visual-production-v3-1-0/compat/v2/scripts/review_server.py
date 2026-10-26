#!/usr/bin/env python3
"""Local-only review station. Buttons persist decisions, never trigger AI generation."""
import argparse, json, mimetypes, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from review_engine import ReviewError, definitions, load, make_ticket, module_statuses, snapshot, transact, applicable
from _storage import ConflictError

ROOT=Path(__file__).resolve().parents[1]
PREVIEWS={
    'R0':['reference.png','reference.jpg','reference.webp'],
    'R1':['reference_grid.png','reference.png','reference.jpg'],
    'R2':['blueprint_guide.png','mask_protected.png','mask_editable.png'],
    'R3':['layout_preview.png','blueprint_guide.png'],
    'R4':['locked.png','candidate.png','baseline.png'],
    'R5':['difference.png','layout_preview.png','locked.png'],
    'R6':['final.png','final.jpg','layout_preview.png']
}

class ReviewServer(ThreadingHTTPServer):
    def __init__(self,addr,handler,project,mode='full'):
        super().__init__(addr,handler);self.project=project.resolve();self.lock=threading.Lock()
        load(self.project,create=True,mode=mode)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send(self,status,content,ctype='application/json; charset=utf-8',filename=None):
        raw=content.encode('utf-8') if isinstance(content,str) else content
        self.send_response(status);self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/app.js':
            return self.send(200,(ROOT/'ui'/'app.js').read_bytes(),'application/javascript; charset=utf-8')
        if u.path in ('/','/index.html'):
            return self.send(200,(ROOT/'ui'/'index.html').read_bytes(),'text/html; charset=utf-8')
        if u.path=='/api/state':
            with self.server.lock:
                s=snapshot(self.server.project)
            previews={stage:[name for name in names if (self.server.project/'artifacts'/name).is_file() and (self.server.project/'artifacts'/name).resolve().is_relative_to(self.server.project)] for stage,names in PREVIEWS.items()}
            d,_,checks=definitions();return self.send(200,json.dumps({'state':{k:v for k,v in s.items() if not k.startswith('_')},'definitions':d,'stages':module_statuses(s),'previews':previews,'applicable_checks':[c for c in checks if applicable(s,c)]},ensure_ascii=False))
        if u.path=='/api/export':
            with self.server.lock:s=snapshot(self.server.project)
            return self.send(200,json.dumps({k:v for k,v in s.items() if not k.startswith('_')},ensure_ascii=False,indent=2),'application/json; charset=utf-8','review_state.json')
        if u.path=='/api/ticket':
            q=parse_qs(u.query); cid=q.get('check_id',[None])[0];sid=q.get('stage',[None])[0]
            with self.server.lock:s=snapshot(self.server.project)
            _,mods,checks=definitions()
            if cid and cid not in checks:return self.send(400,json.dumps({'error':'invalid check_id'}))
            if sid and sid not in [m['id'] for m in mods]:return self.send(400,json.dumps({'error':'invalid stage'}))
            return self.send(200,make_ticket(s,check_id=cid,stage=sid),'text/markdown; charset=utf-8',f'change-ticket-{cid or sid or "all"}.md')
        if u.path=='/api/file':
            q=parse_qs(u.query);name=q.get('path',[''])[0]
            file=(self.server.project/name).resolve()
            if not file.is_relative_to(self.server.project) or file.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not file.is_file():return self.send(404,b'Not found','text/plain')
            return self.send(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        if u.path=='/api/preview':
            q=parse_qs(u.query);stage=q.get('stage',[''])[0];name=q.get('name',[''])[0]
            if name not in PREVIEWS.get(stage,[]):return self.send(404,b'Not found','text/plain')
            file=self.server.project/'artifacts'/name
            if not file.is_file():return self.send(404,b'Not found','text/plain')
            return self.send(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        self.send(404,b'Not found','text/plain')
    def do_POST(self):
        path=urlparse(self.path).path
        if path!='/api/action':return self.send(404,b'Not found','text/plain')
        origin=self.headers.get('Origin')
        allowed=('http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port))
        if origin and origin not in allowed:return self.send(403,json.dumps({'error':'cross-origin request rejected'}))
        if 'application/json' not in self.headers.get('Content-Type',''):
            return self.send(415,json.dumps({'error':'expected application/json'}))
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<1 or n>256000:return self.send(413,json.dumps({'error':'invalid request size'}))
            payload=json.loads(self.rfile.read(n).decode('utf-8'))
            if not isinstance(payload,dict):raise ReviewError('expected JSON object')
            action=payload.get('action');data=payload.get('data',{})
            if not isinstance(data,dict):raise ReviewError('invalid data')
            with self.server.lock:
                result=transact(self.server.project,action,data,payload.get('expected_seq'))
            return self.send(200,json.dumps({'ok':True,'result':result},ensure_ascii=False))
        except ConflictError as e:
            return self.send(409,json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))
        except (ReviewError,ValueError,TypeError,KeyError,OSError) as e:
            return self.send(400,json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--project',required=True,type=Path);a.add_argument('--port',type=int,default=8765);a.add_argument('--mode',choices=['full','local-edit','delivery'],default='full');a.add_argument('--open',action='store_true',help='Open local browser on startup')
    opt=a.parse_args()
    server=ReviewServer(('127.0.0.1',opt.port),Handler,opt.project,opt.mode)
    print(f'Visual Review Desk: http://127.0.0.1:{server.server_port}/',flush=True)
    print('Review state:',server.project/'review_state.json',flush=True)
    if opt.open:threading.Timer(0.5,lambda:webbrowser.open(f'http://127.0.0.1:{server.server_port}/')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
