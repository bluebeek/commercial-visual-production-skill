"""Small CLI views; complete evidence reports remain on disk."""
import json

def compact_result(obj, report=None):
    out={k:obj[k] for k in ('status','reason','meaning','limits','note','guarantee','errors','warnings','missing_required_assets','missing_required','failures','unknowns','changed_outside_editable','changed_in_protected','changed_inside_editable','recomposition_verified','approved_composite_match','pixel_dimensions','judgment','global','locked_union','editable_union','locked_editable_overlap_pixels','region_warning') if k in obj}
    if report is not None:out['report']=str(report)
    for key in ('elements','constraints','checks'):
        if isinstance(obj.get(key),list):
            rows=obj[key]
            out[key+'_count']=len(rows)
            bad=[r for r in rows if not isinstance(r,dict) or r.get('result',r.get('status')) not in ('PASS',)]
            if bad:out[key+'_attention']=bad
    if 'regions' in obj:out['region_count']=len(obj['regions'])
    if 'included_layers' in obj:out['layer_count']=len(obj['included_layers'])
    return out

def emit_result(obj, report=None, full=False):
    print(json.dumps(obj if full else compact_result(obj,report),ensure_ascii=False,indent=2 if full else None,separators=None if full else (',',':')))
