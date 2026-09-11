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
    """Load a .jsonl file; returns a list of dicts."""
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


def normalize_response(response) -> dict:
    """Mirror the normalize_response() used in the Streamlit app."""
    if not isinstance(response, dict):
        response = {"status": "success", "matched_events": []}
    response.setdefault("status", "success")
    response.setdefault("matched_events", [])
    if not isinstance(response["matched_events"], list):
        response["matched_events"] = []
    return response


def extract_event_names(response: dict) -> list[str]:
    """Return a list of event_name strings from a (normalized) response dict."""
    return [
        e.get("event_name", "").strip()
        for e in response.get("matched_events", [])
        if e.get("event_name", "").strip()
    ]


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def build_dataset(
    predictions_path: str,
    ground_truth_path: str,
) -> list[dict]:
    """
    Merge predictions and ground-truth by query string.

    Returns a list of dicts:
      {
        "query":       str,
        "predicted":   list[str],   # event names from LLM response
        "gold":        list[str],   # event names from annotated (corrected) response
        "reviewed":    bool,
      }
    """
    raw_preds = load_jsonl(predictions_path)
    raw_gold = load_jsonl(ground_truth_path)

    # Build gold lookup keyed by query
    gold_map: dict[str, dict] = {}
    for item in raw_gold:
        query = item.get("query", "").strip()
        if query:
            gold_map[query] = item

    dataset = []
    skipped = 0

    for item in raw_preds:
        query = item.get("query", "").strip()
        if not query:
            skipped += 1
            continue

        gold_item = gold_map.get(query)
        if gold_item is None:
            # No annotation exists for this query – skip silently
            skipped += 1
            continue

        reviewed = gold_item.get("reviewed", False)

        # Prediction: field is "response" in response.jsonl
        pred_response = normalize_response(deepcopy(item.get("response", {})))

        gold_response = normalize_response(
            deepcopy(gold_item.get("corrected_response") or {})
        )

        dataset.append(
            {
                "query": query,
                "predicted": extract_event_names(pred_response),
                "gold": extract_event_names(gold_response),
                "reviewed": reviewed,
            }
        )

    print(
        f"[INFO] Loaded {len(dataset)} matched pairs  ({skipped} skipped / unmatched)."
    )
    return dataset


# ---------------------------------------------------------------------------
# Per-query confusion counts  (multiset / bag semantics)
# ---------------------------------------------------------------------------


def compute_confusion(dataset: list[dict]) -> dict[str, dict[str, int]]:
    """
    For each event type compute aggregate TP, FP, FN across all queries.

    Multiset semantics:
      - Both predicted and gold are treated as multisets.
      - TP = min(count_pred, count_gold) for each event type per query.
      - FP = max(0, count_pred - count_gold)
      - FN = max(0, count_gold - count_pred)

    Returns:
      { event_type: {"TP": int, "FP": int, "FN": int, "total_gold": int} }
    """
    confusion: dict[str, dict[str, int]] = defaultdict(
        lambda: {"TP": 0, "FP": 0, "FN": 0, "total_gold": 0}
    )

    for item in dataset:
        pred_counts: dict[str, int] = defaultdict(int)
        gold_counts: dict[str, int] = defaultdict(int)

        for e in item["predicted"]:
            pred_counts[e] += 1
        for e in item["gold"]:
            gold_counts[e] += 1

        all_types = set(pred_counts) | set(gold_counts)

        for et in all_types:
            pc = pred_counts.get(et, 0)
            gc = gold_counts.get(et, 0)
            tp = min(pc, gc)
            fp = max(0, pc - gc)
            fn = max(0, gc - pc)
            confusion[et]["TP"] += tp
            confusion[et]["FP"] += fp
            confusion[et]["FN"] += fn
            confusion[et]["total_gold"] += gc

    return dict(confusion)


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def precision(tp: int, fp: int) -> float:
    denom = tp + fp
    return tp / denom if denom else 0.0


def recall(tp: int, fn: int) -> float:
    denom = tp + fn
    return tp / denom if denom else 0.0


def f1(prec: float, rec: float) -> float:
    denom = prec + rec
    return 2 * prec * rec / denom if denom else 0.0


