from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = REPO_ROOT / "training" / "llm_sft"
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"
TRAIN_FILE = TRAINING_DIR / "budget_query_sft_train.jsonl"
VAL_FILE = TRAINING_DIR / "budget_query_sft_val.jsonl"
README_FILE = TRAINING_DIR / "README.md"
MANIFEST_FILE = TRAINING_DIR / "dataset_manifest.json"
NOTEBOOK_FILE = NOTEBOOKS_DIR / "yandexgpt5_lite_budget_query_sft.ipynb"

RANDOM_SEED = 42
VAL_RATIO = 0.16

SYSTEM_TASK_PROMPT = """Ты преобразуешь русский запрос к системе бюджетной аналитики в JSON для API.
Верни только JSON без пояснений.

Требуемая схема:
- date_from: строка в формате YYYY-MM-DD или null
- date_to: строка в формате YYYY-MM-DD или null
- metrics: массив строк или null
- filters: объект со следующими ключами:
  source_groups, object_query, budget_query, organization_query, document_id,
  document_number, kfsr_code, kcsr_code, kvr_code, kvsr_code, kesr_code,
  kosgu_code, purpose_code, funding_source
- group_by: массив строк или null

Правила:
- если пользователь просит один показатель, верни ровно один metric
- если пользователь не указал даты, верни null
- если пользователь просит по месяцам, верни group_by=["month"]
- если пользователь просит по годам, верни group_by=["year"]
- если пользователь просит по объектам, верни group_by=["object_name"]
- если пользователь просит по организациям, верни group_by=["organization_name"]
- если пользователь просит по источникам, верни group_by=["source_group"]
- если пользователь просит по показателям, верни group_by=["metric"]
- города, муниципалитеты и объекты клади в filters.object_query
- организации, министерства, учреждения и отделы клади в filters.organization_query
- source_groups допускает только массив строк, остальные поля filters должны быть строкой или null

Доступные metrics:
limits, obligations, obligations_without_bo, remaining_limits, cash_payments,
agreement_amount, contract_amount, contract_payment,
institution_payments_with_refund, institution_payments_execution, institution_payments_recovery

Доступные source_groups:
rchb, agreements, gz, buau

Часто встречающиеся значения:
- objects: Благовещенск, Свободный, Тында, Авиабаза
- budgets: Бюджет города Благовещенска, Бюджет города Свободного, Бюджет г. Тынды, Областной бюджет Амурской области
- organizations: Администрация города Тынды, Министерство финансов Амурской области, ГАУ Амурской области "Авиабаза", Министерство образования Амурской области
- kfsr_code: 0502, 0702, 0408
- kcsr_code: 03.2.01.61058, 01.4.02.00000, 05.1.01.12345
- kvr_code: 8.1.2, 244, 414
- funding_source: Региональные средства, Федеральные средства
- purpose_code: ОБ-1, ОБ-136-4
"""


FILTER_KEYS = [
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
]


@dataclass(frozen=True)
class ExampleSpec:
    text_query: str
    target: dict


def empty_filters() -> dict:
    return {key: None for key in FILTER_KEYS}


def make_target(
    *,
    metrics: list[str] | None = None,
    group_by: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    **filters: str | list[str] | None,
) -> dict:
    payload_filters = empty_filters()
    for key, value in filters.items():
        if key not in payload_filters:
            raise KeyError(f"Unsupported filter field: {key}")
        payload_filters[key] = value
    return {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
        "filters": payload_filters,
        "group_by": group_by,
    }


def make_prompt(text_query: str) -> str:
    return (
        f"{SYSTEM_TASK_PROMPT}\n\n"
        f"Запрос пользователя:\n{text_query}\n\n"
        "Верни только JSON:"
    )


def make_record(example: ExampleSpec) -> dict:
    completion = json.dumps(example.target, ensure_ascii=False, indent=2)
    return {
        "task": "budget_query_to_json",
        "text_query": example.text_query,
        "prompt": make_prompt(example.text_query),
        "completion": completion,
        "target": example.target,
    }


