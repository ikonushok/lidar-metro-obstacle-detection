import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from cloud_input import inspect_cloud, point_view


def sample(big=False):
    fields = [S(name=n, offset=o, datatype=d, count=c) for n,o,d,c in
              [('x',0,7,1),('y',4,7,1),('z',8,7,1),('ring',12,4,1),('timestamp',14,8,1),('extra',22,2,2)]]
    data = bytearray(56)
    for offset, xyz in [(0,(1,2,3)), (28,(4,5,6))]:
        struct.pack_into(('>' if big else '<')+'fffHdBB', data, offset, *xyz, 127, 123.25, 7, 8)
    return S(height=2,width=1,point_step=24,row_step=28,data=data,fields=fields,is_bigendian=big,
             header=S(frame_id='original',stamp=S(sec=1,nanosec=2)))


class InputTest(unittest.TestCase):
    def test_endian_unaligned_time_padding_and_vector_field(self):
        for endian in (False, True):
            m=sample(endian)
            a=point_view(m)
            self.assertEqual(a['timestamp'][1,0],123.25)
            np.testing.assert_array_equal(a['extra'][0,0],[7,8])
            stats,xyz=inspect_cloud(m)
            np.testing.assert_array_equal(xyz,[[1,2,3],[4,5,6]])
            self.assertEqual(stats['header_ns'],1000000002)

    def test_nonfinite_and_zero_are_separate(self):
        m=sample()
        struct.pack_into('<fff',m.data,0,0,0,0)
        struct.pack_into('<fff',m.data,28,float('nan'),2,3)
        stats,xyz=inspect_cloud(m)
        self.assertEqual((stats['zero'],stats['nonfinite'],len(xyz)),(1,1,0))

    def test_truncated_data(self):
        m=sample(); m.data.pop()
        with self.assertRaises(ValueError): point_view(m)

    def test_field_outside_point(self):
        m=sample(); m.fields[-1].count=3
        with self.assertRaises(ValueError): point_view(m)

    def test_missing_xyz(self):
        m=sample(); m.fields=m.fields[1:]
        with self.assertRaises(ValueError): point_view(m)

    def test_short_row(self):
        m=sample(); m.row_step=20
        with self.assertRaises(ValueError): point_view(m)


if __name__=='__main__': unittest.main()
