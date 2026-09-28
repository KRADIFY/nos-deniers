import sqlite3
import unittest
from budget_service.events import select
from budget_service.normalize_validated import check_preserved


class ValidatedPipelineTests(unittest.TestCase):
    def test_rebuild_refuses_lost_or_changed_observations_and_duplicate_loss(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('create table facts(year integer,cents integer)')
            db.executemany('insert into facts values (?,?)', [(2021,100),(2021,100),(2026,0)])
            check_preserved(db, [(2021,100),(2021,100),(2026,0),(2026,20)])
            for rows in [[(2021,100),(2026,0)],[(2021,101),(2021,100),(2026,0)]]:
                with self.assertRaisesRegex(ValueError, 'Base servie conservée'):
                    check_preserved(db, rows)

    def event(self, amount=10000):
        return dict(year=2024,budget='BG',measure='CP',mission='TA',program='174',amount_cents=amount,
                    sign=-1,publication_date='2024-02-22',act_id='act',action='',subaction='')

    def params(self, **changes):
        return dict(start=2024,end=2024,budget='BG',measure='CP',scope='TA',exclude=[],constant=False,base=2025,topic='',**changes)

    def test_events_keep_sign_missing_and_explicit_zero_distinct(self):
        for amount, expected, status in [(10000,-100,'published'),(0,0,'published'),(None,None,'not_reported')]:
            r=select([self.event(amount)],self.params(),{})[0]
            self.assertEqual((r['value'],r['status']),(expected,status))

    def test_event_cannot_be_allocated_to_action_or_policy(self):
        base=self.params()
        for changes in [dict(scope='TA/174/01'),dict(exclude=['TA/174/01']),dict(topic='maprimerenov')]:
            r=select([self.event()],dict(base,**changes),{})[0]
            self.assertEqual(r['status'],'detail_unavailable');self.assertIsNone(r['value'])
        self.assertEqual(select([self.event()],dict(base,exclude=['TA/174']),{}),[])

    def test_annulation_in_constant_euros_is_converted_once(self):
        r=select([self.event()],dict(self.params(),constant=True),{2024:'100',2025:'110'})[0]
        self.assertEqual(r['value'],-110)


if __name__=='__main__':unittest.main()
