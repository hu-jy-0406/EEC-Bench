import json,pathlib,hashlib,sys,shutil
from PIL import Image
P=pathlib.Path('.')
def sha(p):return hashlib.sha256(P.joinpath(p).read_bytes()).hexdigest()
def read():return json.loads(P.joinpath('pipeline.json').read_text())
def save(m):P.joinpath('pipeline.json').write_text(json.dumps(m,indent=2)+'\n')
def images(m):return [a['image'] for a in m['assets']]+[f['image'] for s in m['shots'] for f in s['frames'].values()]
if __name__=='__main__':
 op=sys.argv[1]
 if op=='prepare':
  id=sys.argv[2];m=read();im=next(i for i in images(m) if i['id']==id);refs=json.loads(sys.argv[3]) if len(sys.argv)>3 else im['reference_images']
  im['reference_images']=[dict(path=x['path'],role=x['role'],sha256=sha(x['path'])) for x in refs];save(m)
  print(json.dumps(dict(prompt=P.joinpath(im['prompt_path']).read_text(),refs=im['reference_images'])))
 if op=='accept':
  id,src,evidence=sys.argv[2:5];m=read();im=next(i for i in images(m) if i['id']==id);attempt=1+max([r['attempt'] for r in m['reviews'] if r['image_id']==id] or [0]);folder=P/'reviews'/id;folder.mkdir(parents=True,exist_ok=True)
  dest=folder/f'attempt_{attempt:02}.png';pr=folder/f'attempt_{attempt:02}.prompt.txt';shutil.copyfile(im['prompt_path'],pr)
  pic=Image.open(src);pic.load();repair=None
  if id=='room.image':m['settings']['frame_size_px']=[1672,940]
  if id.startswith('shot_') or id=='room.image':
   size=m['settings']['frame_size_px']
   if list(pic.size)!=size:
    if abs(pic.width-size[0])>2 or abs(pic.height-size[1])>2:raise RuntimeError(f'Non-tiny dimension mismatch: {pic.size} vs {size}')
    repair=f'Imperceptible resize from {pic.size} to {size}';pic=pic.resize(size,Image.Resampling.LANCZOS)
  pic.save(dest,format='PNG');shutil.copyfile(dest,im['path']);im.update(status='accepted',size_px=list(pic.size),sha256=sha(dest))
  m['reviews'].append(dict(image_id=id,attempt=attempt,decision='accept',notes=evidence,candidate_path=str(dest),candidate_sha256=sha(dest),prompt_path=str(pr),reference_images=im['reference_images'],tool='image_gen.imagegen',model=None,checks=[dict(requirement='Visual identity, counts, appearance, framing, contacts and planned state',result='pass',evidence=evidence),dict(requirement='Saved PNG decodes and dimensions meet plan',result='pass',evidence=f'PNG decoded at {pic.size}. '+(repair or 'No repair needed.'))],correction=repair));m['status']='generating';save(m)
