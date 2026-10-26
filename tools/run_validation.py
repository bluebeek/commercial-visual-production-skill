"""Run isolated regression suites and retain reproducible local/CI evidence."""
import argparse, hashlib, importlib.metadata, json, os, platform, subprocess, sys, time
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    a=p.parse_args()
    repo=Path(__file__).resolve().parents[1]
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    skill=repo/"skills/commercial-visual-production-v3-1-0"
    env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1")
    results=[]
    for name,cwd in (("v3",skill),("v2",skill/"compat/v2")):
        start=time.monotonic()
        r=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-v"],
                         cwd=cwd,env=env,capture_output=True,encoding="utf-8",errors="replace")
        (out/(name+".log")).write_text(r.stdout+r.stderr,encoding="utf-8")
        results.append({"suite":name,"exit_code":r.returncode,"seconds":round(time.monotonic()-start,3),
                        "log":name+".log"})
    packages={}
    for name in ("Pillow","numpy","scipy"):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    summary={"python":sys.version,"platform":platform.platform(),"packages":packages,
             "real_image_tool_calls":0,"fixture_outputs":"synthetic; test-only decisions",
             "suites":results}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    files={}
    for f in sorted(repo.rglob("*")):
        if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts and not f.is_relative_to(out):
            if any(p in ("validation-results","dist") for p in f.relative_to(repo).parts):continue
            files[f.relative_to(repo).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
    (out/"source-manifest.json").write_text(json.dumps(files,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    return int(any(r["exit_code"] for r in results))

if __name__=="__main__":sys.exit(main())