def generate_examples() -> list[ExampleSpec]:
    examples: list[ExampleSpec] = []
    add = examples.append

    core_examples = [
        ExampleSpec(
            "Покажи лимиты по Благовещенску по месяцам",
            make_target(metrics=["limits"], object_query="Благовещенск", group_by=["month"]),
        ),
        ExampleSpec(
            "Покажи кассовые выплаты по 0502",
            make_target(metrics=["cash_payments"], kfsr_code="0502"),
        ),
        ExampleSpec(
            "Покажи сумму контрактов по источнику gz",
            make_target(metrics=["contract_amount"], source_groups=["gz"]),
        ),
        ExampleSpec(
            "Покажи соглашения по Авиабазе по годам",
            make_target(metrics=["agreement_amount"], object_query="Авиабаза", group_by=["year"]),
        ),
        ExampleSpec(
            "Покажи данные по Благовещенску",
            make_target(metrics=None, object_query="Благовещенск"),
        ),
        ExampleSpec(
            'Покажи кассовые выплаты по организации ГАУ Амурской области "Авиабаза"',
            make_target(metrics=["cash_payments"], organization_query='ГАУ Амурской области "Авиабаза"'),
        ),
        ExampleSpec(
            "Покажи лимиты и кассовые выплаты по Благовещенску по месяцам",
            make_target(metrics=["limits", "cash_payments"], object_query="Благовещенск", group_by=["month"]),
        ),
        ExampleSpec(
            "Покажи данные по документу 1211004698498",
            make_target(metrics=None, document_id="1211004698498"),
        ),
        ExampleSpec(
            "Покажи сумму соглашений по номеру документа 637/1",
            make_target(metrics=["agreement_amount"], document_number="637/1"),
        ),
        ExampleSpec(
            "Покажи платежи по контрактам по источнику gz по месяцам",
            make_target(metrics=["contract_payment"], source_groups=["gz"], group_by=["month"]),
        ),
        ExampleSpec(
            "Покажи выплаты БУАУ с учетом возврата по годам",
            make_target(metrics=["institution_payments_with_refund"], group_by=["year"]),
        ),
        ExampleSpec(
            "Покажи исполнение БУАУ по организациям",
            make_target(metrics=["institution_payments_execution"], group_by=["organization_name"]),
        ),
        ExampleSpec(
            "Покажи восстановление выплат БУАУ по источникам",
            make_target(metrics=["institution_payments_recovery"], group_by=["source_group"]),
        ),
        ExampleSpec(
            "Покажи лимиты по бюджету города Благовещенска",
            make_target(metrics=["limits"], budget_query="Бюджет города Благовещенска"),
        ),
        ExampleSpec(
            "Покажи остаток лимитов по Благовещенску с 01.01.2025 по 31.12.2025",
            make_target(
                metrics=["remaining_limits"],
                object_query="Благовещенск",
                date_from="2025-01-01",
                date_to="2025-12-31",
            ),
        ),
        ExampleSpec(
            "Покажи обязательства без БО по Тынде по годам",
            make_target(metrics=["obligations_without_bo"], object_query="Тында", group_by=["year"]),
        ),
    ]
    examples.extend(core_examples)

    object_variants = [
        ("Благовещенску", "Благовещенск"),
        ("Свободному", "Свободный"),
        ("Тынде", "Тында"),
        ("Авиабазе", "Авиабаза"),
    ]
    budget_variants = [
        ("бюджету города Благовещенска", "Бюджет города Благовещенска"),
        ("бюджету города Свободного", "Бюджет города Свободного"),
        ("бюджету г. Тынды", "Бюджет г. Тынды"),
        ("областному бюджету Амурской области", "Областной бюджет Амурской области"),
    ]
    organization_variants = [
        ("Администрации города Тынды", "Администрация города Тынды"),
        ("Министерству финансов Амурской области", "Министерство финансов Амурской области"),
        ('ГАУ Амурской области "Авиабаза"', 'ГАУ Амурской области "Авиабаза"'),
        ("Министерству образования Амурской области", "Министерство образования Амурской области"),
    ]
    date_ranges = [
        ("с 01.01.2025 по 31.12.2025", "2025-01-01", "2025-12-31"),
        ("с 10.02.2025 по 01.05.2026", "2025-02-10", "2026-05-01"),
        ("за период с 01.03.2025 по 30.09.2025", "2025-03-01", "2025-09-30"),
    ]
    metric_variants = [
        ("limits", ["лимиты", "объем лимитов", "лимиты финансирования"]),
        ("obligations", ["обязательства", "подтвержденные лимиты по БО"]),
        ("obligations_without_bo", ["обязательства без бо", "лимиты без БО"]),
        ("remaining_limits", ["остаток лимитов", "остаточные лимиты"]),
        ("cash_payments", ["кассовые выплаты", "кассовое исполнение"]),
        ("agreement_amount", ["сумму соглашений", "объем соглашений"]),
        ("contract_amount", ["сумму контрактов", "объем контрактов"]),
        ("contract_payment", ["платежи по контрактам", "оплату по контрактам"]),
        ("institution_payments_with_refund", ["выплаты буау с учетом возврата"]),
        ("institution_payments_execution", ["исполнение буау", "выплаты буау исполнение"]),
        ("institution_payments_recovery", ["восстановление выплат буау"]),
    ]
    grouping_variants = [
        (None, ["", ""]),
        (["month"], ["по месяцам", "помесячно"]),
        (["year"], ["по годам", "ежегодно"]),
        (["object_name"], ["по объектам"]),
        (["organization_name"], ["по организациям"]),
        (["source_group"], ["по источникам"]),
        (["metric"], ["по показателям"]),
    ]
    source_group_variants = [
        ("rchb", ["по источнику rchb", "из рчб"]),
        ("agreements", ["по источнику agreements", "из соглашений"]),
        ("gz", ["по источнику gz", "из gz"]),
        ("buau", ["по источнику buau", "из буау"]),
    ]

    compatible_metrics = {
        "rchb": {"limits", "obligations", "obligations_without_bo", "remaining_limits", "cash_payments"},
        "agreements": {"agreement_amount"},
        "gz": {"contract_amount", "contract_payment"},
        "buau": {
            "institution_payments_with_refund",
            "institution_payments_execution",
            "institution_payments_recovery",
        },
    }

    for metric_key, phrases in metric_variants:
        for query_word in ["Покажи", "Выведи", "Нужны", "Построй"]:
            if metric_key.startswith("institution_payments_"):
                break
            for inflected_object, canonical_object in object_variants[:3]:
                for group_by, group_phrases in grouping_variants[:3]:
                    phrase = phrases[(len(canonical_object) + len(query_word)) % len(phrases)]
                    suffix = group_phrases[0] if group_by else ""
                    query = f"{query_word} {phrase} по {inflected_object} {suffix}".strip()
                    add(
                        ExampleSpec(
                            query,
                            make_target(metrics=[metric_key], object_query=canonical_object, group_by=group_by),
                        )
                    )

    for metric_key, phrases in metric_variants:
        if metric_key.startswith("institution_payments_"):
            continue
        for query_word in ["Покажи", "Выведи"]:
            for organization_text, canonical_organization in organization_variants:
                phrase = phrases[(len(canonical_organization) + len(query_word)) % len(phrases)]
                query = f"{query_word} {phrase} по организации {organization_text}"
                add(
                    ExampleSpec(
                        query,
                        make_target(metrics=[metric_key], organization_query=canonical_organization),
                    )
                )

    for metric_key, phrases in metric_variants:
        if metric_key.startswith("institution_payments_"):
            continue
        for budget_text, canonical_budget in budget_variants:
            phrase = phrases[len(canonical_budget) % len(phrases)]
            query = f"Покажи {phrase} по {budget_text}"
            add(
                ExampleSpec(
                    query,
                    make_target(metrics=[metric_key], budget_query=canonical_budget),
                )
            )

    for source_group, source_phrases in source_group_variants:
        for metric_key in compatible_metrics[source_group]:
            phrase = next(phrases for key, phrases in metric_variants if key == metric_key)[0]
            query = f"Покажи {phrase} {source_phrases[0]}"
            add(
                ExampleSpec(
                    query,
                    make_target(metrics=[metric_key], source_groups=[source_group]),
                )
            )
            query = f"Покажи {phrase} {source_phrases[1]} по месяцам"
            add(
                ExampleSpec(
                    query,
                    make_target(metrics=[metric_key], source_groups=[source_group], group_by=["month"]),
                )
            )

    code_examples = [
        ("kfsr_code", "0502", ["лимиты", "кассовые выплаты", "обязательства"]),
        ("kcsr_code", "03.2.01.61058", ["лимиты", "кассовые выплаты"]),
        ("kvr_code", "8.1.2", ["лимиты", "сумму контрактов"]),
        ("purpose_code", "ОБ-1", ["лимиты", "обязательства"]),
        ("funding_source", "Региональные средства", ["лимиты", "кассовые выплаты"]),
        ("funding_source", "Федеральные средства", ["сумму соглашений", "сумму контрактов"]),
    ]
    phrase_to_metric = {
        "лимиты": "limits",
        "кассовые выплаты": "cash_payments",
        "обязательства": "obligations",
        "сумму контрактов": "contract_amount",
        "сумму соглашений": "agreement_amount",
    }
    field_labels = {
        "kfsr_code": "КФСР",
        "kcsr_code": "КЦСР",
        "kvr_code": "КВР",
        "purpose_code": "коду цели",
        "funding_source": "источнику средств",
    }
    for field_name, value, phrases in code_examples:
        for phrase in phrases:
            metric_key = phrase_to_metric[phrase]
            if field_name == "funding_source":
                query = f"Покажи {phrase} по {field_labels[field_name]} {value}"
            elif field_name == "purpose_code":
                query = f"Покажи {phrase} по {field_labels[field_name]} {value}"
            else:
                query = f"Покажи {phrase} по {field_labels[field_name]} {value}"
            add(ExampleSpec(query, make_target(metrics=[metric_key], **{field_name: value})))
            add(
                ExampleSpec(
                    f"{query} по годам",
                    make_target(metrics=[metric_key], group_by=["year"], **{field_name: value}),
                )
            )

    date_metric_pairs = [
        ("limits", "лимиты"),
        ("cash_payments", "кассовые выплаты"),
        ("agreement_amount", "сумму соглашений"),
        ("contract_amount", "сумму контрактов"),
    ]
    for metric_key, metric_phrase in date_metric_pairs:
        for inflected_object, canonical_object in object_variants:
            for date_text, date_from, date_to in date_ranges:
                query = f"Покажи {metric_phrase} по {inflected_object} {date_text}"
                add(
                    ExampleSpec(
                        query,
                        make_target(
                            metrics=[metric_key],
                            object_query=canonical_object,
                            date_from=date_from,
                            date_to=date_to,
                        ),
                    )
                )

    multi_metric_examples = [
        (
            "Покажи лимиты и кассовые выплаты по Благовещенску по годам",
            make_target(metrics=["limits", "cash_payments"], object_query="Благовещенск", group_by=["year"]),
        ),
        (
            "Покажи лимиты и обязательства по Свободному",
            make_target(metrics=["limits", "obligations"], object_query="Свободный"),
        ),
        (
            "Покажи кассовые выплаты и остаток лимитов по Тынде по месяцам",
            make_target(
                metrics=["cash_payments", "remaining_limits"],
                object_query="Тында",
                group_by=["month"],
            ),
        ),
        (
            'Покажи лимиты и кассовые выплаты по организации ГАУ Амурской области "Авиабаза"',
            make_target(
                metrics=["limits", "cash_payments"],
                organization_query='ГАУ Амурской области "Авиабаза"',
            ),
        ),
        (
            "Покажи контрактную сумму и платежи по контрактам по источнику gz",
            make_target(metrics=["contract_amount", "contract_payment"], source_groups=["gz"]),
        ),
        (
            "Покажи выплаты БУАУ с учетом возврата и исполнение БУАУ по годам",
            make_target(
                metrics=["institution_payments_with_refund", "institution_payments_execution"],
                group_by=["year"],
            ),
        ),
    ]
    examples.extend(ExampleSpec(text, target) for text, target in multi_metric_examples)

    generic_queries = [
        ExampleSpec("Покажи данные по Свободному по годам", make_target(object_query="Свободный", group_by=["year"])),
        ExampleSpec(
            "Покажи данные по организации Администрация города Тынды",
            make_target(organization_query="Администрация города Тынды"),
        ),
        ExampleSpec(
            "Покажи данные по бюджету города Благовещенска по месяцам",
            make_target(budget_query="Бюджет города Благовещенска", group_by=["month"]),
        ),
        ExampleSpec("Покажи данные по источнику gz", make_target(source_groups=["gz"])),
        ExampleSpec("Покажи данные по КФСР 0702", make_target(kfsr_code="0702")),
        ExampleSpec("Покажи данные по показателям", make_target(group_by=["metric"])),
        ExampleSpec(
            "Покажи данные по Министерству финансов Амурской области по организациям",
            make_target(
                organization_query="Министерство финансов Амурской области",
                group_by=["organization_name"],
            ),
        ),
    ]
    examples.extend(generic_queries)

    deduped: dict[str, ExampleSpec] = {}
    for example in examples:
        deduped[example.text_query] = example
    return list(deduped.values())


