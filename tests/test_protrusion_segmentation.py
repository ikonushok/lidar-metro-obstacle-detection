import unittest
import numpy as np
from test_stage_3_baseline import cloud, ROOT
from stage_3_baseline import load_geometry_contract, evaluate_cloud, protrusion_clusters


class ProtrusionTest(unittest.TestCase):
    def setUp(self):
        self.config = load_geometry_contract(ROOT / 'config/geometry_contract.yaml')
        self.profiles = {'auto_grade': {'status':'ACTIVE_ASSUMED_AUTO_GRADE',
                                      'z_intercept_m':0, 'grade_m_per_m':0}}

    def test_floor_bridge_separates_two_upright_components(self):
        floor = [(x,-10,0) for x in np.arange(-1,1.01,.1)]
        columns = [(x,-10,z) for x in (-1,1) for z in np.arange(0,1.71,.1)]
        found = protrusion_clusters(np.array(floor+columns),self.config,self.profiles)
        self.assertEqual(len(found),2)
        self.assertTrue(all(c['bounds_source_coordinates']['z']['min'] >= .35 for c in found))

    def test_low_obstacle_and_baseline_output_are_not_removed(self):
        message = cloud([(0,-5,.1)]*5)
        enabled = evaluate_cloud(message,self.config)
        self.config['detection']['protrusion_segmentation']['enabled'] = False
        disabled = evaluate_cloud(message,self.config)
        self.assertEqual(enabled['clusters'],disabled['clusters'])
        self.assertEqual(enabled['status'],disabled['status'])
        self.assertTrue(enabled['clusters'])

    def test_unknown_floor_produces_no_additional_components(self):
        self.assertEqual(protrusion_clusters(np.array([(0,-5,1)]*5),self.config,{}),[])
