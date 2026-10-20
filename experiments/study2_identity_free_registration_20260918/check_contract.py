from register import *
owned_compute_job()
rng=np.random.default_rng(17);Q=rng.normal(size=(30,3));s0=1.35;R0=rz(.7);t0=np.array([.3,-.8,.2]);P=s0*Q@R0.T+t0
x=ls_seed(Q,P);s,R,t=params(x);assert np.allclose(s,s0) and np.allclose(R,R0) and np.allclose(t,t0)
assert np.allclose((P-t)@R/s,Q)
try:read(OLD/'matching.json')
except RuntimeError:blocked=True
else:blocked=False
assert blocked
save(RUN/'contract_check.json',dict(passed=True,synthetic_gravity_similarity_recovered=True,forward_inverse_consistent=True,cross_shot_identity_file_access_actively_blocked=True))
print('CONTRACT CHECK PASSED')
