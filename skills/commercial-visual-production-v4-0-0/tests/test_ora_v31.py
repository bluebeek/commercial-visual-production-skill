import io, tempfile, unittest, zipfile
from pathlib import Path
from PIL import Image
from test_workflow_v3 import read_ora

class CroppedORA(unittest.TestCase):
 def make(self,root,layer=None,**attrs):
  data=io.BytesIO();(layer or Image.new('RGBA',(2,2),'red')).save(data,format='PNG')
  merged=Image.new('RGBA',(4,4));merged.alpha_composite(layer or Image.new('RGBA',(2,2),'red'),(1,1));b=io.BytesIO();merged.save(b,format='PNG')
  a={'name':'ink','src':'data/ink.png','x':'1','y':'1','opacity':'1','visibility':'visible','composite-op':'svg:src-over',**attrs}
  import xml.etree.ElementTree as E
  x=E.Element('image',w='4',h='4');E.SubElement(E.SubElement(x,'stack'),'layer',a)
  p=root/'test.ora'
  with zipfile.ZipFile(p,'w') as z:
   z.writestr('mimetype',b'image/openraster');z.writestr('stack.xml',E.tostring(x));z.writestr('data/ink.png',data.getvalue());z.writestr('mergedimage.png',b.getvalue())
  return p,merged
 def test_nonzero_offset_cropped_layer_recomposes_exactly(self):
  with tempfile.TemporaryDirectory() as d:
   p,expected=self.make(Path(d));actual,names=read_ora(p);self.assertEqual(actual.tobytes(),expected.tobytes());self.assertEqual(names,['ink'])
 def test_layer_outside_canvas_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p,_=self.make(Path(d),x='3')
   with self.assertRaises(ValueError):read_ora(p)
 def test_negative_offset_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p,_=self.make(Path(d),x='-1')
   with self.assertRaises(ValueError):read_ora(p)
 def test_missing_source_is_structured_failure(self):
  with tempfile.TemporaryDirectory() as d:
   p,_=self.make(Path(d),src='data/missing.png',x='0',y='0')
   with self.assertRaises(ValueError):read_ora(p)
 def test_unknown_blend_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p,_=self.make(Path(d),**{'composite-op':'svg:multiply'})
   with self.assertRaises(ValueError):read_ora(p)
