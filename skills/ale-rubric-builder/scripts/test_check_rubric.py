"""Synthetic draft-check regressions. No real task scoring or remote actions."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from check_rubric import check_files, validate_contract


class DraftCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rubric = self.root / "rubric.json"
        self.review = self.root / "review.json"
        self.query = self.root / "query.txt"
        self.query.write_text("Deliver columns c0 through c9.", encoding="utf-8")
        self.rows = [
            {"id": f"r{i}", "source": "expert", "label": "deterministic",
             "description": f"Check that column c{i} is present.",
             "hard_gate": False, "priority": "important"}
            for i in range(10)
        ]
        self.plan = {
            "rubric_sha256": "",
            "basis": {row["id"]: [{"source": "query", "file": "query.txt", "locator": "line 1",
                                   "quote": "Deliver columns c0 through c9.",
                                   "justification": "Explicit required column."}] for row in self.rows},
            "methods": {row["id"]: {"dependency": "code", "confirmed": True,
                                     "evidence": "Synthetic deterministic reader."} for row in self.rows},
        }

    def save(self):
        self.rubric.write_text(json.dumps(self.rows), encoding="utf-8")
        self.plan["rubric_sha256"] = hashlib.sha256(self.rubric.read_bytes()).hexdigest()
        self.review.write_text(json.dumps(self.plan), encoding="utf-8")

    def result(self):
        self.save()
        return check_files(self.rubric, self.review)

    def model(self, count, dependency="judge"):
        for row in self.rows[:count]:
            self.plan["methods"][row["id"]]["dependency"] = dependency

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8",
                               str(Path(__file__).with_name("check_rubric.py")),
                               str(self.rubric), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", check=False)

    def test_pure_code_passes_draft(self):
        report = self.result()
        self.assertEqual(report["status"], "PASS_DRAFT")
        self.assertEqual(report["basis_status"], "PASS_DECLARED_QUOTES")
        self.assertEqual(report["draft_weight_check"]["known_model_weight_share"], "0")

    def test_exact_thirty_passes(self):
        self.model(3)
        report = self.result()
        self.assertEqual(report["status"], "PASS_DRAFT")
        self.assertEqual(report["draft_weight_check"]["known_model_weight_share"], "0.3")

    def test_above_thirty_fails(self):
        self.model(4)
        self.assertEqual(self.result()["status"], "FAIL")

    def test_critical_weight_not_item_count(self):
        self.model(3)
        self.rows[0]["priority"] = "critical"
        report = self.result()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["draft_weight_check"]["total_weight"], "11")

    def test_mixed_and_agent_count_full_weight(self):
        for dependency in ("mixed", "agent"):
            with self.subTest(dependency=dependency):
                self.model(4, dependency)
                self.assertEqual(self.result()["status"], "FAIL")

    def test_unknown_is_not_code(self):
        self.model(1, "unknown")
        report = self.result()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["draft_weight_check"]["model_weight_share_upper"], "0.1")

    def test_unconfirmed_tool_is_unknown(self):
        self.plan["methods"]["r0"]["confirmed"] = False
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_no_evidence_cannot_confirm_tool(self):
        self.plan["methods"]["r0"]["evidence"] = " "
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_schema_alone_cannot_pass_budget(self):
        self.save()
        report = check_files(self.rubric)
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["basis_status"], "NOT_REVIEWED")

    def test_reference_or_rollout_cannot_authorize_requirement(self):
        for source in ("reference", "rollout", "expert"):
            with self.subTest(source=source):
                self.plan["basis"]["r0"][0]["source"] = source
                with self.assertRaisesRegex(ValueError, "only Query/Input"):
                    self.result()

    def test_input_source_and_relative_path(self):
        self.plan["basis"]["r0"][0]["source"] = "input"
        self.assertEqual(self.result()["status"], "PASS_DRAFT")

    def test_invented_quote_rejected(self):
        self.plan["basis"]["r0"][0]["quote"] = "Place title at top left."
        with self.assertRaisesRegex(ValueError, "quote not found"):
            self.result()

    def test_incomplete_basis_rejected(self):
        del self.plan["basis"]["r0"]
        with self.assertRaisesRegex(ValueError, "basis must cover"):
            self.result()

    def test_empty_justification_rejected(self):
        self.plan["basis"]["r0"][0]["justification"] = ""
        with self.assertRaisesRegex(ValueError, "empty basis"):
            self.result()

    def test_stale_review_rejected(self):
        self.save()
        self.rubric.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "rubric_sha256"):
            check_files(self.rubric, self.review)

    def test_missing_method_rejected(self):
        del self.plan["methods"]["r0"]
        with self.assertRaisesRegex(ValueError, "methods must cover"):
            self.result()

    def test_subjective_gate_rejected(self):
        self.rows[0].update(hard_gate=True, label="non-deterministic")
        with self.assertRaisesRegex(ValueError, "hard gate"):
            self.result()

    def test_model_localization_gate_fails_even_with_deterministic_label(self):
        self.rows[0]["hard_gate"] = True
        self.model(1, "mixed")
        self.assertEqual(self.result()["status"], "FAIL")

    def test_unknown_gate_blocks(self):
        self.rows[0]["hard_gate"] = True
        self.model(1, "unknown")
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_duplicate_id_rejected(self):
        self.rows[1]["id"] = self.rows[0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            validate_contract(self.rows)

    def test_duplicate_criterion_rejected(self):
        self.rows[1]["description"] = self.rows[0]["description"] + "  "
        with self.assertRaisesRegex(ValueError, "duplicate description"):
            validate_contract(self.rows)

    def test_extra_weight_and_noncontract_fields_rejected(self):
        self.rows[0]["weight"] = 10
        with self.assertRaisesRegex(ValueError, "six rubric fields"):
            validate_contract(self.rows)
        with self.assertRaisesRegex(ValueError, "six rubric fields"):
            validate_contract([{"criterion": "test", "weight": 1}])

    def test_invalid_enums_and_gate_types(self):
        for field, value in (("source", "invalid-source"), ("priority", "urgent"), ("label", []),
                             ("hard_gate", "false"), ("id", 1), ("description", " ")):
            with self.subTest(field=field):
                original = self.rows[0][field]
                self.rows[0][field] = value
                with self.assertRaises(ValueError):
                    validate_contract(self.rows)
                self.rows[0][field] = original

    def test_empty_array_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonempty"):
            validate_contract([])

    def test_extra_weight_override_rejected(self):
        self.plan["weights"] = {row["id"]: 1 for row in self.rows}
        with self.assertRaisesRegex(ValueError, "exactly rubric_sha256"):
            self.result()

    def test_cli_read_only_and_exit_codes(self):
        for count, expected in ((0, 0), (4, 1)):
            self.model(count)
            self.save()
            before = {p.name: p.read_bytes() for p in self.root.iterdir()}
            process = self.cli("--review", self.review)
            self.assertEqual(process.returncode, expected, process.stderr)
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(self.cli().returncode, 2)

    def test_cli_missing_file_blocks(self):
        self.save()
        self.query.unlink()
        process = self.cli("--review", self.review)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "BLOCKED")

    def test_duplicate_json_key_rejected(self):
        self.rubric.write_text('[{"id":"r1","id":"r2"}]', encoding="utf-8")
        process = self.cli()
        self.assertEqual(process.returncode, 1)
        self.assertIn("duplicate JSON key", process.stdout)

    def isolated_cli(self, script, *args):
        package = self.root / "isolated-skill"
        if not package.exists():
            shutil.copytree(Path(__file__).resolve().parents[1], package,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        workspace = self.root / "unrelated-workspace"
        workspace.mkdir(exist_ok=True)
        return subprocess.run([sys.executable, "-I", "-B", "-X", "utf8",
                               str(package / "scripts" / script), *map(str, args)],
                              cwd=workspace, capture_output=True, text=True,
                              encoding="utf-8", check=False)

    def test_portable_draft_checker_from_unrelated_directory(self):
        self.model(3)
        self.save()
        process = self.isolated_cli("check_rubric.py", self.rubric, "--review", self.review)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["status"], "PASS_DRAFT")
        self.assertEqual(report["draft_weight_check"]["known_model_weight_share"], "0.3")

    def test_missing_bundled_checker_does_not_search_other_projects(self):
        self.save()
        self.isolated_cli("check_rubric.py", self.rubric, "--review", self.review)
        (self.root / "isolated-skill" / "scripts" / "judge_weight_check.py").unlink()
        process = self.isolated_cli("check_rubric.py", self.rubric, "--review", self.review)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "BLOCKED")

    def test_portable_actual_weight_checker_uses_toml_weights(self):
        self.model(3)
        config = self.root / "evaluator.toml"
        review = self.root / "actual-review.json"
        for first_weight, expected in ((1, 0), (2, 1)):
            with self.subTest(first_weight=first_weight):
                config.write_text("\n".join(
                    f"[rubrics.r{i}]\nweight = {first_weight if i == 0 else 1}\nhard_gate = false\n"
                    for i in range(10)), encoding="utf-8")
                actual = {
                    "rubric_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                    "weight_source": "Synthetic TOML with explicit weights",
                    "aggregation": {"kind": "normalized_weighted_sum", "confirmed": True,
                                    "evidence": "Synthetic normalized scoring contract"},
                    "methods": self.plan["methods"],
                }
                review.write_text(json.dumps(actual), encoding="utf-8")
                process = self.isolated_cli("judge_weight_check.py", config, "--review", review)
                self.assertEqual(process.returncode, expected, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
