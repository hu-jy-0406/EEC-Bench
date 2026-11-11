#!/usr/bin/env python3
"""Bridge current detector outputs to existing per-shot geometry backends."""
import argparse,os
from pathlib import Path
from run_gs_integrated import read,save,sha

def inputs(case, all_shots=False):
 from PIL import Image
 from gs_shot_prompt_recovery import active_entities_root
 entity_root=active_entities_root(case)
 mode=read(case/'coordinate_mode.json')['mode'] if (case/'coordinate_mode.json').exists() else 'gravity_aligned'
 for shot in read(case/'entities/manifest.json')['shots']:
  sid=shot['shot_id']
  if not all_shots and sid not in ['shot1','shot3']:continue
  sizes=[]
  for frame in shot['frames']:
   if sha(frame['path'])!=frame['sha256']:raise ValueError('Original JPEG hash mismatch')
   with Image.open(frame['path']) as im:sizes.append(list(im.size))
  entities=read(entity_root/'shots'/sid/'entities.json')['entities']
  save(case/'inputs'/f'{sid}.json',dict(shot_id=sid,frames=shot['frames'],entities=entities,image_sizes=sizes,coordinate_mode=mode,calibration=read(case/'calibration_new/calibration'/f'{sid}.json') if mode=='gravity_aligned' else None))

def calibrate(case, all_shots=False):
 import run_geocalib_boxer as impl
 if not os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-'):raise RuntimeError('Guarded UUID binding required')
 if (case/'calibration_new/calibration').exists():raise FileExistsError('Fresh calibration required')
 shots=[s for s in read(case/'entities/manifest.json')['shots'] if all_shots or s['shot_id'] in ['shot1','shot3']]
 for shot in shots:
  for frame in shot['frames']:
   if sha(frame['path'])!=frame['sha256']:raise ValueError('Original JPEG hash mismatch')
 impl.frozen=lambda:{s['shot_id']:s for s in shots}
 impl.calibrate(case/'calibration_new','cuda')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path);p.add_argument('stage',choices=['calibrate','inputs']);p.add_argument('--all-shots',action='store_true');a=p.parse_args()
 from run_isolated_shot_static_3d import owned_compute_job
 owned_compute_job();{'inputs':inputs,'calibrate':calibrate}[a.stage](a.case.resolve(),a.all_shots)
if __name__=='__main__':main()
