from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from copy import deepcopy

# ---------------------------------------------------------------------------
# I/O
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


def extract_llm_response(item: dict) -> dict:
    """Pull the llm_response from a raw prediction record."""
    response = item.get("response") or {}
    if isinstance(response, list):
        return {}
    return deepcopy(response.get("llm_response") or {})


def extract_corrected(item: dict) -> dict:
    """Pull the corrected response from an annotation record."""
    return deepcopy(
        item.get("corrected_llm_response") or item.get("corrected_response") or {}
    )


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def build_dataset(predictions_path: str, ground_truth_path: str) -> list[dict]:
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

        pred = extract_llm_response(item)
        gold = extract_corrected(gold_item)

        dataset.append(
            {
                "query": query,
                "pred": pred if isinstance(pred, dict) else {},
                "gold": gold if isinstance(gold, dict) else {},
                "reviewed": gold_item.get("reviewed", False),
            }
        )

    skipped_pred = sum(1 for d in dataset if not d["pred"])
    print(
        f"[INFO] Loaded {len(dataset)} matched pairs  ({skipped} skipped / unmatched)."
    )
    if skipped_pred:
        print(
            f"[WARN] {skipped_pred} records have empty/missing llm_response and will be counted as no-prediction."
        )
    return dataset


# ---------------------------------------------------------------------------
# Metric helpers
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


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


# ---------------------------------------------------------------------------
# 1. Intent-level metrics  (classification confusion matrix)
# ---------------------------------------------------------------------------


def compute_intent_confusion(dataset: list[dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})

    for item in dataset:
        if not isinstance(item["pred"], dict) or not isinstance(item["gold"], dict):
            continue

        p_intent = (item["pred"].get("timeIntent") or "").strip()
        g_intent = (item["gold"].get("timeIntent") or "").strip()

        all_intents = {p_intent, g_intent} - {""}
        for intent in all_intents:
            p_has = p_intent == intent
            g_has = g_intent == intent

            if p_has and g_has:
                counts[intent]["TP"] += 1
            elif p_has and not g_has:
                counts[intent]["FP"] += 1
            elif not p_has and g_has:
                counts[intent]["FN"] += 1

    return dict(counts)


def intent_metrics(confusion: dict[str, dict[str, int]]) -> dict[str, dict]:
    result = {}
    for intent, c in sorted(confusion.items()):
        p = precision(c["TP"], c["FP"])
        r = recall(c["TP"], c["FN"])
        result[intent] = {
            "TP": c["TP"],
            "FP": c["FP"],
            "FN": c["FN"],
            "precision": p,
            "recall": r,
            "f1": f1(p, r),
        }
    return result


# ---------------------------------------------------------------------------
# 2. SubClass-level metrics  (grouped by intent)
# ---------------------------------------------------------------------------


def compute_subclass_confusion(
    dataset: list[dict],
) -> dict[str, dict[str, dict[str, int]]]:
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})
    )

    for item in dataset:
        if not isinstance(item["pred"], dict) or not isinstance(item["gold"], dict):
            continue

        p_intent = (item["pred"].get("timeIntent") or "").strip()
        g_intent = (item["gold"].get("timeIntent") or "").strip()

        p_sub = (item["pred"].get("timeIntentSubClass") or "").strip()
        g_sub = (item["gold"].get("timeIntentSubClass") or "").strip()

        group = g_intent or p_intent
        if not group:
            continue

        all_subs = {p_sub, g_sub} - {""}
        for sub in all_subs:
            p_has = p_sub == sub
            g_has = g_sub == sub

            if p_has and g_has:
                counts[group][sub]["TP"] += 1
            elif p_has and not g_has:
                counts[group][sub]["FP"] += 1
            elif not p_has and g_has:
                counts[group][sub]["FN"] += 1

    return {k: dict(v) for k, v in counts.items()}


def subclass_metrics(
    confusion: dict[str, dict[str, dict[str, int]]]
) -> dict[str, dict[str, dict]]:
    result = {}
    for intent, subs in sorted(confusion.items()):
        result[intent] = {}
        for sub, c in sorted(subs.items()):
            p = precision(c["TP"], c["FP"])
            r = recall(c["TP"], c["FN"])
            result[intent][sub] = {
                "TP": c["TP"],
                "FP": c["FP"],
                "FN": c["FN"],
                "precision": p,
                "recall": r,
                "f1": f1(p, r),
            }
    return result


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

_IW = 30
_MW = 12
_SEP_INTENT = "-" * (_IW + _MW * 3 + 3)
_SEP_ERROR = "-" * (_IW + _MW * 2 + 2)


def _hdr_intent() -> str:
    return (
        f"{'Time Intent':<{_IW}}"
        f"{'Precision':>{_MW}}"
        f"{'Recall':>{_MW}}"
        f"{'F1 Score':>{_MW}}"
    )


def _row_intent(label: str, v: dict) -> str:
    return (
        f"{label:<{_IW}}"
        f"{pct(v['precision']):>{_MW}}"
        f"{pct(v['recall']):>{_MW}}"
        f"{pct(v['f1']):>{_MW}}"
    )


def _hdr_error() -> str:
    return (
        f"{'Time Intent':<{_IW}}"
        f"{'False Positives (FP)':>{_MW + 8}}"
        f"{'False Negatives (FN)':>{_MW + 8}}"
    )


