"""Independent readback of the supported flat PNG/ORA subset; no editor compatibility claim."""
import io,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from PIL import Image

def read_ora(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or not names or names[0]!='mimetype' or z.getinfo('mimetype').compress_type!=zipfile.ZIP_STORED or z.read('mimetype')!=b'image/openraster':raise ValueError('invalid ORA mimetype/duplicate members')
        xml=ET.fromstring(z.read('stack.xml'));w=int(xml.get('w'));h=int(xml.get('h'))
        if w<1 or h<1 or w*h>100000000:raise ValueError('invalid ORA canvas')
        stack=xml.find('stack')
        if stack is None or not len(stack):raise ValueError('empty ORA stack')
        rows=list(stack)
        if any(r.tag!='layer' for r in rows):raise ValueError('unsupported nested ORA stack')
        result=Image.new('RGBA',(w,h),(0,0,0,0));layers=[]
        for e in reversed(rows):
            src=e.get('src','');p=PurePosixPath(src)
            if p.is_absolute() or '..' in p.parts or not src.startswith('data/') or not src.endswith('.png'):raise ValueError('invalid ORA layer source')
            if e.get('opacity','1.0') not in ('1','1.0') or e.get('composite-op')!='svg:src-over' or e.get('visibility')!='visible':raise ValueError('unsupported blend/opacity/visibility')
            if int(e.get('x','0')) or int(e.get('y','0')):raise ValueError('unsupported layer offsets')
            with Image.open(io.BytesIO(z.read(src))) as im:
                im.load()
                if im.size!=(w,h):raise ValueError('layer canvas mismatch')
                result.alpha_composite(im.convert('RGBA'))
            layers.append(e.get('name'))
        with Image.open(io.BytesIO(z.read('mergedimage.png'))) as merged:
            if merged.size!=result.size or merged.convert('RGBA').tobytes()!=result.tobytes():raise ValueError('ORA merged image differs from actual stack')
        return result,layers