def accuracy_per_event(tp: int, fp: int, fn: int, total_queries: int) -> float:
    """
    Accuracy = (queries where event was handled correctly) / total_queries.

    "Correctly handled" means neither a spurious prediction (FP) nor a missed
    gold label (FN) for that event type in that query.

    We approximate this at the aggregate level as:
        accuracy = 1 - (FP + FN) / (2 * total_gold + FP)
    which equals the micro-averaged Jaccard / set-accuracy.

    A simpler and more interpretable formula used in many NLP annotation papers:
        accuracy = TP / (TP + FP + FN)   [Jaccard / IoU at set level]
    """
    denom = tp + fp + fn
    return tp / denom if denom else 1.0  # if nothing predicted & nothing gold → perfect


def compute_metrics(confusion: dict[str, dict[str, int]]) -> dict[str, dict]:
    metrics = {}
    for et, counts in sorted(confusion.items()):
        tp = counts["TP"]
        fp = counts["FP"]
        fn = counts["FN"]

        prec = precision(tp, fp)
        rec = recall(tp, fn)
        f1_ = f1(prec, rec)
        acc = accuracy_per_event(tp, fp, fn, counts["total_gold"])

        metrics[et] = {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "accuracy": round(acc * 100, 1),
            "precision": round(prec * 100, 1),
            "recall": round(rec * 100, 1),
            "f1": round(f1_ * 100, 1),
        }
    return metrics


# ---------------------------------------------------------------------------
# Macro / micro aggregates
# ---------------------------------------------------------------------------


def aggregate_metrics(metrics: dict[str, dict]) -> dict:
    n = len(metrics)
    if n == 0:
        return {}

    macro_acc = sum(v["accuracy"] for v in metrics.values()) / n
    macro_prec = sum(v["precision"] for v in metrics.values()) / n
    macro_rec = sum(v["recall"] for v in metrics.values()) / n
    macro_f1 = sum(v["f1"] for v in metrics.values()) / n

    total_tp = sum(v["TP"] for v in metrics.values())
    total_fp = sum(v["FP"] for v in metrics.values())
    total_fn = sum(v["FN"] for v in metrics.values())

    micro_prec = precision(total_tp, total_fp) * 100
    micro_rec = recall(total_tp, total_fn) * 100
    micro_f1 = f1(micro_prec / 100, micro_rec / 100) * 100

    return {
        "macro": {
            "accuracy": round(macro_acc, 1),
            "precision": round(macro_prec, 1),
            "recall": round(macro_rec, 1),
            "f1": round(macro_f1, 1),
        },
        "micro": {
            "precision": round(micro_prec, 1),
            "recall": round(micro_rec, 1),
            "f1": round(micro_f1, 1),
            "TP": total_tp,
            "FP": total_fp,
            "FN": total_fn,
        },
    }


# ---------------------------------------------------------------------------
# Pretty-print tables
# ---------------------------------------------------------------------------

COL_W = {
    "event": 45,
    "acc": 10,
    "prec": 12,
    "rec": 10,
    "f1": 10,
    "fp": 22,
    "fn": 22,
}

SEP_MAIN = "-" * (
    COL_W["event"] + COL_W["acc"] + COL_W["prec"] + COL_W["rec"] + COL_W["f1"] + 5
)
SEP_ERROR = "-" * (COL_W["event"] + COL_W["fp"] + COL_W["fn"] + 4)


def print_metrics_table(metrics: dict[str, dict]) -> None:
    print("\n" + "=" * len(SEP_MAIN))
    print("  Per Event Type Metrics")
    print("=" * len(SEP_MAIN))
    print(
        f"{'Event Type':<{COL_W['event']}}"
        f"{'Accuracy':>{COL_W['acc']}}"
        f"{'Precision':>{COL_W['prec']}}"
        f"{'Recall':>{COL_W['rec']}}"
        f"{'F1 Score':>{COL_W['f1']}}"
    )
    print(SEP_MAIN)
    for et, v in sorted(metrics.items()):
        print(
            f"{et:<{COL_W['event']}}"
            f"{v['accuracy']:>{COL_W['acc'] - 1}.1f}%"
            f"{v['precision']:>{COL_W['prec'] - 1}.1f}%"
            f"{v['recall']:>{COL_W['rec'] - 1}.1f}%"
            f"{v['f1']:>{COL_W['f1'] - 1}.1f}%"
        )
    print(SEP_MAIN)


