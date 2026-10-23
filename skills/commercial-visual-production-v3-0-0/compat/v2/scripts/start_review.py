#!/usr/bin/env python3
"""Portable, dependency-checked local review entrypoint. No dependency installation."""
import argparse,sys,subprocess
from pathlib import Path

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--project',type=Path);p.add_argument('--mode',choices=['full','local-edit','delivery'],default='full')
 p.add_argument('--port',type=int,default=8765);p.add_argument('--check',action='store_true')
 a=p.parse_args()
 if sys.version_info<(3,10):print('BLOCK: Python 3.10+ required');return 2
 try:import PIL,numpy
 except ImportError as exc:print('BLOCK:',exc,'; run this Python with -m pip install Pillow numpy');return 2
 print('Python:',sys.executable,'Pillow:',PIL.__version__,'NumPy:',numpy.__version__,flush=True)
 if a.check:return 0
 if not a.project:p.error('--project is required unless --check')
 project=a.project.resolve();skill=Path(__file__).resolve().parents[1]
 if project==skill or project.is_relative_to(skill):p.error('store project data outside the skill directory')
 print('Workbench: http://127.0.0.1:'+str(a.port),flush=True)
 return subprocess.call([sys.executable,'-X','utf8',str(skill/'scripts/review_server.py'),'--project',str(project),'--mode',a.mode,'--port',str(a.port)])
if __name__=='__main__':sys.exit(main())
