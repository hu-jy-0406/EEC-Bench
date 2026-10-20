"""Accept unchanged latents/weights with RGB deviation bounded by native repeat noise."""
from campaign import ROOT,read,write
import time
p=read(ROOT/'mapped_diagnosis.json')
assert len(p)==6
assert [(x['mode'],x['repeat']) for x in p]==[(m,i) for m in ['standard','mapped_plain','mapped'] for i in range(2)]
assert all(not x['weight_mismatches'] and x['latent_bit_exact'] and x['latent_max_abs']==0 for x in p)
baseline=max(x['pixel_max_abs'] for x in p if x['mode']=='standard')
assert baseline<=1 and all(x['pixel_max_abs']<=baseline for x in p)
write(ROOT/'mapped_validation.json',dict(pass_all=True,all_loaded_parameters_equal=True,all_latents_bit_exact=True,pixels_bit_exact=False,native_repeat_pixel_max_abs=baseline,mapped_pixel_max_abs=max(x['pixel_max_abs'] for x in p if x['mode']=='mapped'),scope='Same-seed short2step generation; original repeat control explains at most1/255 RGB differences. Not full production quality or full-length equivalence.',proof=p,finished=time.time()))
print('PASS: actual parameters and diffusion latents exact; RGB deviation bounded by original repeated-run noise')
