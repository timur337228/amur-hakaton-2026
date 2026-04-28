from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from datasets import Dataset, DatasetDict
from huggingface_hub import login, snapshot_download
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

if "__file__" in globals():
    REPO_ROOT = Path(__file__).resolve().parents[1]
else:
    REPO_ROOT = Path.cwd()
MODEL_NAME = "yandex/YandexGPT-5-Lite-8B-pretrain"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setup_colab_environment() -> tuple[bool, Path]:
    try:
        from google.colab import drive  # type: ignore

        drive.mount("/content/drive")
        drive_root = Path("/content/drive/MyDrive")
        print("Google Drive mounted:", drive_root)
        return True, drive_root
    except Exception:
        return False, Path.cwd()


def resolve_project_dir(drive_root: Path) -> Path:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        drive_root / "amur-hakaton-2026",
        drive_root / "budget-analytics",
        drive_root,
    ]
    for candidate in candidates:
        if (candidate / "training" / "llm_sft").exists():
            return candidate
    return drive_root if drive_root.exists() else Path.cwd()


def resolve_hf_token(project_dir: Path) -> str:
    try:
        from google.colab import userdata  # type: ignore

        secret_token = userdata.get("HF_TOKEN")
        if secret_token:
            os.environ.setdefault("HF_TOKEN", secret_token)
    except Exception:
        pass

    load_env_file(project_dir / ".env")
    load_env_file(Path("/content/.env"))

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError(
            "HF_TOKEN не найден. Добавь его в Colab Secrets как HF_TOKEN "
            "или загрузи .env с HF_TOKEN=..."
        )
    return hf_token


def build_dataset_from_jsonl(train_path: Path, val_path: Path) -> DatasetDict:
    def read_jsonl(path: Path) -> list[dict]:
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                rows.append(
                    {
                        "text": (item.get("prompt") or "") + (item.get("completion") or ""),
                    }
                )
        return rows

    return DatasetDict(
        {
            "train": Dataset.from_list(read_jsonl(train_path)),
            "validation": Dataset.from_list(read_jsonl(val_path)),
        }
    )


def resolve_dataset(project_dir: Path, cache_dir: Path, in_colab: bool) -> DatasetDict:
    train_path = project_dir / "training" / "llm_sft" / "budget_query_sft_train.jsonl"
    val_path = project_dir / "training" / "llm_sft" / "budget_query_sft_val.jsonl"

    if in_colab and (not train_path.exists() or not val_path.exists()):
        try:
            from google.colab import files  # type: ignore

            print("Файлы датасета не найдены. Загрузите budget_query_sft_train.jsonl и budget_query_sft_val.jsonl.")
            uploaded = files.upload()
            upload_dir = Path("/content/training/llm_sft")
            upload_dir.mkdir(parents=True, exist_ok=True)
            for name, content in uploaded.items():
                (upload_dir / name).write_bytes(content)
            train_path = upload_dir / "budget_query_sft_train.jsonl"
            val_path = upload_dir / "budget_query_sft_val.jsonl"
        except Exception as exc:
            raise FileNotFoundError("Не удалось получить train/val jsonl для обучения.") from exc

    if not train_path.exists() or not val_path.exists():
        raise FileNotFoundError(
            f"Не найдены train/val jsonl-файлы: {train_path} / {val_path}"
        )

    dataset_loader_module = project_dir / "training" / "llm_sft" / "dataset_loader.py"
    if dataset_loader_module.exists():
        if str(project_dir) not in sys.path:
            sys.path.insert(0, str(project_dir))
        from training.llm_sft.dataset_loader import load_budget_query_sft_dataset

        dataset = load_budget_query_sft_dataset(cache_dir=str(cache_dir))
        return dataset.map(
            lambda row: {"text": (row.get("prompt") or "") + (row.get("completion") or "")},
            remove_columns=dataset["train"].column_names,
            desc="Build SFT text column",
        )

    return build_dataset_from_jsonl(train_path, val_path)


def main() -> None:
    in_colab, drive_root = setup_colab_environment()
    project_dir = resolve_project_dir(drive_root)
    output_dir = project_dir / "artifacts" / "yandexgpt5-lite-budget-query-lora-t4"
    model_cache_dir = project_dir / ".cache" / "hf_models"
    dataset_cache_dir = project_dir / ".cache" / "hf_datasets"

    print("IN_COLAB:", in_colab)
    print("PROJECT_DIR:", project_dir)

    hf_token = resolve_hf_token(project_dir)

    if not torch.cuda.is_available():
        raise RuntimeError("Нужен GPU с CUDA. Для T4 это обязательно.")

    major, minor = torch.cuda.get_device_capability(0)
    gpu_name = torch.cuda.get_device_name(0)
    supports_bf16 = major >= 8
    compute_dtype = torch.bfloat16 if supports_bf16 else torch.float16
    max_seq_length = 1536 if supports_bf16 else 1024
    gradient_accumulation_steps = 16 if supports_bf16 else 32

    print("GPU:", gpu_name)
    print("CUDA capability:", f"{major}.{minor}")
    print("bf16 supported:", supports_bf16)
    print("max_seq_length:", max_seq_length)

    output_dir.mkdir(parents=True, exist_ok=True)
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    dataset_cache_dir.mkdir(parents=True, exist_ok=True)

    login(token=hf_token, add_to_git_credential=False)

    local_model_dir = snapshot_download(
        repo_id=MODEL_NAME,
        token=hf_token,
        cache_dir=str(model_cache_dir),
        resume_download=True,
    )
    print("Local model dir:", local_model_dir)

    dataset = resolve_dataset(project_dir, dataset_cache_dir, in_colab)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        local_model_dir,
        token=hf_token,
        legacy=False,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        local_model_dir,
        token=hf_token,
        trust_remote_code=True,
        torch_dtype=compute_dtype,
        quantization_config=bnb_config,
        device_map="auto",
        low_cpu_mem_usage=True,
        attn_implementation="eager",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    def tokenize_batch(batch: dict) -> dict:
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_length,
        )

    tokenized_dataset = dataset.map(
        tokenize_batch,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenize dataset",
    )

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    model = get_peft_model(model, lora_config)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=gradient_accumulation_steps,
        num_train_epochs=3,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        evaluation_strategy="steps",
        eval_steps=100,
        save_steps=100,
        save_total_limit=2,
        bf16=supports_bf16,
        fp16=not supports_bf16,
        gradient_checkpointing=True,
        report_to="none",
        optim="paged_adamw_8bit",
        remove_unused_columns=False,
        label_names=["labels"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        tokenizer=tokenizer,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    trainer.model.print_trainable_parameters()
    trainer.train()

    adapter_dir = output_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print("Saved adapter to:", adapter_dir)


if __name__ == "__main__":
    main()
