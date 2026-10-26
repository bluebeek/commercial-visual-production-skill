"""Explicit pixel/profile handling shared by compositing and audits."""
import io
from PIL import Image,ImageCms

def srgb_bytes():return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()

def rgba_image(path,target_icc=None,assume_srgb=False):
 with Image.open(path) as im:
  if im.getexif().get(274,1)!=1:raise ValueError('image has EXIF orientation; normalize explicitly and re-annotate before processing')
  profile=im.info.get('icc_profile')
  alpha=im.convert('RGBA').getchannel('A')
  if target_icc:
   if not profile and not assume_srgb:raise ValueError('untagged image needs explicit color_management.assume_untagged_srgb=true')
   src=ImageCms.ImageCmsProfile(io.BytesIO(profile)) if profile else ImageCms.createProfile('sRGB')
   dst=ImageCms.ImageCmsProfile(io.BytesIO(target_icc))
   rgb=ImageCms.profileToProfile(im.convert('RGB'),src,dst,outputMode='RGB')
  else:rgb=im.convert('RGB')
  result=rgb.convert('RGBA');result.putalpha(alpha)
  return result,profile
