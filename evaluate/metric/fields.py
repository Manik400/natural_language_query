from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from copy import deepcopy

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        sys.exit(f"[ERROR] File not found: {path}")
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print(f"[WARN] Skipping malformed JSON at line {lineno}: {exc}")
    return records


def extract_events(response) -> list[dict]:
    """
    Normalise the response field into a list of event dicts.
    Handles both list-style (fields tool) and dict-style (events tool) payloads.
    """
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        return response.get("matched_events", [])
    return []


def normalise_value(v) -> str:
    """Stringify a field value for comparison."""
    if v is None:
        return ""
    return str(v).strip().lower()


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def build_dataset(predictions_path: str, ground_truth_path: str) -> list[dict]:
    """
    Merge predictions and ground-truth by query string.

    Returns:
      [
        {
          "query":     str,
          "predicted": [ {event_name, relevant_fields:[{field,operator,value,...}]} ],
          "gold":      [ {event_name, relevant_fields:[{field,operator,value,...}]} ],
          "reviewed":  bool,
        },
        ...
      ]
    """
    raw_preds = load_jsonl(predictions_path)
    raw_gold = load_jsonl(ground_truth_path)

    gold_map: dict[str, dict] = {}
    for item in raw_gold:
        q = item.get("query", "").strip()
        if q:
            gold_map[q] = item

    dataset, skipped = [], 0
    for item in raw_preds:
        query = item.get("query", "").strip()
        if not query:
            skipped += 1
            continue

        gold_item = gold_map.get(query)
        if gold_item is None:
            skipped += 1
            continue

        pred_events = extract_events(deepcopy(item.get("response", [])))
        gold_events = extract_events(
            deepcopy(gold_item.get("corrected_response") or [])
        )

        dataset.append(
            {
                "query": query,
                "predicted": pred_events,
                "gold": gold_events,
                "reviewed": gold_item.get("reviewed", False),
            }
        )

    print(
        f"[INFO] Loaded {len(dataset)} matched pairs  ({skipped} skipped / unmatched)."
    )
    return dataset


# ---------------------------------------------------------------------------
# Field-level confusion counting
# ---------------------------------------------------------------------------

FieldKey = tuple  # (event_name, field_name, [operator,] [value,])


def make_field_key(
    event_name: str,
    field_name: str,
    operator: str | None,
    value,
    match_operator: bool,
    match_value: bool,
) -> FieldKey:
    """
    Build the comparison key for a single relevant_field entry.
    By default only (event_name, field_name) must match for a TP.
    Optionally include operator and/or value in the key.
    """
    parts: list = [event_name.strip(), field_name.strip()]
    if match_operator:
        parts.append((operator or "").strip())
    if match_value:
        parts.append(normalise_value(value))
    return tuple(parts)


def fields_to_multiset(
    events: list[dict],
    match_operator: bool,
    match_value: bool,
) -> dict[FieldKey, int]:
    """Convert a list of event dicts to a {key: count} multiset of field assertions."""
    counts: dict[FieldKey, int] = defaultdict(int)
    for ev in events:
        ename = ev.get("event_name", "").strip()
        for rf in ev.get("relevant_fields", []):
            fname = rf.get("field", "").strip()
            if not fname:
                continue
            key = make_field_key(
                ename,
                fname,
                rf.get("operator"),
                rf.get("value"),
                match_operator,
                match_value,
            )
            counts[key] += 1
    return dict(counts)


def compute_confusion(
    dataset: list[dict],
    match_operator: bool,
    match_value: bool,
) -> dict[str, dict[str, dict[str, int]]]:
    """
    Returns nested dict:
      { event_name: { field_name: { TP, FP, FN } } }
    """
    confusion: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})
    )

    for item in dataset:
        pred_ms = fields_to_multiset(item["predicted"], match_operator, match_value)
        gold_ms = fields_to_multiset(item["gold"], match_operator, match_value)

        all_keys = set(pred_ms) | set(gold_ms)

        for key in all_keys:
            # key[0] = event_name, key[1] = field_name
            ename, fname = key[0], key[1]
            pc = pred_ms.get(key, 0)
            gc = gold_ms.get(key, 0)

            tp = min(pc, gc)
            fp = max(0, pc - gc)
            fn = max(0, gc - pc)

            confusion[ename][fname]["TP"] += tp
            confusion[ename][fname]["FP"] += fp
            confusion[ename][fname]["FN"] += fn

    return {k: dict(v) for k, v in confusion.items()}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def precision(tp: int, fp: int) -> float:
    d = tp + fp
    return tp / d if d else 0.0


def recall(tp: int, fn: int) -> float:
    d = tp + fn
    return tp / d if d else 0.0


def f1(p: float, r: float) -> float:
    d = p + r
    return 2 * p * r / d if d else 0.0


def accuracy(tp: int, fp: int, fn: int) -> float:
    """Jaccard / IoU: TP / (TP + FP + FN)"""
    d = tp + fp + fn
    return tp / d if d else 1.0


