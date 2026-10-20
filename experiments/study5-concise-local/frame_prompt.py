from pipeline_io import *
import sys
id=sys.argv[1];m=read();im=next(i for i in images(m) if i['id']==id)
refs=json.loads(P.joinpath('next_refs.json').read_text());im['reference_images']=[dict(path=x['path'],role=x['role'],sha256=sha(x['path'])) for x in refs];P.joinpath(im['prompt_path']).write_text(P.joinpath('next_prompt.txt').read_text());save(m)
