import importlib.util,json,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import providers

class Transport(unittest.TestCase):
 def check_response(self,code):
  calls=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):
    calls.append(self.path);self.rfile.read(int(self.headers['Content-Length']))
    self.send_response(code)
    if code==302:self.send_header('Location','/must-not-replay')
    self.end_headers();self.wfile.write(b'{}')
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   try:r=providers.post('http://127.0.0.1:'+str(server.server_port)+'/one',{'Content-Type':'application/json'},b'{}',5)
   except ValueError:r={'status_code':302}
   self.assertEqual(len(calls),1);self.assertEqual(r['status_code'],code)
  finally:server.shutdown();server.server_close();thread.join()
 def test_actual_http_429_sends_once(self):self.check_response(429)
 def test_actual_http_500_sends_once(self):self.check_response(500)
 def test_http_redirect_not_replayed(self):self.check_response(302)

class Package(unittest.TestCase):
 def test_each_host_package_has_same_core_and_correct_entrypoint(self):
  repo=Path(__file__).resolve().parents[3];tool=repo/'tools/package_v4.py'
  if not tool.exists():self.skipTest('package builder is a repository tool, not shipped inside skill')
  spec=importlib.util.spec_from_file_location('package_v4_test',tool);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as out:
   result=module.package(Path(__file__).resolve().parents[1],out)
   self.assertEqual(len(result['packages']),4)
   for item in result['packages']:
    with zipfile.ZipFile(Path(out)/item['archive']) as z:
     self.assertIn(item['entrypoint'],z.namelist());self.assertNotIn('README.md',z.namelist())
    self.assertTrue(item['core_match']);self.assertEqual(item['native_host_import'],'NOT_TESTED')
