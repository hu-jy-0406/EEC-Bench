"""One fresh request; require exactly the failed request body's hash."""
import json,runpy,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_gemini_backend as backend
expected=json.loads((R/'run01/calls/identity_review_attempt1/request.json').read_text())['request_body_sha256']
original=backend.send

def send(body,timeout):
 assert backend.sha(json.dumps(body).encode())==expected,'Retry request differs from the original evidence/prompt/schema/settings'
 return original(body,timeout)
backend.send=send
sys.argv=[str(B/'scripts/run_gs_gemini_stage.py'),'run_gs_flow1_stage.py',str(R/'run01'),'review_identity','--runtime-profile','safe_spatial_medium']
runpy.run_path(sys.argv[0],run_name='__main__')
