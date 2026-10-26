"""Project-level cross-process transaction lock and optimistic state writes."""
from contextlib import contextmanager
from pathlib import Path
import json,os,tempfile,time

class ConflictError(ValueError):pass

@contextmanager
def project_lock(project,timeout=8):
 root=Path(project).resolve();root.mkdir(parents=True,exist_ok=True)
 with (root/'.review.lock').open('a+b') as handle:
  handle.seek(0,2)
  if handle.tell()==0:handle.write(b'0');handle.flush()
  deadline=time.monotonic()+timeout
  while True:
   try:
    handle.seek(0)
    if os.name=='nt':
     import msvcrt
     msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    else:
     import fcntl
     fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    break
   except OSError:
    if time.monotonic()>deadline:raise ConflictError('项目正被其他操作占用，请稍后重试')
    time.sleep(.025)
  try:yield
  finally:
   handle.seek(0)
   if os.name=='nt':
    import msvcrt
    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
   else:
    import fcntl
    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def write_unlocked(project,state):
 root=Path(project).resolve();path=root/'review_state.json'
 existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
 expected=state.get('_loaded_seq')
 if existing is not None and expected!=existing.get('seq'):raise ConflictError('审核状态已更新，请重新读取后再提交')
 clean={k:v for k,v in state.items() if not k.startswith('_')}
 if existing is not None:
  history=root/'.review-history';history.mkdir(exist_ok=True)
  backup=history/f'{existing["seq"]:08d}.json'
  if not backup.exists():backup.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8')
 fd,tmp=tempfile.mkstemp(prefix='.review-',suffix='.json',dir=root)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump(clean,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 state['_loaded_seq']=state['seq']
