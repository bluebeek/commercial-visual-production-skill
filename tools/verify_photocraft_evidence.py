"""Independent review of saved real PhotoCraft visibility/range evidence (no tool calls)."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from PIL import Image

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--evidence',required=True,type=Path);a=ap.parse_args()
 repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'skills/commercial-visual-production-v3-1-0/scripts'))
 from ora_verify import read_layers
 from _workflow import load,atomic,sha
 root=a.evidence.resolve();results=[]
 for name,rid in [('eight-layer-project','correct-copy'),('patch-project-verified','v3')]:
  project=root/name;request=json.loads((project/'actual-editor-audit/verify-request.json').read_text(encoding='utf-8'));image,layers=read_layers(project/request['input']);visibility=[]
  for layer in layers:
   expected=Image.new('RGBA',image.size)
   for other in reversed(layers):
    if other['name']!=layer['name']:expected.alpha_composite(other['image'])
   with Image.open(project/('actual-editor-audit/hidden-'+layer['name']+'.png')) as im:count=int(np.any(np.asarray(expected)!=np.asarray(im.convert('RGBA')),axis=2).sum())
   visibility.append({'layer':layer['name'],'changed_from_expected':count})
  s=load(project);r=s['revisions'][rid];item={'project':name,'visibility':visibility,'editor_status':s['checks'][rid]['editor']['status'],'accepted_revision':s['accepted_revision'],'real_image_generation_calls':0,'simulated_baseline_events':s['calls_used']}
  if name=='patch-project-verified':
   j=s['jobs']['actual-edit'];before=s['revisions']['v2'];x,y,w,h=j['editor_plan']['operation']['rect']
   old=np.asarray(Image.open(project/before['image']).convert('RGBA'));new=np.asarray(Image.open(project/r['image']).convert('RGBA'));mask=np.zeros(old.shape[:2],dtype=bool);mask[y:y+h,x:x+w]=True;changed=np.any(old!=new,axis=2)
   item['adopted']={'inside_changed':int((changed&mask).sum()),'outside_changed':int((changed&~mask).sum()),'patch_bounds':Image.open(project/'production/actual-edit/materialized/patch.png').getbbox(),'prior_patch_file_preserved':all(sha(project/path)==digest and r['files'].get(path)==digest for path,digest in before['files'].items() if path.endswith('production/prior-patch/materialized/patch.png'))}
  results.append(item)
 neg=root/'negative-project';source=json.loads((neg/'negative-plan.json').read_text(encoding='utf-8'))['input'];baseline,_=read_layers(neg/source)
 with Image.open(neg/'missing-canvas-preview.png') as im:negative_preview=int(np.any(np.asarray(baseline)!=np.asarray(im.convert('RGBA')),axis=2).sum())
 n=load(neg);negative={'preview_changed':negative_preview,'editor_status':n['checks']['correct-copy']['editor']['status'],'reason':n['checks']['correct-copy']['editor']['detail']}
 passed=all(x['editor_status']=='PASS' and all(y['changed_from_expected']==0 for y in x['visibility']) for x in results) and results[1]['adopted']['inside_changed']==16 and results[1]['adopted']['outside_changed']==0 and results[1]['adopted']['prior_patch_file_preserved'] and negative['editor_status']=='FAIL'
 report={'status':'PASS' if passed else 'FAIL','cases':results,'negative':negative,'scope':'actual PhotoCraft MCP engine on synthetic fixtures; GUI not tested; no user acceptance'};atomic(root/'actual-independent-checks.json',report);print(json.dumps(report,ensure_ascii=False));return int(not passed)
if __name__=='__main__':sys.exit(main())
