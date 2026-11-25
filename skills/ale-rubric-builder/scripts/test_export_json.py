import unittest
from export_json import export


class ExportTest(unittest.TestCase):
    def test_preserves_six_fields_and_versions_host_output(self):
        rows = [{'id': 'r1', 'source': 'expert', 'label': 'deterministic',
                 'description': 'Output contains the requested sheet.', 'hard_gate': False, 'priority': 'critical'}]
        result = export(rows, 'Confirmed')
        self.assertEqual(result['schema'], 'ale-rubric-result/v1')
        self.assertEqual(result['rubrics'], rows)
        self.assertNotIn('signature', result)
        with self.assertRaises(ValueError):
            export([{**rows[0], 'signature': 'fake'}], 'Confirmed')


if __name__ == '__main__':
    unittest.main()
