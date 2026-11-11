import sys, unittest
from pathlib import Path
import numpy as np
from scipy.optimize._numdiff import approx_derivative
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import center_axis_registration as reg

class CenterAxisTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(103)
        self.x=rng.normal(size=(12,3))*[2,3,.7]
        self.theta=2.17
        self.m=(1.27,reg.rz(self.theta),np.array([1.2,-.8,.4]))
        self.y=reg.transform(self.x,self.m)

    def test_exact_known_transform(self):
        f=reg.fit(self.x,self.y,np.full(5,self.theta),axis_weight=.1)
        np.testing.assert_allclose(reg.transform(self.x,f['model']),self.y,atol=2e-6)
        self.assertAlmostEqual(f['model'][0],1.27,places=6)
        np.testing.assert_allclose(f['model'][1]@[0,0,1],[0,0,1],atol=1e-12)

    def test_center_only_closed_form(self):
        import gravity_box_registration as other
        y=self.y+np.random.default_rng(9).normal(0,.1,self.y.shape)
        a=reg.fit(self.x,y,delta=None)['model'];b=other.weighted_similarity(self.x,y)
        np.testing.assert_allclose(reg.transform(self.x,a),reg.transform(self.x,b),atol=2e-6)

    def test_analytic_gradient(self):
        x=self.x/4;y=self.y/4;p=np.array([.8,.2,.1,-.1,.3]);ds=np.array([.3,1.2])
        for delta in [None,.05,.7]:
            f=lambda v:reg.objective(v,x,y,ds,.2,delta)[0]
            numeric=approx_derivative(f,p).reshape(-1)
            np.testing.assert_allclose(reg.objective(p,x,y,ds,.2,delta)[1],numeric,atol=1e-7)

    def test_undirected_edges(self):
        a=reg.fit(self.x,self.y,np.full(4,self.theta),axis_weight=.3)
        b=reg.fit(self.x,self.y,np.full(4,self.theta)+np.array([0,np.pi,0,-np.pi]),axis_weight=.3)
        np.testing.assert_allclose(reg.transform(self.x,a['model']),reg.transform(self.x,b['model']),atol=2e-6)

    def test_independent_coordinate_gauges(self):
        g1=(.43,reg.rz(.7),np.array([.8,-2.,.5]));g2=(1.9,reg.rz(-1.1),np.array([-2.,1.,.2]))
        xx,yy=reg.transform(self.x,g1),reg.transform(self.y,g2)
        a=reg.fit(self.x,self.y,np.full(4,self.theta),axis_weight=.1)['model']
        b=reg.fit(xx,yy,np.full(4,self.theta-1.8),axis_weight=.1)['model']
        mapped=reg.compose(reg.inverse(g2),reg.compose(b,g1))
        np.testing.assert_allclose(reg.transform(self.x,a),reg.transform(self.x,mapped),atol=2e-6)

    def test_local_motion_robustness(self):
        corrupt=self.y.copy();corrupt[0]+=[10,0,0]
        r=reg.fit(self.x,corrupt,np.full(5,self.theta),axis_weight=.1)['model']
        ls=reg.fit(self.x,corrupt,delta=None)['model']
        err=lambda m:np.mean(np.linalg.norm(reg.transform(self.x,m)[1:]-self.y[1:],axis=1))
        self.assertLess(err(r),.3*err(ls))
        self.assertGreater(np.linalg.norm(reg.transform(self.x,r)[0]-corrupt[0]),8)

    def test_swap_visible_under_independent_reference_fit(self):
        corrupt=self.y.copy();corrupt[[0,1]]=corrupt[[1,0]]
        f=reg.fit(self.x[2:],corrupt[2:],np.full(4,self.theta),axis_weight=.1)
        p=reg.pair_cosines(self.x,corrupt,f['model'])
        self.assertLess(p[0]['cosine'],-.999999)

    def test_fixed_scale_and_inverse(self):
        f=reg.fit(self.x,self.y,np.full(4,self.theta),axis_weight=.1,fixed_scale=1.27)
        self.assertAlmostEqual(f['model'][0],1.27,places=12)
        np.testing.assert_allclose(reg.transform(self.x,f['model']),self.y,atol=2e-6)
        np.testing.assert_allclose(reg.transform(self.y,reg.inverse(f['model'])),self.x,atol=2e-6)

    def test_zero_vector_and_degenerate_yaw(self):
        x=np.array([[0,0,0],[0,0,0],[1,0,0.]])
        self.assertIsNone(reg.pair_cosines(x,x,(1,np.eye(3),np.zeros(3)))[0]['cosine'])
        with self.assertRaises(ValueError):reg.fit(np.array([[0,0,0],[0,0,1.]]),np.array([[0,0,0],[0,0,1.]]))

if __name__=='__main__':unittest.main()