def _row_error(label: str, v: dict) -> str:
    return f"{label:<{_IW}}" f"{v['FP']:>{_MW + 8}}" f"{v['FN']:>{_MW + 8}}"


def print_intent_metrics(metrics: dict[str, dict]) -> None:
    print("\n" + "=" * len(_SEP_INTENT))
    print("  Time Intent Metrics")
    print("=" * len(_SEP_INTENT))
    print(_hdr_intent())
    print(_SEP_INTENT)
    for intent, v in metrics.items():
        print(_row_intent(intent, v))
    print(_SEP_INTENT)


def print_intent_errors(metrics: dict[str, dict]) -> None:
    print("\n" + "=" * len(_SEP_ERROR))
    print("  Time Intent Errors (FP & FN)")
    print("=" * len(_SEP_ERROR))
    print(_hdr_error())
    print(_SEP_ERROR)
    for intent, v in metrics.items():
        print(_row_error(intent, v))
    print(_SEP_ERROR)


def print_subclass_metrics(metrics: dict[str, dict[str, dict]]) -> None:
    print("\n" + "=" * len(_SEP_INTENT))
    print("  Time Intent SubClass Metrics (Grouped)")
    print("=" * len(_SEP_INTENT))

    for n, (intent, subs) in enumerate(metrics.items(), 1):
        print(f"\n{n}. {intent}")
        print(
            f"  {'SubClass':<{_IW - 2}}{'Precision':>{_MW}}{'Recall':>{_MW}}{'F1 Score':>{_MW}}"
        )
        print("  " + "-" * (_IW - 2 + _MW * 3 + 2))
        for sub, v in subs.items():
            print(
                f"  {sub:<{_IW - 2}}"
                f"{pct(v['precision']):>{_MW}}"
                f"{pct(v['recall']):>{_MW}}"
                f"{pct(v['f1']):>{_MW}}"
            )


def print_overall(i_metrics: dict[str, dict]) -> None:
    n = len(i_metrics)
    if n == 0:
        return
    macro_p = sum(v["precision"] for v in i_metrics.values()) / n
    macro_r = sum(v["recall"] for v in i_metrics.values()) / n
    macro_f = sum(v["f1"] for v in i_metrics.values()) / n

    tot_tp = sum(v["TP"] for v in i_metrics.values())
    tot_fp = sum(v["FP"] for v in i_metrics.values())
    tot_fn = sum(v["FN"] for v in i_metrics.values())
    mp = precision(tot_tp, tot_fp)
    mr = recall(tot_tp, tot_fn)

    print("\n" + "=" * 50)
    print("  Overall Summary")
    print("=" * 50)
    print(f"  {'Macro Precision':<28} {pct(macro_p)}")
    print(f"  {'Macro Recall':<28} {pct(macro_r)}")
    print(f"  {'Macro F1':<28} {pct(macro_f)}")
    print(f"  {'Micro Precision':<28} {pct(mp)}")
    print(f"  {'Micro Recall':<28} {pct(mr)}")
    print(f"  {'Micro F1':<28} {pct(f1(mp, mr))}")
    print(f"  {'Total TP':<28} {tot_tp}")
    print(f"  {'Total FP':<28} {tot_fp}")
    print(f"  {'Total FN':<28} {tot_fn}")
    print("=" * 50)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def save_results(payload: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"\n[INFO] Results saved → {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate time-intent predictions against human annotations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--predictions",
        default=os.path.join("evaluate", "data", "time", "response.jsonl"),
        help="Path to LLM response.jsonl",
    )
    parser.add_argument(
        "--ground_truth",
        default=os.path.join("evaluate", "data", "time", "annotated.jsonl"),
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
        help="Only evaluate queries marked 'reviewed'",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 1. Load
    dataset = build_dataset(args.predictions, args.ground_truth)

    if args.reviewed_only:
        before = len(dataset)
        dataset = [d for d in dataset if d["reviewed"]]
        print(f"[INFO] Filtered to reviewed-only: {len(dataset)} / {before} pairs.")

    if not dataset:
        sys.exit("[ERROR] No usable pairs found. Check file paths and content.")

    # 2. Intent metrics
    i_confusion = compute_intent_confusion(dataset)
    i_metrics = intent_metrics(i_confusion)

    # 3. SubClass metrics
    s_confusion = compute_subclass_confusion(dataset)
    s_metrics = subclass_metrics(s_confusion)

    # 4. Print
    print_intent_metrics(i_metrics)
    print_intent_errors(i_metrics)
    print_subclass_metrics(s_metrics)
    print_overall(i_metrics)

    # 5. Optional JSON export
    if args.output:
        payload: dict = {
            "intent_metrics": {
                k: {
                    **v,
                    "precision": pct(v["precision"]),
                    "recall": pct(v["recall"]),
                    "f1": pct(v["f1"]),
                }
                for k, v in i_metrics.items()
            },
            "subclass_metrics": {
                intent: {
                    sub: {
                        **sv,
                        "precision": pct(sv["precision"]),
                        "recall": pct(sv["recall"]),
                        "f1": pct(sv["f1"]),
                    }
                    for sub, sv in subs.items()
                }
                for intent, subs in s_metrics.items()
            },
        }
        save_results(payload, args.output)


if __name__ == "__main__":
    main()
