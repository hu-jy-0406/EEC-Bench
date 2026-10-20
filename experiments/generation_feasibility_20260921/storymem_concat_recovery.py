import subprocess,time,json,imageio_ffmpeg
from pathlib import Path
r=Path(__file__).resolve().parent;o=r/'outputs/storymem_official';st=time.monotonic();exe=imageio_ffmpeg.get_ffmpeg_exe()
cmd=[exe,'-f','concat','-safe','0','-i',str(o/'concat_list.txt'),'-c','copy','-y',str(o/'storymem_official.mp4')]
rc=subprocess.call(cmd);(r/'storymem_concat_recovery.json').write_text(json.dumps(dict(returncode=rc,seconds=time.monotonic()-st,command=cmd,scope='postprocess only; reuses four completed original videos')));raise SystemExit(rc)
