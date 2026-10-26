import importlib.util, json, sys, tempfile, threading, unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import review_engine as e
import review_server as web
from PIL import Image
from _evidence import save_report

class ReviewWorkBenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.project=Path(self.tmp.name)
        self.state=e.load(self.project,create=True,name='test-project')
        self.defs,self.mods,self.checks=e.definitions()
        (self.project/'evidence.txt').write_text('test fixture only',encoding='utf-8')
        Image.new('RGB',(32,32),'blue').save(self.project/'candidate.png')
        e.apply(self.state,self.project,'revision',{'revision':'v1','evidence_files':['candidate.png']})
    def tearDown(self):self.tmp.cleanup()
    def save(self):e.write_state(self.project,self.state)
    def change(self,action,**params):
        if action in ('approve','resolve'):params.setdefault('evidence_files',['evidence.txt','candidate.png'])
        return e.apply(self.state,self.project,action,params)
    def test_all_modules_have_reviewable_checks_and_dependencies(self):
        self.assertEqual(len(self.mods),7)
        self.assertEqual(len(self.checks),31)
        self.assertTrue(all(c.get('evidence') for c in self.checks.values()))
        self.assertTrue(all(x in self.checks for c in self.checks.values() for x in c.get('affects',[])))
    def test_single_component_feedback_only_invalidates_affected(self):
        for cid in ['R1.typography','R1.palette','R2.bounds','R3.type_plan','R5.fidelity','R3.real_assets']:
            self.change('approve',check_id=cid,evidence='有基准文件与人工审查证据')
        self.change('reject',check_id='R1.typography',issue='标题字形与参考的宽度比例差距明显，请修正文字框。',severity='P1')
        self.assertEqual(self.state['checks']['R1.typography']['status'],'rejected')
        for cid in ['R2.bounds','R3.type_plan','R5.fidelity']:
            self.assertEqual(self.state['checks'][cid]['status'],'stale',cid)
        self.assertEqual(self.state['checks']['R1.palette']['status'],'approved')
        self.assertEqual(self.state['checks']['R3.real_assets']['status'],'approved')
        ticket=e.make_ticket(self.state,check_id='R1.typography')
        self.assertIn('标题字形',ticket)
        self.assertIn('R3.type_plan',ticket)
        self.assertNotIn('R3.real_assets',ticket)
    def test_idempotent_confirmation_does_not_invalidate_other_checks(self):
        self.change('approve',check_id='R1.typography',evidence='字体排版坐标比对已经完成')
        self.change('approve',check_id='R2.bounds',evidence='结构蓝图位置审查完成')
        self.change('approve',check_id='R1.typography',evidence='字体排版坐标比对已经完成')
        self.assertEqual(self.state['checks']['R2.bounds']['status'],'approved')
        self.change('approve',check_id='R1.typography',evidence='新修复版标题框的位置对照证据')
        self.assertEqual(self.state['checks']['R2.bounds']['status'],'stale')

    def test_problem_must_be_fixed_version_before_reapproval(self):
        self.change('reject',check_id='R1.whitespace',issue='标题右侧留白不足，须整体扩大空白区域。',severity='P1')
        with self.assertRaises(e.ReviewError):self.change('approve',check_id='R1.whitespace',evidence='新图片对照已核对')
        iid=self.state['issues'][0]['id']
        with self.assertRaises(e.ReviewError):self.change('resolve',issue_id=iid,resolution='已完成修复对比检查')
        self.change('resolve',issue_id=iid,fixed_revision='V3.2',resolution='已修复标题右侧留白，并提交新的版面截图')
        self.assertEqual(self.state['checks']['R1.whitespace']['status'],'pending')
        self.change('approve',check_id='R1.whitespace',evidence='V3.2并列参考对照截图')
        self.assertEqual(e.open_issues(self.state),[])
        self.assertEqual(self.state['checks']['R1.whitespace']['status'],'approved')
    def test_stage_gate_requires_all_signoffs_and_auto_reports(self):
        with self.assertRaises(e.ReviewError):self.change('signoff',stage='R1')
        for item in self.mods[0]['checks']:
            self.change('approve',check_id=item['id'],evidence='已检查真实素材及项目证据')
        self.change('signoff',stage='R0')
        with self.assertRaises(e.ReviewError):self.change('signoff',stage='R1')
        for item in self.mods[1]['checks']:
            self.change('approve',check_id=item['id'],evidence='按参考网格检查完成')
        self.change('signoff',stage='R1')
        self.assertIn('R1',self.state['signoffs'])
        self.change('reject',check_id='R1.typography',issue='字体设计不合参考。')
        self.assertNotIn('R1',self.state['signoffs'])
        self.assertIn('R0',self.state['signoffs'])
        with self.assertRaises(e.ReviewError):self.change('signoff',stage='R2')
    def test_auto_report_requires_actual_file_and_fresh_sha(self):
        with self.assertRaises(e.ReviewError):self.change('approve',check_id='R2.preflight',evidence='程序检查结果文件')
        reports=self.project/'artifacts';reports.mkdir()
        file=reports/'preflight.json';file.write_text(json.dumps({'status':'PASS'}),encoding='utf8')
        self.change('inspect')
        with self.assertRaises(e.ReviewError):self.change('approve',check_id='R2.preflight',evidence='minimal JSON is not evidence')
        (self.project/'blueprint.json').write_text('{}',encoding='utf-8')
        for name in ['guide.png','preview.png','edit.png','protected.png']:Image.new('RGB',(32,32),'blue').save(reports/name)
        save_report(file,'preflight',{'status':'PASS'},{'blueprint':self.project/'blueprint.json'},dict(zip(['guide','preview','editable_mask','protected_mask'],[reports/n for n in ['guide.png','preview.png','edit.png','protected.png']])))
        self.change('inspect');self.change('approve',check_id='R2.preflight',evidence='artifacts/preflight.json sha256')
        file.write_text(json.dumps({'status':'BLOCK','errors':['overlap']}),encoding='utf8')
        with self.assertRaises(e.ReviewError):e.require_auto(self.state,self.project,'R2.preflight',self.checks['R2.preflight'])
        self.change('inspect')
        self.assertEqual(self.state['checks']['R2.preflight']['status'],'stale')
    def test_na_only_for_supported_checks_with_reason(self):
        with self.assertRaises(e.ReviewError):self.change('na',check_id='R2.preflight',issue='无需审查')
        with self.assertRaises(e.ReviewError):self.change('na',check_id='R4.lock',issue='')
        self.change('na',check_id='R4.lock',issue='本次为新构图且无基准修图，不涉及局部硬锁')
        self.assertEqual(self.state['checks']['R4.lock']['status'],'na')
    def test_review_server_http_buttons_api(self):
        server=web.ReviewServer(('127.0.0.1',0),web.Handler,self.project)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}'
            page=urlopen(url+'/').read().decode('utf8');self.assertIn('商业视觉',page);self.assertIn('/app.js',page)
            script=urlopen(url+'/app.js').read().decode('utf8');self.assertIn('data-action',script)
            state=json.loads(urlopen(url+'/api/state').read());self.assertEqual(len(state['definitions']['modules']),7)
            body=json.dumps({'action':'reject','data':{'check_id':'R1.typography','issue':'标题透视与参考图不一致，需要按透视轴重建','severity':'P0'}}).encode()
            request=Request(url+'/api/action',body,{'Content-Type':'application/json','Origin':url},method='POST')
            response=json.load(urlopen(request));self.assertTrue(response['ok'])
            self.assertEqual(len(json.load(urlopen(url+'/api/state'))['state']['issues']),1)
            ticket=urlopen(url+'/api/ticket?check_id=R1.typography').read().decode('utf8')
            self.assertIn('标题透视',ticket)
            bad=Request(url+'/api/action',body,{'Content-Type':'application/json','Origin':'https://random.example'},method='POST')
            with self.assertRaises(HTTPError) as exc:urlopen(bad)
            self.assertEqual(exc.exception.code,403)
            with self.assertRaises(HTTPError) as exc:urlopen(url+'/api/preview?stage=R1&name=../../etc/passwd')
            self.assertEqual(exc.exception.code,404)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
if __name__=='__main__':unittest.main()

# More cases can be added without changing production scripts. This package tests behavior, not visual aesthetics.
