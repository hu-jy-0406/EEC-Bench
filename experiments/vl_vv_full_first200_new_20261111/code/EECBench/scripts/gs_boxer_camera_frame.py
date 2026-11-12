"""Camera-oriented Boxer inference frame; no physical gravity is estimated.

Axes use the fixed convention (camera right, camera forward, negative camera
 down). This is a local model-input convention, NOT a physical-up measurement.
Its world pose changes covariantly with the scene coordinate gauge. The model
was trained with gravity-aligned frames; quality without measured gravity must
be evaluated, and this adapter does not claim unchanged predictions.
"""
import numpy as np
CAMERA_FROM_MODEL=np.array([[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])

def model_to_scene(camera_to_scene):
    camera=np.asarray(camera_to_scene,float)
    if camera.shape!=(4,4) or not np.isfinite(camera).all():raise ValueError('Invalid camera pose')
    result=camera.copy();result[:3,:3]=camera[:3,:3]@CAMERA_FROM_MODEL
    return result

def predict(model,datum):
    import torch
    from utils.tw.pose import PoseTW
    inputs=model.prepare_inputs(datum)
    camera=inputs['T_world_rig0']@inputs['cam0'].T_camera_rig.inverse()
    C=torch.as_tensor(CAMERA_FROM_MODEL,dtype=camera.R.dtype,device=camera.R.device)
    inputs['T_world_voxel0']=PoseTW.from_Rt(camera.R@C,camera.t)
    # Providing this explicit pose bypasses Boxer's implicit world-Z gravity
    # alignment. Leave weights, depth patches, image features and head unchanged.
    return model.query(inputs,model.encode(inputs))