def split_examples(examples: list[ExampleSpec]) -> tuple[list[dict], list[dict]]:
    records = [make_record(example) for example in examples]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(records)
    val_size = max(12, int(len(records) * VAL_RATIO))
    val_records = records[:val_size]
    train_records = records[val_size:]
    return train_records, val_records


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_readme(train_count: int, val_count: int) -> None:
    text = f"""# Budget Query SFT Dataset

Датасет подготовлен для дообучения модели на задаче:

`text query -> JSON filters`

## Файлы

- `budget_query_sft_train.jsonl` — обучающая выборка
- `budget_query_sft_val.jsonl` — валидационная выборка

## Размер

- train: `{train_count}`
- val: `{val_count}`

## Формат записи

Каждая строка в `.jsonl` содержит:

- `task`
- `text_query`
- `prompt`
- `completion`
- `target`

Для обучения через `TRL SFTTrainer` удобнее всего использовать формат `prompt` + `completion`.

## Сценарии

Датасет покрывает:

- метрики `limits`, `cash_payments`, `agreement_amount`, `contract_amount`, `contract_payment`
- бюджетные показатели `obligations`, `obligations_without_bo`, `remaining_limits`
- фильтры по `object_query`, `organization_query`, `budget_query`
- фильтры по `source_groups`, `kfsr_code`, `kcsr_code`, `kvr_code`, `purpose_code`, `funding_source`
- даты
- группировки по месяцам, годам, объектам, организациям, источникам и показателям
- одиночные и множественные метрики
"""
    README_FILE.write_text(text, encoding="utf-8")


