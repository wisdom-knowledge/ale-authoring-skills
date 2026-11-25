"""Read-only 30% model-dependent weight preflight; Python 3.11+, stdlib only.

Exit 0: PASS_PREFLIGHT, 1: FAIL, 2: BLOCKED (including invalid input).
Does not execute an evaluator or attest the truth of reviewer declarations.
"""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys
import tomllib

MODEL = {"judge", "agent", "mixed"}
DEPENDENCIES = MODEL | {"code", "unknown"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object, parse_float=Decimal)


def read_rubrics(path):
    path = Path(path)
    if path.suffix.lower() == ".toml":
        with path.open("rb") as stream:
            return tomllib.load(stream, parse_float=Decimal)
    return read_json(path)


def number(value, label):
    require(type(value) in (int, float, Decimal), f"{label}: numeric value required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label}: invalid number") from exc
    require(result.is_finite() and result >= 0, f"{label}: finite nonnegative number required")
    return result


def normalize(data):
    if isinstance(data, dict):
        mapping = data.get("rubrics")
        require(isinstance(mapping, dict), "expected top-level rubrics mapping")
        data = []
        for rid, value in mapping.items():
            require(isinstance(value, dict), f"{rid}: expected rubric object")
            require("id" not in value or value["id"] == rid, f"{rid}: conflicting id")
            data.append(dict(value, id=rid))
    require(isinstance(data, list) and data, "expected nonempty rubric array")
    seen = set()
    for item in data:
        require(isinstance(item, dict), "rubric must be an object")
        rid = item.get("id")
        require(isinstance(rid, str) and rid.strip(), "id must be a nonempty string")
        require(rid not in seen, f"duplicate rubric id: {rid}")
        seen.add(rid)
        require(type(item.get("hard_gate")) is bool, f"{rid}: hard_gate must be boolean")
        if "weight" in item:
            number(item["weight"], f"{rid}.weight")
        if "uses_model" in item:
            require(type(item["uses_model"]) is bool, f"{rid}: uses_model must be boolean")
    return data


def check(data, review, sha256):
    rows = normalize(data)
    ids = {row["id"] for row in rows}
    require(isinstance(review, dict), "review must be an object")
    require(review.get("rubric_sha256") == sha256, "stale/missing rubric_sha256")
    methods = review.get("methods")
    require(isinstance(methods, dict) and set(methods) == ids,
            "methods must cover exactly all rubric IDs")
    weight_map = review.get("weights")
    if weight_map is not None:
        require(isinstance(weight_map, dict) and set(weight_map) == ids,
                "weights must cover exactly all rubric IDs")
        for rid, value in weight_map.items():
            number(value, f"weights.{rid}")
    issues, failures, contributions = [], [], []
    weight_source = review.get("weight_source")
    if not isinstance(weight_source, str) or not weight_source.strip():
        issues.append("missing weight_source: identify approved weights/parser/version")
    aggregation = review.get("aggregation", {})
    require(isinstance(aggregation, dict), "aggregation must be an object")
    if not (aggregation.get("kind") == "normalized_weighted_sum"
            and aggregation.get("confirmed") is True
            and isinstance(aggregation.get("evidence"), str)
            and aggregation["evidence"].strip()):
        issues.append("unverified aggregation: normalized weights, scoring scale and hard-gate effects need runtime evidence")
    missing, known_model, direct_judge, unknown, total = [], Decimal(0), Decimal(0), Decimal(0), Decimal(0)
    for item in rows:
        rid = item["id"]
        method = methods[rid]
        require(isinstance(method, dict), f"{rid}: method must be an object")
        dep = method.get("dependency")
        require(dep in DEPENDENCIES, f"{rid}: invalid dependency")
        require(type(method.get("confirmed")) is bool, f"{rid}: confirmed must be boolean")
        evidence = method.get("evidence")
        require(isinstance(evidence, str), f"{rid}: evidence must be a string")
        confirmed = method["confirmed"] and bool(evidence.strip())
        effective = dep if confirmed else "unknown"
        # Existing configuration can establish model use, never prove its absence.
        source_model = item.get("uses_model") is True or item.get("mode") == "主观"
        if source_model and effective not in MODEL:
            effective = "mixed"
            issues.append(f"{rid}: source declares model use; review does not match")
        if effective == "unknown":
            issues.append(f"{rid}: dependency is unverified/unknown")
        if item["hard_gate"] and effective in MODEL:
            failures.append(f"{rid}: model-dependent hard_gate (even at zero weight)")
        elif item["hard_gate"] and effective == "unknown":
            issues.append(f"{rid}: hard_gate dependency not verified")
        value = item.get("weight")
        if weight_map is not None:
            mapped = weight_map[rid]
            require(value is None or number(value, rid) == number(mapped, rid),
                    f"{rid}: weight map conflicts with rubric weight")
            value = mapped
        if value is None:
            missing.append(rid)
            weight = None
        else:
            weight = number(value, f"{rid}.weight")
            total += weight
            if effective in MODEL:
                known_model += weight
            if effective == "judge":
                direct_judge += weight
            if effective == "unknown":
                unknown += weight
        contributions.append({"id": rid, "weight": str(weight) if weight is not None else None,
                              "declared_dependency": dep, "effective_dependency": effective,
                              "hard_gate": item["hard_gate"],
                              "model_weight": str(weight) if weight is not None and effective in MODEL else
                              ("0" if effective == "code" else None)})
    lower = upper = direct = None
    if missing:
        issues.append("missing numeric weights: " + ", ".join(missing))
    elif total <= 0:
        issues.append("total weight must be positive")
    else:
        lower = str(known_model / total)
        upper = str((known_model + unknown) / total)
        direct = str(direct_judge / total)
        if known_model * 10 > total * 3:
            failures.append("known model-dependent weight exceeds 30%")
        for row in contributions:
            row["total_weight_share"] = str(Decimal(row["weight"]) / total)
    status = "FAIL" if failures else "BLOCKED" if issues else "PASS_PREFLIGHT"
    return {"status": status, "limit": "0.30", "rubric_count": len(rows),
            "rubric_sha256": sha256, "policy": "conservative: judge/agent/mixed count full rubric weight",
            "total_weight": str(total) if not missing else None,
            "known_model_weight_share": lower, "model_weight_share_upper": upper,
            "direct_judge_only_share": direct, "missing_weight_ids": missing,
            "failures": failures, "blockers": issues, "contributions": contributions,
            "scope": "Declared-method preflight only; not evaluator validity/stability certification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rubric", type=Path)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="New local JSON report; never overwrite existing files")
    args = parser.parse_args()
    try:
        if args.report and args.report.exists():
            raise ValueError("report already exists; choose a new local filename")
        sha = hashlib.sha256(args.rubric.read_bytes()).hexdigest()
        report = check(read_rubrics(args.rubric), read_json(args.review), sha)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        report = {"status": "BLOCKED", "input_error": str(exc)}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report and not args.report.exists():
        try:
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
        except OSError:
            print("Report could not be written; no existing file overwritten.", file=sys.stderr)
            return 2
    return {"PASS_PREFLIGHT": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
