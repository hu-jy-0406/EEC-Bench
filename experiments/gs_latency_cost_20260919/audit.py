"""Audit original inputs, unchanged numerics, scoring gates and paid usage."""
import json,hashlib,sys
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_flow1_compact_payload import equivalent,unpack
import run_wedetect_shot_entities as io
from chain import C
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();manifest=io.read(C/'raw_manifest.json');images=[f for s in manifest['shots'] for f in s['frames']]
assert all(io.sha(f['path'])==f['sha256'] for f in images)
source=io.read(C/'provenance.json')['source_hashes'];unchanged={k:io.sha(k)==v for k,v in source.items() if Path(k).name in ['gs_flow1_evaluator.py','run_matching.py','prepare_correspondences.py','register.py']};assert all(unchanged.values())
base={r['relation_id']:r for r in io.read(C/'all_pair_cosines.json')};cases={};wire_count=0
for name in ['astra_low_chain_r2','astra_low_suffix_r3','astra_medium_suffix_r4','safe_spatial_medium']:
 root=H/name
 if not (root/'spatial.json').exists():continue
 current={r['relation_id']:r for r in io.read(root/'all_pair_cosines.json')};assert set(current)==set(base)
 for key in base:
  for field in ['cosine','vector_shot1','vector_shot3','vector_shot3_aligned']:assert current[key][field]==base[key][field]
 cases[name]=dict(all_28_cosines_and_vectors_exact=True,quality=io.read(root/'quality.json')['comparison'])
for variant in H.iterdir():
 if not variant.is_dir():continue
 parent=variant/'calls' if (variant/'calls').is_dir() else variant
 for call in parent.iterdir():
  if not call.is_dir() or not (call/'wire_input.json').is_file() or not (call/'output.schema.json').is_file():continue
  wire=io.read(call/'wire_input.json')
  if 'encoding' not in wire:continue
  equivalent(io.read(call/'input.json'),unpack(wire));wire_count+=1
  if (call/'status.json').exists() and io.read(call/'status.json')['status']=='success':assert io.audit_events(call/'events.jsonl')==io.read(call/'status.json')['usage']
files=[B/'scripts'/n for n in ['gs_efficient_transport.py','gs_witness_codec.py','gs_runtime_profile.py','run_gs_integrated.py','run_gs_flow1_stage.py','run_gs_motion_fusion.py','prepare_gs_integrated.py']]
io.dump(H/'audit.json',dict(original_jpeg_hashes=12,all_originals_unchanged=True,unchanged_numerical_and_scoring_sources=unchanged,lossless_wire_payloads_checked=wire_count,cases=cases,implementation_sha256={str(p):io.sha(p) for p in files}))
print('AUDIT OK',wire_count,'lossless payloads;',len(cases),'complete numerical comparisons')
