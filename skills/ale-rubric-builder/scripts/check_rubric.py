"""Read-only draft checks. Exit 0: PASS_DRAFT, 1: FAIL, 2: BLOCKED.

Use the bundled weight checker with the documented draft weight profile.
No scoring, weight tuning, remote access, or production acceptance is performed.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


FIELDS = {"id", "source", "label", "description", "hard_gate", "priority"}
BASIS_FIELDS = {"source", "file", "locator", "quote", "justification"}
REVIEW_FIELDS = {"rubric_sha256", "basis", "methods"}
EXIT_CODES = {"PASS_DRAFT": 0, "FAIL": 1, "BLOCKED": 2}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def load_weight_checker():
    path = Path(__file__).resolve().with_name("judge_weight_check.py")
    spec = importlib.util.spec_from_file_location("_ale_draft_weight_core", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def validate_contract(rows):
    require(isinstance(rows, list) and bool(rows), "expected a nonempty rubric array")
    ids, descriptions = set(), set()
    for index, item in enumerate(rows, 1):
        require(isinstance(item, dict), f"item {index}: expected an object")
        require(set(item) == FIELDS, f"item {index}: expected exactly the six rubric fields")
        rid = item["id"]
        require(text(rid) and rid == rid.strip(), f"item {index}: invalid id")
        require(rid not in ids, f"duplicate id: {rid}")
        ids.add(rid)
        require(text(item["description"]), f"{rid}: empty description")
        description = " ".join(item["description"].split())
        require(description not in descriptions, f"{rid}: duplicate description")
        descriptions.add(description)
        for field, choices in (
            ("source", {"expert", "model", "user"}),
            ("priority", {"critical", "important"}),
            ("label", {"deterministic", "non-deterministic"}),
        ):
            require(isinstance(item[field], str) and item[field] in choices,
                    f"{rid}: invalid {field}")
        require(type(item["hard_gate"]) is bool, f"{rid}: hard_gate must be boolean")
        require(not item["hard_gate"] or item["label"] == "deterministic",
                f"{rid}: a non-deterministic criterion cannot be a hard gate")
    return ids


def validate_basis(basis, ids, directory):
    require(isinstance(basis, dict) and set(basis) == ids,
            "basis must cover exactly all rubric IDs")
    source_texts = {}
    for rid, refs in basis.items():
        require(isinstance(refs, list) and bool(refs), f"{rid}: missing Query/Input basis")
        for ref in refs:
            require(isinstance(ref, dict) and set(ref) == BASIS_FIELDS,
                    f"{rid}: expected source/file/locator/quote/justification")
            require(all(text(ref[field]) for field in BASIS_FIELDS), f"{rid}: empty basis field")
            require(ref["source"] in {"query", "input"},
                    f"{rid}: only Query/Input may authorize a requirement")
            path = (directory / ref["file"]).resolve()
            if path not in source_texts:
                source_texts[path] = path.read_text(encoding="utf-8-sig")
            require(ref["quote"] in source_texts[path], f"{rid}: quote not found in declared source")


def check_files(rubric_path, review_path=None):
    core = load_weight_checker()
    rubric_path = Path(rubric_path)
    rows = core.read_json(rubric_path)
    ids = validate_contract(rows)
    sha = hashlib.sha256(rubric_path.read_bytes()).hexdigest()
    if review_path is not None:
        review_path = Path(review_path)
        review = core.read_json(review_path)
        require(isinstance(review, dict) and set(review) == REVIEW_FIELDS,
                "draft review requires exactly rubric_sha256, basis, methods")
        require(review["rubric_sha256"] == sha, "stale/missing rubric_sha256")
        validate_basis(review["basis"], ids, review_path.resolve().parent)
        methods = review["methods"]
        basis_status = "PASS_DECLARED_QUOTES"
    else:
        methods = {rid: {"dependency": "unknown", "confirmed": False, "evidence": ""} for rid in ids}
        basis_status = "NOT_REVIEWED"

    # This fixed draft profile does not attest the target evaluator configuration.
    weights = {row["id"]: 2 if row["priority"] == "critical" else 1 for row in rows}
    review = {
        "rubric_sha256": sha,
        "weights": weights,
        "weight_source": "Bundled draft profile: critical=2, important=1",
        "aggregation": {
            "kind": "normalized_weighted_sum",
            "confirmed": True,
            "evidence": "Draft profile: normalized weighted sum with code-only hard gates",
        },
        "methods": methods,
    }
    budget = core.check(rows, review, sha)
    status = "PASS_DRAFT" if budget["status"] == "PASS_PREFLIGHT" else budget["status"]
    return {
        "status": status,
        "contract_status": "PASS",
        "basis_status": basis_status,
        "rubric_sha256": sha,
        "draft_weight_check": budget,
        "scope": "Six-field schema, declared source quotes, and draft weighted budget only; "
                 "not semantic coverage, tool execution, model scores, or production acceptance",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rubric", type=Path)
    parser.add_argument("--review", type=Path, help="Local draft basis/method declarations")
    args = parser.parse_args(argv)
    try:
        report = check_files(args.rubric, args.review)
    except (OSError, ImportError, UnicodeError) as exc:
        report = {"status": "BLOCKED", "error": str(exc)}
    except (ValueError, TypeError, KeyError) as exc:
        report = {"status": "FAIL", "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
