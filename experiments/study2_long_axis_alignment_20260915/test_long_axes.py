import unittest
import numpy as np
from fit_long_axes import fit, long_axis, rz, wrap_axis


class LongAxesTests(unittest.TestCase):
    def test_known_yaw_and_opposite_axis_signs(self):
        theta = np.radians(-27)
        observations = theta + np.array([0, np.pi, -np.pi, 2*np.pi])
        self.assertAlmostEqual(fit(observations), theta, places=12)
        # The nearest-zero branch is explicit: an undirected box axis cannot
        # distinguish a 153 degree rotation from -27 degrees.
        self.assertAlmostEqual(fit([np.radians(153)]), theta, places=12)

    def test_axis_permutation_and_vertical_height(self):
        R = rz(.3)
        box = dict(size=[2., 1., 8.], R_scene_from_object=R.tolist())
        out = long_axis(box)
        self.assertEqual(out['axis_index'], 0)
        self.assertEqual(out['horizontal_aspect_ratio'], 2.)
        perm = [2, 0, 1]  # proper cyclic reparametrization of the same OBB
        other = long_axis(dict(size=np.array(box['size'])[perm], R_scene_from_object=R[:, perm]))
        self.assertAlmostEqual(float(wrap_axis(out['heading_rad'] - other['heading_rad'])), 0.)
        self.assertEqual(other['horizontal_aspect_ratio'], 2.)

    def test_degenerate_evidence_rejected(self):
        for values in [[], [0, np.pi/2], [np.nan]]:
            with self.assertRaises(ValueError):
                fit(values)
        with self.assertRaises(ValueError):
            long_axis(dict(size=[1, 2, 3], R_scene_from_object=[[1,0,0],[0,.8,-.6],[0,.6,.8]]))

    def test_loss_minimum_and_near_square_rule(self):
        deltas = np.radians([-35, -25, -22, -24])
        theta = fit(deltas)
        loss = lambda t: np.mean(np.sin(t-deltas)**2)
        self.assertLess(abs(np.mean(np.sin(2*(theta-deltas)))), 1e-12)
        for angle in np.linspace(-np.pi/2, np.pi/2, 2001):
            self.assertLessEqual(loss(theta), loss(angle) + 1e-12)
        self.assertLess(long_axis(dict(size=[1,1.05,4], R_scene_from_object=rz(1.2)))['horizontal_aspect_ratio'], 1.2)


if __name__ == '__main__':
    unittest.main()
