import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PIPE = Path(__file__).resolve().parents[1] / 'cloud/vendor/pipeline'
sys.path.insert(0, str(PIPE))
import entity_resolve as E


def row(i, name='星月餐厅', address='', phone='', location=None):
    return dict(id=i, name=name, address=address, phone=phone,
                location=location, status='active')


class Safety(unittest.TestCase):
    def groups(self, auto, review=(), keep=()):
        return E.candidate_groups([{'id': i + 1} for i in range(3)], auto, review, keep)

    def test_overlap_reproduction_and_fix(self):
        auto, review = [(0, 1, [])], [(1, 2, [])]
        self.assertEqual(E.components(auto, 3), [[0, 1]])
        self.assertEqual(E.components(auto + review, 3), [[0, 1, 2]])
        self.assertEqual(self.groups(auto, review), ([], [[0, 1, 2]]))

    def test_real_brand_bridge_requires_review(self):
        rows = [row(1, name='星月', address='月光路12号'),
                row(2, name='星月海天', address='月光路12号'),
                row(3, name='海天', address='月光路12号')]
        R, auto, review, _ = E.build(rows)
        self.assertEqual(len(auto), 2)
        self.assertEqual(E.candidate_groups(R, auto, review, []), ([], [[0, 1, 2]]))

    def test_real_strong_plus_weak_bridge_no_overlap(self):
        rows = [row(1, name='星月', address='月光路12号'),
                row(2, name='星月海天', address='月光路12号', phone='02112345678'),
                row(3, name='海天', address='月光路20号', phone='02112345678')]
        R, auto, review, _ = E.build(rows)
        self.assertEqual(len(auto), 1)
        self.assertEqual(len(review), 1)
        self.assertEqual(E.candidate_groups(R, auto, review, []), ([], [[0, 1, 2]]))

    def test_strong_chain_not_auto(self):
        self.assertEqual(self.groups([(0, 1, []), (1, 2, [])]), ([], [[0, 1, 2]]))

    def test_complete_strong_triangle_auto(self):
        self.assertEqual(self.groups([(0, 1, []), (1, 2, []), (0, 2, [])]), ([[0, 1, 2]], []))

    def test_keep_survives_growth(self):
        self.assertEqual(self.groups([(0, 1, []), (1, 2, []), (0, 2, [])], keep=[frozenset((1, 2))])[0], [])

    def test_keep_survives_shrink(self):
        self.assertEqual(self.groups([(0, 1, [])], keep=[frozenset((1, 2, 9))])[0], [])

    def test_unrelated_keep_does_not_block(self):
        self.assertEqual(self.groups([(0, 1, [])], keep=[frozenset((1, 9))])[0], [[0, 1]])

    def test_same_complete_street_address_auto(self):
        self.assertTrue(E.build([row(1,address='上海市月光路12号'), row(2,address='月光路12号')])[1])

    def test_same_mall_without_unit_review(self):
        r = E.build([row(1,address='星光广场'), row(2,address='星光广场')])
        self.assertFalse(r[1]); self.assertTrue(r[2])

    def test_same_mall_unit_auto(self):
        r = E.build([row(1,address='星光广场2层201'), row(2,address='星光广场2层201')])
        self.assertTrue(r[1])

    def test_different_units_shared_phone_review(self):
        r = E.build([row(1,address='星光广场2层201',phone='02112345678'), row(2,address='星光广场2层202',phone='02112345678')])
        self.assertFalse(r[1]); self.assertTrue(r[2])

    def test_basement_not_above_ground(self):
        self.assertNotEqual(E.mall_unit('星光广场B1层101'), E.mall_unit('星光广场1层101'))

    def test_shared_landline_alone_review(self):
        r = E.build([row(1,phone='02112345678'), row(2,phone='02112345678')])
        self.assertFalse(r[1]); self.assertTrue(r[2])

    def test_shared_mobile_mall_review(self):
        r = E.build([row(1,address='星光广场',phone='13812345678'), row(2,address='星光广场',phone='13812345678')])
        self.assertFalse(r[1]); self.assertTrue(r[2])

    def test_shared_400_review(self):
        self.assertFalse(E.build([row(1,phone='4001234567'), row(2,phone='4001234567')])[1])

    def test_unrelated_shared_phone_phone_bucket(self):
        r = E.build([row(1,name='星月',phone='02112345678'), row(2,name='海天',phone='02112345678')])
        self.assertFalse(r[1]); self.assertTrue(r[3])

    def test_rename_and_shared_phone_both_visible(self):
        r = E.build([row(1,name='星月',address='星光广场2层201',phone='02112345678'), row(2,name='海天',address='星光广场2层201',phone='02112345678')])
        self.assertFalse(r[1]); self.assertTrue(r[2]); self.assertTrue(r[3])

    def test_far_coordinates_override_address(self):
        with patch.object(E, 'll', side_effect=[(121,31), (122,31)]):
            self.assertFalse(E.build([row(1,address='月光路12号'), row(2,address='月光路12号')])[1])

    def test_shared_center_coordinate_review(self):
        with patch.object(E, 'll', return_value=(121,31)):
            r = E.build([row(1), row(2)])
            self.assertFalse(r[1]); self.assertTrue(r[2])

    def test_placeholder_address_not_strong(self):
        self.assertFalse(E.build([row(1,address='门牌待补12号'), row(2,address='门牌待补12号')])[1])

    def test_keep_adjacent_loaded(self):
        self.assertIn(frozenset((1010,1640)), E.load_keep())

    def test_malformed_keep_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td)/'keep.json'; f.write_text('["1|1"]')
            with patch.object(E, 'KEEP_FILE', str(f)):
                with self.assertRaises(ValueError): E.load_keep()

    def test_apply_blocked_before_fetch_or_write(self):
        with patch.object(sys,'argv',['entity_resolve','--apply','missing.json']), patch.object(E.C,'fetch_all') as fetch, patch.object(E.C,'req') as req:
            with self.assertRaises(SystemExit) as exc: E.main()
            self.assertEqual(exc.exception.code, 2)
            fetch.assert_not_called(); req.assert_not_called()

    def test_plan_dry_run_no_writes(self):
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td)/'plan.json')
            with patch.object(sys,'argv',['entity_resolve','--plan',out]), patch.object(E.C,'fetch_all',return_value=[row(1,address='月光路12号'),row(2,address='月光路12号')]), patch.object(E.C,'req') as req:
                E.main(); req.assert_not_called()
            plan = json.loads(Path(out).read_text())
            self.assertFalse(plan['apply_enabled'])
            self.assertEqual(plan['merge']['1|2']['action'],'review')
            self.assertEqual(plan['merge']['1|2']['bucket'],'AUTO')

if __name__ == '__main__': unittest.main()
