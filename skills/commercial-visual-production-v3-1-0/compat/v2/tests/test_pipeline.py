import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
EXAMPLE=ROOT/'assets/blueprint.example.json'
OBSERVED=ROOT/'assets/observed.example.json'

def cmd(script,*params):
    return subprocess.run([sys.executable,str(SCRIPTS/script),*map(str,params)],capture_output=True,text=True,encoding="utf-8",env={**os.environ,"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"})

class ProductionPipelineTest(unittest.TestCase):
    def test_blueprint_preflight_and_render(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'out'
            run=cmd('blueprint.py','--spec',EXAMPLE,'--out',output)
            self.assertEqual(run.returncode,0,run.stderr+' '+run.stdout)
            for fn in ['preflight.json','blueprint_guide.png','layout_preview.png','mask_editable.png','mask_protected.png','production_contract.md']:
                self.assertTrue((output/fn).exists(),fn)
            with Image.open(output/'layout_preview.png') as im:
                self.assertEqual(im.size,(1080,1920))
    def test_reference_grid(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            Image.new("RGB",(200,300),(120,120,120)).save(d/"reference.png")
            run=cmd("reference_grid.py","--image",d/"reference.png","--out",d/"grid.png")
            self.assertEqual(run.returncode,0,run.stderr+run.stdout)
            with Image.open(d/"grid.png") as im: self.assertEqual(im.size,(200,300))

    def test_exact_flat_color_region(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            b=cmd("blueprint.py","--spec",EXAMPLE,"--out",d/"preview")
            self.assertEqual(b.returncode,0)
            c=cmd("pixel_audit.py","--image",d/"preview/layout_preview.png","--spec",EXAMPLE,"--out",d/"color.json")
            self.assertEqual(c.returncode,0,c.stdout+c.stderr)
            self.assertEqual(json.loads((d/"color.json").read_text(encoding="utf-8"))["status"],"PASS")
            # Wrong brand hue is a real failure, not an aesthetic judgment.
            wrong=Image.new("RGB",(1080,1920),(0,0,0))
            wrong.save(d/"wrong.png")
            bad=cmd("pixel_audit.py","--image",d/"wrong.png","--spec",EXAMPLE,"--out",d/"bad.json")
            self.assertEqual(bad.returncode,2)

    def test_audit_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'audit.json'
            rendered=Path(d)/'actual.png'
            Image.new('RGB',(1080,1920),'blue').save(rendered)
            observations=json.loads(OBSERVED.read_text(encoding='utf-8'))
            observations['image_sha256']=hashlib.sha256(rendered.read_bytes()).hexdigest()
            observed_file=Path(d)/'observed.json'
            observed_file.write_text(json.dumps(observations),encoding='utf-8')
            run=cmd('layout_audit.py','--spec',EXAMPLE,'--observed',observed_file,'--image',rendered,'--out',output)
            self.assertEqual(run.returncode,0,run.stdout+' '+run.stderr)
            original=observations.copy();original['boxes']=dict(observations['boxes'])
            original['boxes']['coach']=[0.1,0.13,0.17,0.21]
            bad=Path(d)/'bad.json';bad.write_text(json.dumps(original))
            run=cmd('layout_audit.py','--spec',EXAMPLE,'--observed',bad,'--image',rendered,'--out',output)
            self.assertEqual(run.returncode,2,run.stdout+' '+run.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))['status'],'BLOCK')
    def test_hard_lock_outside_exact(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            # Full image candidate deliberately changes every pixel.
            a=np.zeros((1920,1080,4),dtype=np.uint8)
            a[:]=[12,35,56,255]
            b=np.zeros_like(a);b[:]=[254,0,200,255]
            Image.fromarray(a,mode='RGBA').save(d/'baseline.png')
            Image.fromarray(b,mode='RGBA').save(d/'candidate.png')
            run=cmd('locked_edit.py','--baseline',d/'baseline.png','--candidate',d/'candidate.png','--spec',EXAMPLE,'--out',d/'result.png')
            self.assertEqual(run.returncode,0,run.stdout+' '+run.stderr)
            result=np.asarray(Image.open(d/'result.png'))
            self.assertTrue(np.array_equal(result[:1500],a[:1500]))
            self.assertTrue(np.any(result!=a))
            report=json.loads((d/'result.report.json').read_text(encoding="utf-8"))
            self.assertEqual(report['changed_outside_editable'],0)
            self.assertEqual(report['changed_in_protected'],0)
            # Refuse different size: no silently resized candidate.
            Image.fromarray(b[:1000],mode='RGBA').save(d/'wrong.png')
            wrong=cmd('locked_edit.py','--baseline',d/'baseline.png','--candidate',d/'wrong.png','--spec',EXAMPLE,'--out',d/'should_not_exist.png')
            self.assertNotEqual(wrong.returncode,0)
            self.assertFalse((d/'should_not_exist.png').exists())
    def test_export_real_asset_layers_and_refuse_missing(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            spec=json.loads(EXAMPLE.read_text(encoding="utf-8"))
            spec["canvas"]={"width":64,"height":96,"background":"#005EAD"}
            spec["editable_regions"]=[]
            spec["protected_regions"]=[{"id":"b","rect":[0,0,1,0.7]}]
            # An intentionally small real alpha asset to test raster layer export.
            rgba=np.zeros((20,12,4),dtype=np.uint8)
            rgba[4:16,2:10]=[255,255,0,255]
            Image.fromarray(rgba,mode="RGBA").save(d/"asset.png")
            for el in spec["elements"]:
                if el["role"] not in ("negative_space",):el["source"]="asset.png"
            bp=d/"bp.json";bp.write_text(json.dumps(spec))
            run=cmd("export_layers.py","--spec",bp,"--out",d/"layers")
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertTrue((d/"layers/layout_layers.ora").exists())
            import zipfile
            with zipfile.ZipFile(d/"layers/layout_layers.ora") as z:
                self.assertEqual(z.read("mimetype"),b"image/openraster")
                self.assertIn("stack.xml",z.namelist())
            spec["elements"][0].pop("source")
            bp.write_text(json.dumps(spec))
            bad=cmd("export_layers.py","--spec",bp,"--out",d/"bad_output")
            self.assertNotEqual(bad.returncode,0)
            self.assertFalse((d/"bad_output/layout_layers.ora").exists())

    def test_overlap_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            spec=json.loads(EXAMPLE.read_text(encoding="utf-8"))
            spec['protected_regions']=[{'id':'oops','rect':spec['editable_regions'][0]['rect']}]
            path=Path(d)/'bad.json';path.write_text(json.dumps(spec))
            run=cmd('blueprint.py','--spec',path,'--out',Path(d)/'out')
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(json.loads((Path(d)/'out/preflight.json').read_text(encoding="utf-8"))['status'],'BLOCK')

if __name__=='__main__':unittest.main()
