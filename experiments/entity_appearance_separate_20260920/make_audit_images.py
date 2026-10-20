from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent
for name,study,eid,keys in [
 ('study2_person','study2','ge0004',['shot1_f0','shot1_f72','shot3_f72','shot3_f96']),
 ('study3_lamp','study3','ge0003',['shot1_f0','shot1_f120','shot3_f0','shot3_f120'])]:
 canvas=Image.new('RGB',(960,380),'white');draw=ImageDraw.Draw(canvas)
 for i,key in enumerate(keys):
  im=Image.open(root/study/'entities'/eid/(key+'.png')).convert('RGB'); im.thumbnail((230,340))
  canvas.paste(im,(i*240+(230-im.width)//2,30));draw.text((i*240+5,5),key,fill='black')
 canvas.save(root/(name+'.jpg'),quality=85)
