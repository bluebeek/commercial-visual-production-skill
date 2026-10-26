"""Strict flat src-over ORA reader with bounded cropped-layer support."""
import io,zipfile,xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from PIL import Image

def read_layers(path):
 try:
  with zipfile.ZipFile(path) as z:
   members=z.namelist()
   if len(members)!=len(set(members)) or not members or members[0]!='mimetype' or z.getinfo('mimetype').compress_type!=zipfile.ZIP_STORED or z.read('mimetype')!=b'image/openraster':raise ValueError('invalid ORA mimetype/duplicate members')
   xml=ET.fromstring(z.read('stack.xml'));w=int(xml.get('w'));h=int(xml.get('h'))
   if w<1 or h<1 or w*h>100000000:raise ValueError('invalid ORA canvas')
   stack=xml.find('stack')
   if stack is None or not len(stack):raise ValueError('empty ORA stack')
   if any(e.tag!='layer' for e in stack):raise ValueError('unsupported nested ORA stack')
   layers=[];seen=set()
   for e in stack:
    name=e.get('name');src=e.get('src','');p=PurePosixPath(src)
    if not name or name in seen:raise ValueError('missing/duplicate ORA layer name')
    seen.add(name)
    if p.is_absolute() or '..' in p.parts or not src.startswith('data/') or not src.endswith('.png'):raise ValueError('invalid ORA layer source')
    if e.get('opacity','1.0') not in ('1','1.0') or e.get('composite-op')!='svg:src-over' or e.get('visibility')!='visible':raise ValueError('unsupported blend/opacity/visibility')
    x=int(e.get('x','0'));y=int(e.get('y','0'))
    with Image.open(io.BytesIO(z.read(src))) as im:
     im.load()
     if x<0 or y<0 or x+im.width>w or y+im.height>h:raise ValueError('ORA cropped layer outside canvas')
     canvas=Image.new('RGBA',(w,h));canvas.paste(im.convert('RGBA'),(x,y))
    layers.append({'name':name,'image':canvas,'offset':[x,y]})
   result=Image.new('RGBA',(w,h))
   for layer in reversed(layers):result.alpha_composite(layer['image'])
   with Image.open(io.BytesIO(z.read('mergedimage.png'))) as im:
    im.load()
    if im.size!=result.size or im.convert('RGBA').tobytes()!=result.tobytes():raise ValueError('ORA merged image differs from actual stack')
   return result,layers
 except (KeyError,TypeError,ET.ParseError,zipfile.BadZipFile) as e:raise ValueError('invalid ORA member/structure: '+str(e)) from e

def read_ora(path):
 image,layers=read_layers(path)
 return image,[x['name'] for x in reversed(layers)]
