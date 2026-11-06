"""Read-only environment inventory. Availability is not host-invocation evidence."""
import argparse, importlib.metadata, json, os, platform, shutil, subprocess, sys
from pathlib import Path

HOSTS={'codex':'codex','claude-code':'claude','cursor':'cursor','chatgpt':None,'claude-chat':None,'gemini-chat':None}

def inspect(host):
    if host not in HOSTS:raise ValueError('unknown host')
    binary=shutil.which(HOSTS[host]) if HOSTS[host] else None
    version=None
    if binary:
        try:
            r=subprocess.run([binary,'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10,creationflags=0x08000000 if os.name=='nt' else 0)
            version=r.stdout.strip()[:300] if r.returncode==0 else 'VERSION_QUERY_FAILED'
        except (OSError,subprocess.TimeoutExpired):version='VERSION_QUERY_FAILED'
    packages={}
    for name in ('Pillow','numpy','scipy'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    return {'schema':'cvisual.host.inventory.v1','host':host,'os':platform.platform(),'python':sys.version,
            'packages':packages,'launcher_found':bool(binary),'launcher_version':version,
            'credentials_present':{'openai':bool(os.environ.get('OPENAI_API_KEY')),'google':bool(os.environ.get('GEMINI_API_KEY'))},
            'verification':{'skill_discovery':'NOT_TESTED','native_host_invocation':'NOT_TESTED',
                            'real_generation':'NOT_TESTED','photocraft':'NOT_TESTED','complete_delivery':'NOT_TESTED'},
            'notice':'Inventory only. Never infer skill/runtime compatibility from an executable or package.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',choices=list(HOSTS),required=True);p.add_argument('--out',type=Path);a=p.parse_args();d=inspect(a.host)
    text=json.dumps(d,ensure_ascii=False,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
if __name__=='__main__':main()
