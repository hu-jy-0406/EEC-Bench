import json,sys
from pathlib import Path
from huggingface_hub import HfApi
out=Path(__file__).parent
rows={}
for name in ['depth-anything/DA3NESTED-GIANT-LARGE-1.1','yyfz233/Pi3X','nvidia/dvlt']:
 try:
  info=HfApi().model_info(name,files_metadata=True)
  rows[name]={'sha':info.sha,'files':[{'name':s.rfilename,'size':s.size} for s in info.siblings]}
 except Exception as e:rows[name]={'error':str(e)}
(out/'model_availability.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
