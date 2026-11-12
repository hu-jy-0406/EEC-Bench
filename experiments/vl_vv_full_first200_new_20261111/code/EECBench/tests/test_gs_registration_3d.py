import sys
import unittest
from pathlib import Path
import numpy as np
from scipy.optimize._numdiff import approx_derivative
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_registration_3d import objective_and_gradient, distances, fit_all_pairs, rotation


class Registration3DTests(unittest.TestCase):
    def test_exact_sum_not_squares_or_truncation(self):
        p=np.array([[3.,4,0],[0,0,120.]])
        q=np.zeros_like(p)
        value,_=objective_and_gradient(np.zeros(5),p,q)
        self.assertEqual(value,125.)

    def test_analytic_gradient(self):
        rng=np.random.default_rng(21);p=rng.normal(size=(30,3));q=rng.normal(size=(30,3))
        x=np.array([.2,.7,1.,-.3,.5])
        numeric=approx_derivative(lambda z:objective_and_gradient(z,p,q)[0],x).ravel()
        np.testing.assert_allclose(objective_and_gradient(x,p,q)[1],numeric,rtol=1e-6,atol=1e-6)

    def test_known_transform(self):
        q=np.random.default_rng(8).normal(size=(40,3));p=1.3*q@rotation(.73).T+[.2,-.4,.1]
        fit=fit_all_pairs(p,q,yaw_starts=8)
        self.assertLess(fit['objective_value'],1e-6)
        np.testing.assert_allclose(fit['translation'],[.2,-.4,.1],atol=1e-6)
        self.assertAlmostEqual(fit['scale'],1.3,places=6)

    def test_large_error_pair_remains_in_objective(self):
        q=np.random.default_rng(18).normal(size=(40,3));p=q.copy();p[-1]+=[100.,0,0]
        fit=fit_all_pairs(p,q,yaw_starts=8)
        errors=distances(np.array(fit['parameters']),p,q)
        self.assertEqual(fit['fit_rows'],40);self.assertEqual(fit['points_removed'],0)
        self.assertGreater(errors[-1],90.)
        self.assertAlmostEqual(fit['objective_value'],float(errors.sum()),places=10)
        self.assertGreater(fit['objective_value'],90.)

    def test_invalid_points_fail_without_silent_deletion(self):
        q=np.eye(3);p=q.copy();p[0,0]=np.nan
        with self.assertRaises(ValueError):fit_all_pairs(p,q)


if __name__=='__main__':unittest.main()