def print_error_table(metrics: dict[str, dict]) -> None:
    # Only show event types that have at least one FP or FN
    error_types = {et: v for et, v in metrics.items() if v["FP"] > 0 or v["FN"] > 0}

    print("\n" + "=" * len(SEP_ERROR))
    print("  Error Analysis (False Positives & False Negatives)")
    print("=" * len(SEP_ERROR))
    print(
        f"{'Event Type':<{COL_W['event']}}"
        f"{'False Positives (FP)':>{COL_W['fp']}}"
        f"{'False Negatives (FN)':>{COL_W['fn']}}"
    )
    print(SEP_ERROR)
    if error_types:
        for et, v in sorted(error_types.items()):
            print(
                f"{et:<{COL_W['event']}}"
                f"{v['FP']:>{COL_W['fp']}}"
                f"{v['FN']:>{COL_W['fn']}}"
            )
    else:
        print("  (No errors found – perfect predictions!)")
    print(SEP_ERROR)


def print_aggregate(agg: dict) -> None:
    print("\n" + "=" * 50)
    print("  Aggregate Metrics")
    print("=" * 50)
    macro = agg.get("macro", {})
    micro = agg.get("micro", {})
    print(f"  {'Macro Accuracy':<30} {macro.get('accuracy', 0.0):.1f}%")
    print(f"  {'Macro Precision':<30} {macro.get('precision', 0.0):.1f}%")
    print(f"  {'Macro Recall':<30} {macro.get('recall', 0.0):.1f}%")
    print(f"  {'Macro F1':<30} {macro.get('f1', 0.0):.1f}%")
    print()
    print(f"  {'Micro Precision':<30} {micro.get('precision', 0.0):.1f}%")
    print(f"  {'Micro Recall':<30} {micro.get('recall', 0.0):.1f}%")
    print(f"  {'Micro F1':<30} {micro.get('f1', 0.0):.1f}%")
    print(f"  {'Total TP':<30} {micro.get('TP', 0)}")
    print(f"  {'Total FP':<30} {micro.get('FP', 0)}")
    print(f"  {'Total FN':<30} {micro.get('FN', 0)}")
    print("=" * 50)


# ---------------------------------------------------------------------------
# Optional JSON export
# ---------------------------------------------------------------------------


def save_results(
    metrics: dict,
    agg: dict,
    path: str,
) -> None:
    payload = {
        "per_event_metrics": metrics,
        "aggregate": agg,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"\n[INFO] Results saved → {path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate LLM event-matching predictions against human annotations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--predictions",
        default=os.path.join("evaluate", "data", "events", "response.jsonl"),
        help="Path to LLM response.jsonl  (default: evaluate/data/events/response.jsonl)",
    )
    parser.add_argument(
        "--ground_truth",
        default=os.path.join("evaluate", "data", "events", "annotated.jsonl"),
        help="Path to annotated.jsonl  (default: evaluate/data/events/annotated.jsonl)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save JSON results (e.g. evaluate/data/events/eval_results.json)",
    )
    parser.add_argument(
        "--reviewed_only",
        action="store_true",
        default=False,
        help="Only evaluate queries that have been marked 'reviewed' in annotated.jsonl",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── 1. Load & merge ────────────────────────────────────────────────────
    dataset = build_dataset(args.predictions, args.ground_truth)

    if args.reviewed_only:
        before = len(dataset)
        dataset = [d for d in dataset if d["reviewed"]]
        print(f"[INFO] Filtered to reviewed-only: {len(dataset)} / {before} pairs.")

    if not dataset:
        sys.exit("[ERROR] No usable pairs found. Check file paths and content.")

    # ── 2. Compute confusion counts ────────────────────────────────────────
    confusion = compute_confusion(dataset)

    # ── 3. Derive metrics ──────────────────────────────────────────────────
    metrics = compute_metrics(confusion)
    agg = aggregate_metrics(metrics)

    # ── 4. Print tables ────────────────────────────────────────────────────
    print_metrics_table(metrics)
    print_error_table(metrics)
    print_aggregate(agg)

    # ── 5. Optional JSON export ────────────────────────────────────────────
    if args.output:
        save_results(metrics, agg, args.output)


if __name__ == "__main__":
    main()
