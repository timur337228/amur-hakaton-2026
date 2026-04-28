from __future__ import annotations

import json
import unittest
from pathlib import Path

from training.llm_sft.dataset_loader import BUDGET_QUERY_FEATURES, load_budget_query_sft_dataset


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_FILE = REPO_ROOT / "training" / "llm_sft" / "budget_query_sft_train.jsonl"
VAL_FILE = REPO_ROOT / "training" / "llm_sft" / "budget_query_sft_val.jsonl"
MANIFEST_FILE = REPO_ROOT / "training" / "llm_sft" / "dataset_manifest.json"
NOTEBOOK_FILE = REPO_ROOT / "notebooks" / "yandexgpt5_lite_budget_query_sft.ipynb"
CACHE_DIR = Path("/tmp/amur-hf-datasets-cache")

EXPECTED_ROOT_KEYS = {"date_from", "date_to", "metrics", "filters", "group_by"}
EXPECTED_FILTER_KEYS = {
    "source_groups",
    "object_query",
    "budget_query",
    "organization_query",
    "document_id",
    "document_number",
    "kfsr_code",
    "kcsr_code",
    "kvr_code",
    "kvsr_code",
    "kesr_code",
    "kosgu_code",
    "purpose_code",
    "funding_source",
}


class SFTAssetsTests(unittest.TestCase):
    def test_generated_dataset_files_exist_and_have_rows(self) -> None:
        self.assertTrue(TRAIN_FILE.exists())
        self.assertTrue(VAL_FILE.exists())

        train_rows = self._read_jsonl(TRAIN_FILE)
        val_rows = self._read_jsonl(VAL_FILE)

        self.assertGreaterEqual(len(train_rows), 100)
        self.assertGreaterEqual(len(val_rows), 20)

    def test_dataset_record_schema_is_consistent(self) -> None:
        rows = self._read_jsonl(TRAIN_FILE)[:10] + self._read_jsonl(VAL_FILE)[:10]
        for row in rows:
            with self.subTest(text_query=row["text_query"]):
                self.assertEqual(row["task"], "budget_query_to_json")
                self.assertIn(row["text_query"], row["prompt"])
                self.assertIsInstance(row["completion"], str)
                self.assertEqual(set(row["target"].keys()), EXPECTED_ROOT_KEYS)
                self.assertEqual(set(row["target"]["filters"].keys()), EXPECTED_FILTER_KEYS)

    def test_manifest_matches_generated_files(self) -> None:
        self.assertTrue(MANIFEST_FILE.exists())
        payload = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["task"], "budget_query_to_json")
        self.assertEqual(payload["base_model"], "yandex/YandexGPT-5-Lite-8B-pretrain")
        self.assertEqual(set(payload["schema"]["root_keys"]), EXPECTED_ROOT_KEYS)
        self.assertEqual(set(payload["schema"]["filter_keys"]), EXPECTED_FILTER_KEYS)

    def test_notebook_exists_and_mentions_hf_token_and_model(self) -> None:
        self.assertTrue(NOTEBOOK_FILE.exists())
        notebook = json.loads(NOTEBOOK_FILE.read_text(encoding="utf-8"))
        all_source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        self.assertIn("HF_TOKEN", all_source)
        self.assertIn("yandex/YandexGPT-5-Lite-8B-pretrain", all_source)
        self.assertIn("SFTTrainer", all_source)

    def test_dataset_loader_loads_both_splits_with_explicit_features(self) -> None:
        dataset = load_budget_query_sft_dataset(cache_dir=CACHE_DIR)
        self.assertEqual(dataset["train"].num_rows, 426)
        self.assertEqual(dataset["validation"].num_rows, 80)
        self.assertEqual(dataset["train"].features, BUDGET_QUERY_FEATURES)
        first_target = dataset["train"][0]["target"]
        self.assertIn("filters", first_target)
        self.assertEqual(set(first_target["filters"].keys()), EXPECTED_FILTER_KEYS)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        rows = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows


if __name__ == "__main__":
    unittest.main()
