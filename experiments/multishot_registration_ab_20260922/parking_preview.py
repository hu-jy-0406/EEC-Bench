from pathlib import Path
import subprocess,json
import imageio_ffmpeg
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
root=Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments')
src=root/'wan_generation_400_20260921/videos/7M9pU29bOeY_s00004_n4_clean_v2'
out=root/'multishot_registration_ab_20260922/shared/parking4/display'
out.mkdir(exist_ok=True)
for i in (1,2):
 p=src/f'Shot{i}.mp4'
 subprocess.run([ffmpeg,'-v','error','-threads','1','-i',str(p),'-map','0:v:0','-c:v','copy','-movflags','+faststart','-y',str(out/f'Shot{i}_playback.mp4')],check=True)
 subprocess.run([ffmpeg,'-v','error','-threads','1','-i',str(p),'-filter_complex_threads','1','-filter_complex','fps=12,scale=624:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse','-loop','0','-y',str(out/f'Shot{i}_preview.gif')],check=True)
 print(i,'ready',flush=True)
