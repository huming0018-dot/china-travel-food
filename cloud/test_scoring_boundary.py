"""Offline: cd cloud && python -m unittest -v test_scoring_boundary."""
import contextlib
import datetime
import importlib.util
import io
import pathlib
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch

PIPE = pathlib.Path(__file__).parent / 'vendor' / 'pipeline'
sys.path.insert(0, str(PIPE))
from scoring_calculation import compute, taste_val

TODAY = datetime.date(2026, 11, 17)

def review(**kw):
    row = dict(restaurant_id=1, review_kind='diner', is_fake_suspect=False,
               is_hidden=False, trust_level='high', aspect_taste=5,
               visit_date=TODAY.isoformat(), author_name='a')
    row.update(kw)
    return row

def restaurant(**kw):
    row = dict(id=1, name='fixture', score_objective=None, score_endorsement=None,
               soft_ad_penalty=0, score_evidence_level='insufficient',
               score_taste=None, score_diner=None, review_count=0,
               review_confidence=0, score_total=50)
    row.update(kw)
    return row

def score(rows, restaurants=None, links=None, cuisines=None, **kw):
    args = dict(reference_date=TODAY, half_life=180.0, prior_strength=8.0)
    args.update(kw)
    return compute(rows, restaurants or [restaurant()], links or [], cuisines or [], **args)

class ScoringBoundaryTests(unittest.TestCase):
    def test_pure_import_no_database_or_network(self):
        subprocess.run([sys.executable, '-I', '-c', f'''
import sys
sys.path.insert(0, {str(PIPE.resolve())!r})
class Block:
 def find_spec(self, fullname, *args):
  if fullname in ('common', 'requests', 'scoring_engine'):
   raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import scoring_calculation
'''], check=True)

    def test_empty_evidence_and_authority_fallback(self):
        pred, n = score([])
        self.assertEqual(n, 0)
        self.assertEqual(pred[1], dict(taste=None, diner=None, count=0, conf=0,
                                      nind=0, evidence='insufficient', total=None))
        pred, _ = score([], [restaurant(score_objective=100, score_endorsement=100)])
        self.assertEqual((pred[1]['total'], pred[1]['evidence']), (70, 'provisional'))

    def test_review_filters_and_rating_fallback(self):
        excluded = [review(review_kind='ad'), review(is_fake_suspect=True),
                    review(is_hidden=True), review(trust_level='low'),
                    review(aspect_taste=None)]
        pred, n = score(excluded + [review(aspect_taste=None, rating_total=5)])
        self.assertEqual((n, pred[1]['count']), (1, 1))
        self.assertEqual(taste_val(dict(aspect_taste=2, rating_taste=4)), 2)
        self.assertEqual((pred[1]['taste'], pred[1]['diner'], pred[1]['conf']),
                         (73.33, 100.0, 0.111))

    def test_explicit_date_decay_and_independent_authors(self):
        rows = [review(), review(author_name='b', aspect_taste=1,
                                visit_date=(TODAY-datetime.timedelta(days=180)).isoformat())]
        pred, n = score(rows)
        self.assertEqual((n, pred[1]['nind'], pred[1]['evidence']), (2, 2, 'verified'))
        self.assertEqual((pred[1]['diner'], pred[1]['taste'], pred[1]['conf']), (66.67, 69.47, 0.158))
        later, _ = score(rows, reference_date=TODAY+datetime.timedelta(days=180))
        self.assertLess(later[1]['conf'], pred[1]['conf'])
        self.assertEqual(score([review(visit_date='invalid')]), score([review()]))

    def test_cuisine_prior_and_penalty(self):
        cuisines=[dict(id=10,name='leaf',dimension='菜系',parent_category='parent'),
                  dict(id=20,name='parent',dimension='菜系',parent_category=None)]
        links=[dict(restaurant_id=1,cuisine_id=10,is_primary=True)]
        pred, _=score([review()], links=links, cuisines=cuisines)
        self.assertEqual(pred[1]['taste'], 100)
        penalized, _=score([review()], [restaurant(soft_ad_penalty=200)], links, cuisines)
        self.assertEqual(penalized[1]['total'], 0)

    def test_real_batch_default_dry_run_and_compatibility(self):
        db=types.ModuleType('common')
        tables={'restaurants':[restaurant()], 'reviews':[review()],
                'restaurant_cuisines':[], 'cuisines':[]}
        db.fetch_all=Mock(side_effect=lambda table,*a,**kw: tables[table])
        db.req=Mock(side_effect=AssertionError('write attempted'))
        with patch.dict(sys.modules, {'common':db}):
            spec=importlib.util.spec_from_file_location('scoring_engine_fixture', PIPE/'scoring_engine.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.REF_DATE=TODAY
            self.assertIs(module.taste_val, taste_val)
            self.assertEqual(module.compute([review()],[restaurant()],[],[]),score([review()]))
            module.HALF_LIFE, module.M = 90.0, 4.0
            self.assertEqual(module.compute([review()],[restaurant()],[],[]),
                             score([review()], half_life=90.0, prior_strength=4.0))
            module.HALF_LIFE, module.M = 180.0, 8.0
            output=io.StringIO()
            with patch.object(sys,'argv',['scoring_engine.py']), contextlib.redirect_stdout(output):
                module.main()
            self.assertIn('[dry-run] 未写库', output.getvalue())
            self.assertIn('有效口味证据行 1', output.getvalue())
            self.assertEqual(db.fetch_all.call_count,4)
            db.req.assert_not_called()

if __name__ == '__main__':
    unittest.main()
