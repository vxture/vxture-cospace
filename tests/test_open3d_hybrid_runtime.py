"""Run explicitly in the isolated Open3D environment with stdlib unittest."""
import unittest
import numpy as np
try:
    import open3d as o3d
except ImportError:
    o3d=None


@unittest.skipIf(o3d is None,'requires the isolated Open3D experiment environment')
class HybridRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.intrinsic=o3d.camera.PinholeCameraIntrinsic(160,120,130.,130.,79.5,59.5)
        y,x=np.mgrid[:120,:160]
        self.color=np.stack([127+60*np.sin(x*.15)+35*np.cos(y*.12),
                             127+50*np.sin(x*.08+y*.13),127+70*np.cos(x*.12-y*.11)],axis=-1).astype('u1')
        self.depth=np.full((120,160),2.,dtype=np.float32)
    def image(self,color,depth):
        return o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(color.copy()),
            o3d.geometry.Image(depth.copy()),depth_scale=1.,depth_trunc=10.,convert_rgb_to_intensity=True)
    def compute(self,source,target):
        return o3d.pipelines.odometry.compute_rgbd_odometry(source,target,self.intrinsic,np.eye(4),
            o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm(),o3d.pipelines.odometry.OdometryOption())
    def test_identity_pose(self):
        image=self.image(self.color,self.depth)
        ok,matrix,information=self.compute(image,image)
        self.assertTrue(ok); self.assertTrue(np.allclose(matrix,np.eye(4),atol=1e-8))
        self.assertEqual(information.shape,(6,6))
    def test_known_image_shift_checks_transform_direction(self):
        # Nonperiodic texture avoids aperture ambiguity; invalid margins exclude
        # the artificial wrap introduced by np.roll from the optimizer.
        rng=np.random.default_rng(42)
        raw=rng.uniform(0,255,(120,160,3))
        color=((raw+np.roll(raw,1,0)+np.roll(raw,-1,0)
                +np.roll(raw,1,1)+np.roll(raw,-1,1))/5).astype('u1')
        depth=self.depth.copy()
        depth[:10]=0; depth[-10:]=0; depth[:,:10]=0; depth[:,-10:]=0
        target=self.image(color,depth)
        source=self.image(np.roll(color,-2,axis=1),depth)
        ok,matrix,_=self.compute(source,target)
        self.assertTrue(ok)
        self.assertAlmostEqual(matrix[0,3],2*2/130,delta=.004)
        self.assertGreater(matrix[0,3],0)
        reverse_ok,reverse,_=self.compute(target,source)
        self.assertTrue(reverse_ok)
        self.assertLess(np.linalg.norm((matrix@reverse)[:3,3]),.004)
    def test_zero_depth_is_not_filled_by_image_creation(self):
        depth=self.depth.copy(); depth[20:40,20:40]=0
        image=self.image(self.color,depth)
        self.assertTrue(np.all(np.asarray(image.depth)[20:40,20:40]==0))
    def test_constant_color_has_no_photometric_gradient(self):
        image=self.image(np.full_like(self.color,128),self.depth)
        self.assertEqual(float(np.ptp(np.asarray(image.color))),0.)
        self.assertGreater(float(np.asarray(image.color).mean()),0.)
    def test_color_only_identity(self):
        image=self.image(self.color,self.depth)
        ok,matrix,_=o3d.pipelines.odometry.compute_rgbd_odometry(image,image,self.intrinsic,np.eye(4),
            o3d.pipelines.odometry.RGBDOdometryJacobianFromColorTerm(),o3d.pipelines.odometry.OdometryOption())
        self.assertTrue(ok); self.assertTrue(np.allclose(matrix,np.eye(4),atol=1e-8))
    def test_interior_mask_preserves_color_and_removes_depth_associations(self):
        from packages.construction.rgbd_diagnostics import interior_mask
        depth=self.depth.copy(); depth[50:60,70:80]=0
        core=interior_mask(depth,4)
        masked=np.where(core,depth,0).astype(np.float32)
        original=self.image(self.color,depth); interior=self.image(self.color,masked)
        self.assertTrue(np.array_equal(np.asarray(original.color),np.asarray(interior.color)))
        self.assertTrue(np.all(np.asarray(interior.depth)[46:64,66:84]==0))
    def test_bad_transform_is_rejected_by_adapter(self):
        from experiments.scripts.run_nyu_open3d import geometric_check
        points=np.array([[0.,0.,2.]]); pixels=np.array([[0,0]])
        matrix=np.eye(4); matrix[0,0]=-1
        result=geometric_check(points,points,pixels,matrix,True)
        self.assertFalse(result['accepted']); self.assertIn('invalid_transform',result['reasons'])


if __name__=='__main__': unittest.main()
