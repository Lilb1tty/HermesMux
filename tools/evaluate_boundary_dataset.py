"""Evaluate the required human-labelled topic-boundary gate without dependencies.

Labels JSONL:      {"id": "case-1", "is_new_topic": true}
Predictions JSONL: {"id": "case-1", "is_new_topic": true, "confidence": 0.97,
                    "status": "ok"}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            case_id = str(row["id"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError(f"{path}:{line_number}: invalid JSONL row") from error
        if case_id in rows:
            raise ValueError(f"{path}:{line_number}: duplicate id {case_id!r}")
        rows[case_id] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.90)
    args = parser.parse_args()
    labels, predictions = _read_jsonl(args.labels), _read_jsonl(args.predictions)
    if len(labels) < 200:
        raise ValueError("quality gate requires at least 200 human-labelled samples")
    if set(labels) != set(predictions):
        raise ValueError("labels and predictions must have exactly the same ids")

    true_positive = false_positive = false_negative = errors_that_switched = 0
    for case_id, label in labels.items():
        expected = label.get("is_new_topic")
        if expected not in {True, False} or not isinstance(expected, bool):
            raise ValueError(f"label {case_id!r} must contain boolean is_new_topic")
        prediction = predictions[case_id]
        confidence = prediction.get("confidence", 0)
        requested_switch = (
            prediction.get("is_new_topic") is True
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and confidence >= args.threshold
        )
        switched = prediction.get("status", "ok") == "ok" and requested_switch
        if prediction.get("status", "ok") != "ok" and requested_switch:
            errors_that_switched += 1
        if expected is True and switched:
            true_positive += 1
        elif expected is True:
            false_negative += 1
        elif switched:
            false_positive += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    result = {
        "samples": len(labels), "precision": precision, "recall": recall,
        "false_positives": false_positive, "false_negatives": false_negative,
        "error_switches": errors_that_switched,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if precision >= 0.95 and recall >= 0.60 and errors_that_switched == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"quality gate error: {error}", file=sys.stderr)
        raise SystemExit(2)
