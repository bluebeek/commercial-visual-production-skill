"""Install candidate bundles into isolated directories and test actual copied scripts."""
import argparse,hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path

def main():
    a=argparse.ArgumentParser();a.add_argument('--packages',type=Path,required=True);a.add_argument('--out',type=Path,required=True);o=a.parse_args()
    packages=o.packages.resolve();out=o.out.resolve()
    if out.exists():raise ValueError('smoke output exists; use a new directory')
    out.mkdir(parents=True)
    manifest=json.loads((packages/'V4_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    entries=json.loads((packages/'packages.json').read_text(encoding='utf-8'));results=[]
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    for item in entries:
        archive=packages/item['archive']
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('package changed')
        destination=out/item['host'];destination.mkdir()
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                target=(destination/name).resolve()
                if not target.is_relative_to(destination):raise ValueError('package traversal')
            z.extractall(destination)
        skill=(destination/item['entrypoint']).parent
        mismatch=[n for n,h in manifest['files'].items() if hashlib.sha256((skill/n).read_bytes()).hexdigest()!=h]
        r=subprocess.run([sys.executable,str(skill/'scripts/workflow.py'),'init','--project',str(destination/'project'),'--project-id','installed-smoke'],capture_output=True,encoding='utf-8',env=env)
        state=json.loads((destination/'project/workflow_state.json').read_text(encoding='utf-8')) if r.returncode==0 else {}
        ok=not mismatch and r.returncode==0 and state.get('schema')=='cvisual.workflow.v4' and state.get('call_budget')==0 and state.get('calls_used')==0
        result={'host_package':item['host'],'files':len(manifest['files']),'hash_mismatches':mismatch,'init_exit_code':r.returncode,'zero_budget':state.get('call_budget')==0,'status':'PASS' if ok else 'FAIL','native_host_invocation':'NOT_TESTED'}
        if item['host']=='native':
            t=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_generation_v4.py','-v'],cwd=skill,capture_output=True,encoding='utf-8',env=env)
            (out/'installed-generation.log').write_text(t.stdout+t.stderr,encoding='utf-8')
            result['installed_simulated_generation_exit_code']=t.returncode
            if t.returncode:result['status']='FAIL'
        results.append(result)
    report={'real_image_calls':0,'global_install_modified':False,'results':results}
    (out/'installation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    return int(any(x['status']!='PASS' for x in results))
if __name__=='__main__':sys.exit(main())
