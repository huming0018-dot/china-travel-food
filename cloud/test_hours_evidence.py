import datetime as dt
import unittest
from hours_evidence import evidence, parse_hours, resolve
from opening_hours_backfill import audit, approved, Budget

class HoursTests(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(len(parse_hours('每日 11:00-22:00')['weekly']), 7)
    def test_overnight(self):
        self.assertTrue(parse_hours('每天 18:00-02:00')['weekly'][0]['overnight'])
    def test_ambiguous(self):
        for s in ('11:00-22:00', '周一休息', '每天 11:00-22:00 节假日除外', '每日 25:00-26:00', '每日 10:00-10:00'):
            self.assertIsNone(parse_hours(s))
    def test_conflict(self):
        rows = [self.row('每日 11:00-22:00'), self.row('每日 12:00-22:00')]
        self.assertEqual(resolve(rows)['action'], 'hold')
    def row(self, raw):
        v = evidence(raw, 'https://example.org/shop', 'official_restaurant', 'exact_name_and_address')
        return {'value': v, 'source_url': v['source_url'], 'confidence': .9}
    def test_valid(self):
        self.assertEqual(resolve([self.row('每日 11:00-22:00')])['action'], 'apply')
    def test_stale(self):
        row = self.row('每日 11:00-22:00')
        row['value']['captured_at'] = (dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=31)).isoformat()
        self.assertEqual(resolve([row])['action'], 'hold')
    def test_legacy(self):
        self.assertEqual(resolve([{'value': {'raw': '每日 11:00-22:00'}}])['action'], 'hold')
    def test_tampered(self):
        row=self.row('每日 11:00-22:00'); row['value']['parsed']['weekly'][0]['opens']='09:00'
        self.assertEqual(resolve([row])['action'], 'hold')
    def test_g2_excluded(self):
        row=dict(id=1,status='active',phone='02112345678',price_avg=100,location='point',opening_hours={'raw':'existing'},review_count=0)
        self.assertEqual(audit([row])['map_queue'],0)
        row['opening_hours']=None
        self.assertEqual(audit([row])['hours_fraction_in_queue'],1)
    def test_access_default_closed(self):
        self.assertFalse(approved({'url':'https://example.org/shop'}))
    def test_budget(self):
        b=Budget(1); b.take()
        with self.assertRaises(RuntimeError): b.take()

if __name__ == '__main__':
    unittest.main()
