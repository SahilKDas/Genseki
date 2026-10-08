"""Public evidence must not disclose host paths or mutate private evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'))
from report_schema7 import public_report
from genseki.artifacts import _private


class PublicationTests(unittest.TestCase):
    def test_relative_paths_and_original_unchanged(self):
        original=dict(frozen=dict(files={'model':dict(source=str(ROOT/'Nu/work/model.nnue'),sha256='abc')}),
                      diagnostic=str(ROOT/'Nu/work/report.json'))
        before=copy.deepcopy(original);published=public_report(original)
        self.assertEqual(published['frozen']['files']['model']['source'],'Nu/work/model.nnue')
        self.assertEqual(published['frozen']['files']['model']['sha256'],'abc')
        self.assertEqual(original,before)
        self.assertFalse(_private(published))

    def test_actual_campaign_has_no_host_metadata(self):
        report=json.loads((ROOT/'Nu/reports/schema7/campaign.json').read_text())
        self.assertFalse(_private(report))
        self.assertFalse(_private(public_report(report)))


if __name__=='__main__':unittest.main()