def notebook_cells() -> list[dict]:
    return [
        markdown_cell(
            "# Дообучение YandexGPT-5-Lite-8B-pretrain\n"
            "\n"
            "Ноутбук подготавливает LoRA/SFT-обучение для задачи преобразования русских аналитических запросов в JSON-фильтры API."
        ),
        markdown_cell(
            "## Что нужно до запуска\n"
            "\n"
            "- GPU с CUDA и желательно 16+ GB VRAM\n"
            "- `HF_TOKEN` в корневом `.env`\n"
            "- датасет уже лежит в `training/llm_sft/`\n"
            "\n"
            "Модель `yandex/YandexGPT-5-Lite-8B-pretrain` в model card описана как **llama-like**, поэтому для LoRA можно использовать обычный стек `Transformers + PEFT + TRL`."
        ),
        code_cell(
            "!pip install -q datasets transformers accelerate peft trl bitsandbytes sentencepiece huggingface_hub"
        ),
        code_cell(
            "from __future__ import annotations\n"
            "\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "\n"
            "import torch\n"
            "from datasets import load_dataset\n"
            "from huggingface_hub import login\n"
            "from peft import LoraConfig, prepare_model_for_kbit_training\n"
            "from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig\n"
            "from trl import SFTConfig, SFTTrainer\n"
        ),
        code_cell(
            "def load_env_file(path: Path) -> None:\n"
            "    if not path.exists():\n"
            "        return\n"
            "    for raw_line in path.read_text(encoding='utf-8').splitlines():\n"
            "        line = raw_line.strip()\n"
            "        if not line or line.startswith('#') or '=' not in line:\n"
            "            continue\n"
            "        key, value = line.split('=', 1)\n"
            "        os.environ.setdefault(key.strip(), value.strip().strip('\"').strip(\"'\"))\n"
            "\n"
            "repo_root = Path.cwd()\n"
            "if not (repo_root / '.env').exists() and (repo_root.parent / '.env').exists():\n"
            "    repo_root = repo_root.parent\n"
            "\n"
            "load_env_file(repo_root / '.env')\n"
            "hf_token = os.getenv('HF_TOKEN')\n"
            "if not hf_token:\n"
            "    raise RuntimeError('HF_TOKEN не найден в .env')\n"
            "\n"
            "login(token=hf_token, add_to_git_credential=False)\n"
            "print('HF token loaded successfully')"
        ),
        code_cell(
            "MODEL_NAME = 'yandex/YandexGPT-5-Lite-8B-pretrain'\n"
            "TRAIN_PATH = repo_root / 'training' / 'llm_sft' / 'budget_query_sft_train.jsonl'\n"
            "VAL_PATH = repo_root / 'training' / 'llm_sft' / 'budget_query_sft_val.jsonl'\n"
            "OUTPUT_DIR = repo_root / 'artifacts' / 'yandexgpt5-lite-budget-query-lora'\n"
            "\n"
            "MAX_SEQ_LENGTH = 1536\n"
            "print(TRAIN_PATH)\n"
            "print(VAL_PATH)"
        ),
        code_cell(
            "dataset = load_dataset(\n"
            "    'json',\n"
            "    data_files={'train': str(TRAIN_PATH), 'validation': str(VAL_PATH)},\n"
            ")\n"
            "dataset"
        ),
        code_cell(
            "sample = dataset['train'][0]\n"
            "print(sample['text_query'])\n"
            "print(sample['prompt'][:700])\n"
            "print(sample['completion'])"
        ),
        code_cell(
            "if not torch.cuda.is_available():\n"
            "    raise RuntimeError('Для дообучения нужен GPU с CUDA. На CPU этот ноутбук не рассчитан.')\n"
            "\n"
            "bnb_config = BitsAndBytesConfig(\n"
            "    load_in_4bit=True,\n"
            "    bnb_4bit_quant_type='nf4',\n"
            "    bnb_4bit_use_double_quant=True,\n"
            "    bnb_4bit_compute_dtype=torch.bfloat16,\n"
            ")\n"
            "\n"
            "tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, token=hf_token, legacy=False)\n"
            "if tokenizer.pad_token is None:\n"
            "    tokenizer.pad_token = tokenizer.eos_token\n"
            "tokenizer.padding_side = 'right'\n"
            "\n"
            "model = AutoModelForCausalLM.from_pretrained(\n"
            "    MODEL_NAME,\n"
            "    token=hf_token,\n"
            "    device_map='auto',\n"
            "    torch_dtype=torch.bfloat16,\n"
            "    quantization_config=bnb_config,\n"
            ")\n"
            "model.config.use_cache = False\n"
            "model = prepare_model_for_kbit_training(model)"
        ),
        code_cell(
            "lora_config = LoraConfig(\n"
            "    r=16,\n"
            "    lora_alpha=32,\n"
            "    lora_dropout=0.05,\n"
            "    bias='none',\n"
            "    task_type='CAUSAL_LM',\n"
            "    target_modules='all-linear',\n"
            ")\n"
            "\n"
            "training_args = SFTConfig(\n"
            "    output_dir=str(OUTPUT_DIR),\n"
            "    max_seq_length=MAX_SEQ_LENGTH,\n"
            "    per_device_train_batch_size=1,\n"
            "    per_device_eval_batch_size=1,\n"
            "    gradient_accumulation_steps=16,\n"
            "    num_train_epochs=3,\n"
            "    learning_rate=2e-4,\n"
            "    lr_scheduler_type='cosine',\n"
            "    warmup_ratio=0.05,\n"
            "    logging_steps=10,\n"
            "    eval_strategy='steps',\n"
            "    eval_steps=50,\n"
            "    save_steps=50,\n"
            "    save_total_limit=2,\n"
            "    bf16=True,\n"
            "    gradient_checkpointing=True,\n"
            "    completion_only_loss=True,\n"
            "    report_to='none',\n"
            "    optim='paged_adamw_8bit',\n"
            ")\n"
            "\n"
            "trainer = SFTTrainer(\n"
            "    model=model,\n"
            "    args=training_args,\n"
            "    train_dataset=dataset['train'],\n"
            "    eval_dataset=dataset['validation'],\n"
            "    peft_config=lora_config,\n"
            ")\n"
            "trainer.model.print_trainable_parameters()"
        ),
        code_cell("trainer.train()"),
        code_cell(
            "trainer.save_model(str(OUTPUT_DIR / 'adapter'))\n"
            "tokenizer.save_pretrained(str(OUTPUT_DIR / 'adapter'))"
        ),
        code_cell(
            "test_queries = [\n"
            "    'Покажи лимиты по Благовещенску по месяцам',\n"
            "    'Покажи кассовые выплаты по 0502',\n"
            "    'Покажи сумму контрактов по источнику gz',\n"
            "]\n"
            "\n"
            "def build_inference_prompt(query: str) -> str:\n"
            "    return (\n"
            "        'Ты преобразуешь русский запрос к системе бюджетной аналитики в JSON для API. '\n"
            "        'Верни только JSON без пояснений.\\n\\n'\n"
            "        f'Запрос пользователя:\\n{query}\\n\\nВерни только JSON:'\n"
            "    )\n"
            "\n"
            "for query in test_queries:\n"
            "    prompt = build_inference_prompt(query)\n"
            "    inputs = tokenizer(prompt, return_tensors='pt').to(model.device)\n"
            "    with torch.no_grad():\n"
            "        outputs = model.generate(**inputs, max_new_tokens=220, temperature=0.0, do_sample=False)\n"
            "    generated = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)\n"
            "    print('QUERY:', query)\n"
            "    print(generated)\n"
            "    print('-' * 80)"
        ),
    ]


