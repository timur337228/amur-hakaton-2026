from __future__ import annotations

from pathlib import Path

from datasets import Features, Sequence, Value, load_dataset


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = REPO_ROOT / "training" / "llm_sft" / "budget_query_sft_train.jsonl"
VAL_PATH = REPO_ROOT / "training" / "llm_sft" / "budget_query_sft_val.jsonl"


BUDGET_QUERY_FEATURES = Features(
    {
        "task": Value("string"),
        "text_query": Value("string"),
        "prompt": Value("string"),
        "completion": Value("string"),
        "target": {
            "date_from": Value("string"),
            "date_to": Value("string"),
            "metrics": Sequence(Value("string")),
            "filters": {
                "source_groups": Sequence(Value("string")),
                "object_query": Value("string"),
                "budget_query": Value("string"),
                "organization_query": Value("string"),
                "document_id": Value("string"),
                "document_number": Value("string"),
                "kfsr_code": Value("string"),
                "kcsr_code": Value("string"),
                "kvr_code": Value("string"),
                "kvsr_code": Value("string"),
                "kesr_code": Value("string"),
                "kosgu_code": Value("string"),
                "purpose_code": Value("string"),
                "funding_source": Value("string"),
            },
            "group_by": Sequence(Value("string")),
        },
    }
)


def load_budget_query_sft_dataset(*, cache_dir: str | Path | None = None):
    return load_dataset(
        "json",
        data_files={
            "train": str(TRAIN_PATH),
            "validation": str(VAL_PATH),
        },
        features=BUDGET_QUERY_FEATURES,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
    )
