"""Pure geometry and JSON validation for Commercial Visual Production V2."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import re

ALLOWED_ROLES = {'person','coach','product','logo','headline','subhead','text','background','decoration','architecture','negative_space','group'}
ALLOWED_LOCK = {'L0','L1','L2','L3'}
ALLOWED_REFERENCE = {'composition','typography','color','identity','product','architecture','mood'}
ALLOWED_CONSTRAINT = {'above','left_of','nonoverlap','min_area_ratio','align_left','align_center_x','inside'}
CONSTRAINT_ALIASES={'area_ratio_min':'min_area_ratio','contained_in':'inside'}

def load_project(path):
    p = Path(path).resolve()
    raw = json.loads(p.read_text(encoding='utf-8'))
    return raw, p.parent

def parse_box(obj, label):
    if not isinstance(obj, list) or len(obj) != 4:
        raise ValueError(f'{label}: box needs [x,y,width,height]')
    nums = [float(i) for i in obj]
    if not all(math.isfinite(i) for i in nums):
        raise ValueError(f'{label}: non-finite number')
    x,y,w,h = nums
    if w <= 0 or h <= 0 or min(x,y) < 0 or x+w > 1.000000001 or y+h > 1.000000001:
        raise ValueError(f'{label}: box must be within normalized 0..1 canvas')
    return nums

def bbox_rect(box):
    x,y,w,h=box
    return (x,y,x+w,y+h)

def area(box): return box[2]*box[3]

def intersect_area(a,b):
    ax0,ay0,ax1,ay1=bbox_rect(a)
    bx0,by0,bx1,by1=bbox_rect(b)
    return max(0,min(ax1,bx1)-max(ax0,bx0))*max(0,min(ay1,by1)-max(ay0,by0))

def evaluate_constraint(constraint, boxes):
    typ=CONSTRAINT_ALIASES.get(constraint.get('type'),constraint.get('type'))
    a_id,b_id=constraint.get('a'),constraint.get('b')
    if typ not in ALLOWED_CONSTRAINT:
        return False, f'unsupported constraint: {typ}; allowed: {sorted(ALLOWED_CONSTRAINT)}'
    if a_id not in boxes or b_id not in boxes:
        return None, 'missing observation'
    a,b=boxes[a_id],boxes[b_id]
    ax,ay,aw,ah=a; bx,by,bw,bh=b
    t=float(constraint.get('tolerance',0.015))
    if typ == 'above': return ay+ah <= by+t, f'{a_id} bottom={ay+ah:.3f} / {b_id} top={by:.3f}'
    if typ == 'left_of': return ax+aw <= bx+t, f'{a_id} right={ax+aw:.3f} / {b_id} left={bx:.3f}'
    if typ == 'nonoverlap': return intersect_area(a,b) <= float(constraint.get('max_overlap',0.0)), f'overlap={intersect_area(a,b):.4f}'
    if typ == 'min_area_ratio':
        ratio=float(constraint.get('ratio',1.0))
        return area(a)>=ratio*area(b), f'area ratio actual={area(a)/area(b):.2f} vs min={ratio:.2f}'
    if typ == 'align_left': return abs(ax-bx)<=t, f'left delta={abs(ax-bx):.3f}'
    if typ == 'align_center_x': return abs((ax+aw/2)-(bx+bw/2))<=t, f'center delta={abs((ax+aw/2)-(bx+bw/2)):.3f}'
    if typ == 'inside':
        return ax>=bx-t and ay>=by-t and ax+aw<=bx+bw+t and ay+ah<=by+bh+t, 'containment'
    return None, 'unsupported'

def mask_for_regions(regions,width,height):
    im=Image.new('L',(width,height),0)
    d=ImageDraw.Draw(im)
    for r in regions:
        if 'rect' in r:
            arr=r['rect']
            if not isinstance(arr,list) or len(arr)!=4:
                raise ValueError(f"region {r.get('id','?')}: invalid rect")
            x0,y0,x1,y1=map(float,arr)
            if not (0<=x0<x1<=1 and 0<=y0<y1<=1):
                raise ValueError(f"region {r.get('id','?')}: rect requires normalized [x0,y0,x1,y1]")
            # use half-open pixel intervals so adjacent rectangles don't overlap
            xl=int(round(x0*width)); xr=int(round(x1*width))-1
            yt=int(round(y0*height)); yb=int(round(y1*height))-1
            if xl<=xr and yt<=yb: d.rectangle([xl,yt,xr,yb],fill=255)
        elif 'polygon' in r:
            ps=r['polygon']
            if len(ps)<3 or any(len(pt)!=2 or not all(0<=float(v)<=1 for v in pt) for pt in ps):
                raise ValueError(f"region {r.get('id','?')}: invalid polygon")
            d.polygon([(round(float(x)*width),round(float(y)*height)) for x,y in ps],fill=255)
        else:
            raise ValueError(f"region {r.get('id','?')} missing rect/polygon")
    return np.asarray(im,dtype=np.uint8)>0

def validate_project(project, root, mode='draft'):
    errors=[]; warnings=[]
    canv=project.get('canvas',{})
    w,h=canv.get('width'),canv.get('height')
    if not isinstance(w,int) or not isinstance(h,int) or not (8<=w<=12000 and 8<=h<=12000):
        errors.append('canvas width/height must be integers between 8 and 12000')
        w=h=256
    bg=canv.get('background','#FFFFFF')
    if not (isinstance(bg,str) and len(bg)==7 and bg.startswith('#') and all(c in '0123456789ABCDEFabcdef' for c in bg[1:])):
        errors.append('canvas.background must be #RRGGBB')
    elements=project.get('elements',[])
    if not isinstance(elements,list) or not elements: errors.append('elements must be nonempty list'); elements=[]
    ids=set(); boxes={}
    safe_margin=float(project.get('rules',{}).get('safe_margin',0.0))
    for i,e in enumerate(elements):
        if not isinstance(e,dict): errors.append(f'elements[{i}] invalid'); continue
        eid=e.get('id')
        if not isinstance(eid,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',eid) or '..' in eid or eid in ids:
            errors.append(f'elements[{i}] id missing/duplicate'); continue
        ids.add(eid)
        try: boxes[eid]=parse_box(e.get('box'),eid)
        except Exception as ex: errors.append(str(ex)); continue
        if e.get('role') not in ALLOWED_ROLES: errors.append(f'{eid}: invalid role')
        if e.get('lock','L3') not in ALLOWED_LOCK: errors.append(f'{eid}: invalid lock')
        if not isinstance(e.get('z',0),(int,float)) or not math.isfinite(e.get('z',0)): errors.append(f'{eid}: z must be finite numeric')
        if e.get('fit','contain')!='contain': errors.append(f'{eid}: only non-distorting contain is supported')
        if any(k in e for k in ('rotation','rotate','transform','perspective','skew')):
            errors.append(f'{eid}: transforms are not supported; bake them into a source asset and remeasure its axis-aligned box')
        if e.get('source'):
            path=(root/e['source']).resolve()
            if not path.is_relative_to(root.resolve()): errors.append(f'{eid}: asset path must stay within project directory')
            elif not path.is_file():
                warnings.append(f'{eid}: source missing: {e["source"]}; will use placeholder')
        elif e.get('lock','L3') in ('L0','L1') and e.get('role') in ('person','coach','product','logo','architecture'):
            warnings.append(f'{eid}: {e.get("lock")} protected element has no source; only placeholder possible; do NOT claim fidelity')
        if not e.get('allow_bleed',False) and safe_margin>0:
            x,y,bw,bh=boxes[eid]
            if min(x,y,1-x-bw,1-y-bh)<safe_margin-1e-9:
                warnings.append(f'{eid}: within declared safe_margin; mark allow_bleed=true if intentional')
    refs=project.get('reference_roles',[])
    for i,r in enumerate(refs):
        if r.get('role') not in ALLOWED_REFERENCE: errors.append(f'reference_roles[{i}]: invalid role')
    for i,c in enumerate(project.get('constraints',[])):
        cid=c.get('id',f'constraint_{i}')
        res,why=evaluate_constraint(c,boxes)
        if res is False: errors.append(f'blueprint constraint {cid} failed: {why}')
        elif res is None: errors.append(f'constraint {cid} missing element box/unsupported')
    missing=[]
    for e in elements:
        if not isinstance(e,dict):continue
        required=e.get('required',True)
        needs_asset=e.get('role') not in ('negative_space','group','background')
        if required and (needs_asset or e.get('source')):
            if not e.get('source') or not (root/e['source']).is_file():missing.append(e.get('id','?'))
    if missing:
        message='required real assets missing: '+', '.join(missing)
        (errors if mode=='production' else warnings).append(message)
    try:
        editable=mask_for_regions(project.get('editable_regions',[]),w,h)
        protected=protection_mask(project,root,w,h)
        if (editable & protected).any(): errors.append('editable_regions and protected_regions overlap; fix before running locked edit')
    except Exception as ex: errors.append(str(ex))
    if not project.get('editable_regions',[]): warnings.append('no editable regions set; locked edit will block until editable mask is declared')
    estimate=(w*h*4*4)/(1024*1024)
    warnings.append(f'working raster estimate >= {estimate:.1f} MiB; large sources and masks add memory')
    return {'status':'BLOCK' if errors else ('DRAFT_ONLY' if missing else 'PASS'),'mode':mode,'errors':errors,'warnings':warnings,'missing_required_assets':missing,'canvas':{'width':w,'height':h},'element_count':len(elements)},boxes

def protection_mask(project,root,w,h):
    """Conservative L0/L1 box protection. Exceptions need an explicit authorization file."""
    protected=mask_for_regions(project.get('protected_regions',[]),w,h)
    for e in project.get('elements',[]):
        if e.get('lock') not in ('L0','L1') or e.get('role') in ('group','negative_space'):continue
        x,y,bw,bh=parse_box(e['box'],e['id'])
        region=mask_for_regions([{'rect':[x,y,x+bw,y+bh]}],w,h)
        authorization=e.get('edit_authorization')
        if authorization:
            if not isinstance(authorization,dict) or not authorization.get('reason'):raise ValueError('edit_authorization requires reason and evidence_file')
            ev=(root/str(authorization.get('evidence_file',''))).resolve()
            if not ev.is_relative_to(root.resolve()) or not ev.is_file():raise ValueError('L0/L1 edit requires a project-local authorization evidence file')
            # Only explicitly approved subregions are exempt, never the complete lock by a boolean.
            allowed=mask_for_regions(authorization.get('regions',[]),w,h)
            if not allowed.any() or (allowed & ~region).any():raise ValueError('authorized subregion must be inside the protected element box')
            region &= ~allowed
        protected |= region
    return protected
