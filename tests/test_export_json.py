import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / 'skills' / name / 'scripts/export_json.py' for name in ['ale-task-interviewer', 'ale-reference-interviewer']]
DRAFT = {'title': 'Fixture', 'software': ['Blender'], 'softwareVersion': '5.0', 'description': '', 'prompt': 'Create a cube', 'economicValue': 'Confirmed use', 'steps': 'Confirmed steps', 'criteria': [], 'rubrics': []}


class ExportTest(unittest.TestCase):
    def test_independent_packages_match(self):
        self.assertEqual(SCRIPTS[0].read_bytes(), SCRIPTS[1].read_bytes())

    def test_cli_preserves_draft_and_refuses_overwrite(self):
        for script in SCRIPTS:
            with tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder) / 'draft.json', Path(folder) / 'response.json'
                source.write_text(json.dumps(DRAFT), encoding='utf-8')
                command = [sys.executable, str(script), str(source), str(output), '--reply', 'Confirmed']
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(json.loads(output.read_text(encoding='utf-8')), {'reply': 'Confirmed', 'draft': DRAFT})
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual(json.loads(source.read_text()), DRAFT)

    def test_rejects_missing_facts_and_invalid_weights(self):
        spec = importlib.util.spec_from_file_location('export_json', SCRIPTS[0])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for patch in [{'prompt': ''}, {'software': []}, {'signature': 'forged'}, {'criteria': [{'id': 'A', 'requirement': '', 'evidence': '', 'method': '', 'hardGate': False, 'weight': float('nan')}]}]:
            with self.assertRaises(ValueError):
                module.validate({**copy.deepcopy(DRAFT), **patch})


if __name__ == '__main__':
    unittest.main()