def compute_metrics(
    confusion: dict[str, dict[str, dict[str, int]]]
) -> dict[str, dict[str, dict]]:
    """
    Returns:
      { event_name: { field_name: {TP,FP,FN,precision,recall,f1,accuracy}, "_TOTAL_": {...} } }
    """
    result: dict[str, dict[str, dict]] = {}

    for ename, fields in sorted(confusion.items()):
        result[ename] = {}
        tot_tp = tot_fp = tot_fn = 0

        for fname, counts in sorted(fields.items()):
            tp, fp, fn = counts["TP"], counts["FP"], counts["FN"]
            p = precision(tp, fp)
            r = recall(tp, fn)
            result[ename][fname] = {
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "precision": round(p * 100, 1),
                "recall": round(r * 100, 1),
                "f1": round(f1(p, r) * 100, 1),
                "accuracy": round(accuracy(tp, fp, fn) * 100, 1),
            }
            tot_tp += tp
            tot_fp += fp
            tot_fn += fn

        tp, fp, fn = tot_tp, tot_fp, tot_fn
        p = precision(tp, fp)
        r = recall(tp, fn)
        result[ename]["_TOTAL_"] = {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "precision": round(p * 100, 1),
            "recall": round(r * 100, 1),
            "f1": round(f1(p, r) * 100, 1),
            "accuracy": round(accuracy(tp, fp, fn) * 100, 1),
        }

    return result


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------

_C = {
    "field": 30,
    "tp": 6,
    "fp": 6,
    "fn": 6,
    "prec": 12,
    "rec": 10,
    "f1": 10,
    "acc": 12,
}
_ROW_W = sum(_C.values()) + len(_C) - 1
_SEP = "-" * _ROW_W
_HDR = (
    f"{'Field':<{_C['field']}}"
    f"{'TP':>{_C['tp']}}"
    f"{'FP':>{_C['fp']}}"
    f"{'FN':>{_C['fn']}}"
    f"{'Precision':>{_C['prec']}}"
    f"{'Recall':>{_C['rec']}}"
    f"{'F1':>{_C['f1']}}"
    f"{'Accuracy':>{_C['acc']}}"
)


def fmt_row(label: str, v: dict) -> str:
    return (
        f"{label:<{_C['field']}}"
        f"{v['TP']:>{_C['tp']}}"
        f"{v['FP']:>{_C['fp']}}"
        f"{v['FN']:>{_C['fn']}}"
        f"{v['precision']:>{_C['prec'] - 1}.1f}%"
        f"{v['recall']:>{_C['rec'] - 1}.1f}%"
        f"{v['f1']:>{_C['f1'] - 1}.1f}%"
        f"{v['accuracy']:>{_C['acc'] - 1}.1f}%"
    )


def print_metrics(metrics: dict[str, dict[str, dict]]) -> None:
    for ename, fields in metrics.items():
        print("\n" + "=" * _ROW_W)
        print(f"  {ename}")
        print("=" * _ROW_W)
        print(_HDR)
        print(_SEP)

        for fname, v in fields.items():
            if fname == "_TOTAL_":
                continue
            print(fmt_row(fname, v))

        print(_SEP)
        if "_TOTAL_" in fields:
            print(fmt_row("TOTAL", fields["_TOTAL_"]))
        print(_SEP)


def print_overall_summary(metrics: dict[str, dict[str, dict]]) -> None:
    """Macro summary across all event types."""
    all_totals = [v["_TOTAL_"] for v in metrics.values() if "_TOTAL_" in v]
    if not all_totals:
        return

    agg_tp = sum(t["TP"] for t in all_totals)
    agg_fp = sum(t["FP"] for t in all_totals)
    agg_fn = sum(t["FN"] for t in all_totals)
    p = precision(agg_tp, agg_fp)
    r = recall(agg_tp, agg_fn)

    print("\n" + "=" * 50)
    print("  Overall Summary (micro-averaged across all event types)")
    print("=" * 50)
    print(f"  {'Total TP':<28} {agg_tp}")
    print(f"  {'Total FP':<28} {agg_fp}")
    print(f"  {'Total FN':<28} {agg_fn}")
    print(f"  {'Micro Precision':<28} {p * 100:.1f}%")
    print(f"  {'Micro Recall':<28} {r * 100:.1f}%")
    print(f"  {'Micro F1':<28} {f1(p, r) * 100:.1f}%")
    print(f"  {'Micro Accuracy':<28} {accuracy(agg_tp, agg_fp, agg_fn) * 100:.1f}%")
    print("=" * 50)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def save_results(metrics: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)
    print(f"\n[INFO] Results saved → {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate field-level predictions against human-annotated ground truth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--predictions",
        default=os.path.join("evaluate", "data", "fields", "response.jsonl"),
        help="Path to LLM response.jsonl",
    )
    parser.add_argument(
        "--ground_truth",
        default=os.path.join("evaluate", "data", "fields", "annotated.jsonl"),
        help="Path to annotated.jsonl",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save JSON results",
    )
    parser.add_argument(
        "--reviewed_only",
        action="store_true",
        default=False,
        help="Only evaluate queries marked 'reviewed' in annotated.jsonl",
    )
    parser.add_argument(
        "--match_operator",
        action="store_true",
        default=False,
        help="Require operator to match (not just field name) for a TP",
    )
    parser.add_argument(
        "--match_value",
        action="store_true",
        default=False,
        help="Require value to match (not just field name) for a TP",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 1. Load & merge
    dataset = build_dataset(args.predictions, args.ground_truth)

    if args.reviewed_only:
        before = len(dataset)
        dataset = [d for d in dataset if d["reviewed"]]
        print(f"[INFO] Filtered to reviewed-only: {len(dataset)} / {before} pairs.")

    if not dataset:
        sys.exit("[ERROR] No usable pairs found. Check file paths and content.")

    # 2. Confusion counts
    confusion = compute_confusion(dataset, args.match_operator, args.match_value)

    # 3. Metrics
    metrics = compute_metrics(confusion)

    # 4. Print
    print_metrics(metrics)
    print_overall_summary(metrics)

    # 5. Optional JSON export
    if args.output:
        save_results(metrics, args.output)


if __name__ == "__main__":
    main()
