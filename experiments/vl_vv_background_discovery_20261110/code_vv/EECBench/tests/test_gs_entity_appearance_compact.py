import copy
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_entity_appearance_compact as m

class CompactTests(unittest.TestCase):
    def payload(self):
        return dict(global_entity_id='g',name='target',normal_story_prompt=dict(facts=[dict(fact_id='p1',text='turn')]),appearances=[dict(appearance_id='a'),dict(appearance_id='b')])
    def raw(self):return dict(u=[2,1],s=[75,25,100,None],e=[[0,1],[0,1],[0,1],[]],why='对应表面颜色改变，比例稳定。',limits='细节不可辨',expected_changes=[])
    def test_local_mean_and_null(self):
        r=m.expand(self.raw(),self.payload());self.assertAlmostEqual(r['score'],200/3)
        raw=self.raw();raw['s']=[None]*4;raw['e']=[[]]*4;self.assertIsNone(m.expand(raw,self.payload())['score'])
    def test_reject_missing_panel_wrong_witness_or_fact(self):
        for k in range(4):
            r=self.raw()
            if k==0:r['u'].pop()
            elif k==1:r['e'][0]=[0,2]
            elif k==2:r['u'][1]=0
            else:r['expected_changes']=['invented']
            with self.assertRaises(ValueError):m.expand(r,self.payload())
    def test_sheet_roundtrip_and_original_order(self):
        from PIL import Image
        p=self.payload();p['appearances']=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,(w,h) in enumerate([(30,10),(40,60),(180,50),(22,33)]):
                image=Image.new('RGB',(w,h),(31*i,15,250));image.putpixel((w-1,h-1),(1,2,3));path=root/f'{i}.png';image.save(path)
                p['appearances'].append(dict(appearance_id=f'a{i}',crop_path=str(path),crop_sha256=m.sha(path),shot_id='shot1',frame_id=i,timestamp_sec=float(i),derived_crop_xyxy=[10,20,10+w,20+h],candidates=[dict(box_xyxy=[12,22,w+8,h+18])]))
            rows,images,audit=m.sheets(p,root/'sheets',max_side=128)
            self.assertEqual([a['appearance_id'] for a in audit],['a0','a1','a2','a3'])
            self.assertGreater(len(images),1)
            for a in audit:
                with Image.open(images[a['sheet_index']]['path']) as sheet,Image.open(a['crop_path']) as crop:
                    self.assertEqual(sheet.crop(a['rect']).tobytes(),crop.tobytes())
            self.assertEqual(rows[0][5][0][:2],[2,2])
    def test_wire_omits_provenance_not_narrative(self):
        p=self.payload();p['original_frame']='private/local/path';w=m.wire_payload(p,[[1,2]])
        self.assertEqual(w['facts'],p['normal_story_prompt']['facts']);self.assertNotIn('original_frame',w)
if __name__=='__main__':unittest.main()