def markdown_cell(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source.splitlines()],
    }


def code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source.splitlines()],
    }


def write_notebook() -> None:
    notebook = {
        "cells": notebook_cells(),
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_FILE.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(train_count: int, val_count: int, total_count: int) -> None:
    payload = {
        "task": "budget_query_to_json",
        "generator": "scripts/generate_budget_sft_assets.py",
        "random_seed": RANDOM_SEED,
        "train_records": train_count,
        "validation_records": val_count,
        "total_records": total_count,
        "base_model": "yandex/YandexGPT-5-Lite-8B-pretrain",
        "files": {
            "train": str(TRAIN_FILE.relative_to(REPO_ROOT)),
            "validation": str(VAL_FILE.relative_to(REPO_ROOT)),
            "readme": str(README_FILE.relative_to(REPO_ROOT)),
            "notebook": str(NOTEBOOK_FILE.relative_to(REPO_ROOT)),
        },
        "schema": {
            "root_keys": ["date_from", "date_to", "metrics", "filters", "group_by"],
            "filter_keys": FILTER_KEYS,
        },
    }
    MANIFEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    examples = generate_examples()
    train_records, val_records = split_examples(examples)

    write_jsonl(TRAIN_FILE, train_records)
    write_jsonl(VAL_FILE, val_records)
    write_readme(len(train_records), len(val_records))
    write_manifest(len(train_records), len(val_records), len(train_records) + len(val_records))
    write_notebook()

    print(f"Generated train dataset: {TRAIN_FILE} ({len(train_records)} records)")
    print(f"Generated val dataset:   {VAL_FILE} ({len(val_records)} records)")
    print(f"Generated notebook:      {NOTEBOOK_FILE}")


if __name__ == "__main__":
    main()
