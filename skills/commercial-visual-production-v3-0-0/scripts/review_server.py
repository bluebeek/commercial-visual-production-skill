"""Local V3 workbench. Generation requests queue for the active assistant; checks really run."""
import argparse,json,mimetypes,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import workflow,production,checks
from _workflow import *

class ReviewServer(ThreadingHTTPServer):
 def __init__(self,address,project):
  super().__init__(address,Handler);self.project=Path(project).resolve();self.operation_lock=threading.Lock();load(self.project)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,status,value,ctype='application/json; charset=utf-8'):
  raw=value if isinstance(value,bytes) else (value if isinstance(value,str) else dump(value)).encode('utf-8')
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; base-uri 'none'");self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  u=urlparse(self.path)
  try:
   if u.path in ('/','/index.html'):return self.send(200,(ROOT/'ui/index.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/app.js':return self.send(200,(ROOT/'ui/app.js').read_bytes(),'application/javascript; charset=utf-8')
   if u.path=='/api/state':
    s=load(self.server.project);out=workflow.summary(self.server.project);out['checks']=s['checks'];out['all_requirements']=s['requirements'];out['all_issues']=s['issues'];out['stage_versions']={k:v['id'] for k,v in s['stages'].items()};out['preview']=s['stages'].get('R2',{}).get('data',{}).get('preview');out['test_only']=s['test_mode'];return self.send(200,out)
   if u.path=='/api/file':
    p=local(self.server.project,parse_qs(u.query).get('path',[''])[0])
    if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.json','.txt','.ora'):raise WorkflowError('unsupported preview type')
    return self.send(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
   if u.path=='/api/export':return self.send(200,load(self.server.project))
   return self.send(404,{'error':'not found'})
  except (ValueError,OSError,KeyError,TypeError) as e:return self.send(400,{'error':str(e)})
 def do_POST(self):
  if urlparse(self.path).path!='/api/action':return self.send(404,{'error':'not found'})
  if self.headers.get('Origin') not in (None,'http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)):return self.send(403,{'error':'cross origin rejected'})
  if 'application/json' not in self.headers.get('Content-Type',''):return self.send(415,{'error':'expected JSON'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=256000:raise WorkflowError('invalid request size')
   body=json.loads(self.rfile.read(n));name=body['action'];d=body.get('data',{});seq=body.get('expected_seq')
   if not isinstance(d,dict):raise WorkflowError('invalid action data')
   with self.server.operation_lock:
    s=load(self.server.project)
    if seq is None or seq!=s['seq']:raise ConflictError('页面版本已过期，请刷新；不会覆盖他人操作')
    if name in ('confirm-blueprint','accept','accept-exception','accept-delivery'):
     # A click records a declared local human decision, not an authenticated signature.
     namepart='ui-decision-'+str(s['seq']+1)+'.json';actor='test' if s['test_mode'] else 'user'
     atomic(self.server.project/'decisions'/namepart,{'action':name,'data':d,'actor':actor,'at':now(),'test_only':s['test_mode']})
     d.update(actor=actor,reason=d.get('reason') or '用户在本地工作台点击 '+name,evidence_files=['decisions/'+namepart])
    if name=='review':
     rid=d['revision'];d.update(actor='test' if s['test_mode'] else 'user',evidence_files=[s['revisions'][rid]['image']])
    if name in ('run-checks','export-delivery','accept-delivery'):
     result=checks.action(self.server.project,{'run-checks':'run','export-delivery':'export','accept-delivery':'accept-delivery'}[name],d,seq)
    elif name=='queue-generation':result=production.action(self.server.project,'prepare',d,seq)
    else:result=workflow.perform(self.server.project,name,d,seq)
   return self.send(200,{'ok':True,'result':result})
  except ConflictError as e:return self.send(409,{'ok':False,'error':str(e)})
  except (ValueError,OSError,KeyError,TypeError) as e:return self.send(400,{'ok':False,'error':str(e)})
def main():
 a=argparse.ArgumentParser();a.add_argument('--project',required=True,type=Path);a.add_argument('--port',type=int,default=8765);o=a.parse_args()
 server=ReviewServer(('127.0.0.1',o.port),o.project);print('http://127.0.0.1:'+str(server.server_port),flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
