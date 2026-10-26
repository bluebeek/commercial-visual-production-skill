import sys,tempfile,unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import review_engine as e

class HistoricalRevisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
  for name,color in [('a.png','red'),('b.png','blue'),('c.png','green')]:Image.new('RGB',(32,32),color).save(self.p/name)
  e.load(self.p,create=True)
 def tearDown(self):self.tmp.cleanup()
 def register(self,revision,file):return e.transact(self.p,'revision',{'revision':revision,'evidence_files':[file]})
 def test_reject_historical_id_with_different_file(self):
  self.register('v01','a.png');self.register('v02','b.png')
  with self.assertRaises(e.ReviewError):self.register('v01','c.png')
  self.assertEqual(e.load(self.p)['active_revision']['id'],'v02')
 def test_reject_historical_id_with_changed_bytes_at_same_path(self):
  self.register('v01','a.png');self.register('v02','b.png')
  Image.new('RGB',(32,32),'green').save(self.p/'a.png')
  with self.assertRaises(e.ReviewError):self.register('v01','a.png')
  self.assertEqual(e.load(self.p)['active_revision']['id'],'v02')
 def test_allow_return_to_unchanged_historical_version(self):
  self.register('v01','a.png');self.register('v02','b.png');self.register('v01','a.png')
  self.assertEqual(e.load(self.p)['active_revision']['id'],'v01')
  self.assertEqual(e.load(self.p)['signoffs'],{})

if __name__=='__main__':unittest.main(verbosity=2)
