# Budget Query SFT Dataset

Датасет подготовлен для дообучения модели на задаче:

`text query -> JSON filters`

## Файлы

- `budget_query_sft_train.jsonl` — обучающая выборка
- `budget_query_sft_val.jsonl` — валидационная выборка

## Размер

- train: `426`
- val: `80`

## Формат записи

Каждая строка в `.jsonl` содержит:

- `task`
- `text_query`
- `prompt`
- `completion`
- `target`

Для обучения через `TRL SFTTrainer` удобнее всего использовать формат `prompt` + `completion`.

## Важно для HuggingFace Datasets

Если загружать `.jsonl` напрямую через `load_dataset("json", ...)`, можно поймать ошибку вида:

`TypeError: Couldn't cast array of type string to null`

Причина в том, что часть полей в `target` опциональна. Например:

- в `train` поле `target.filters.document_id` может быть только `null`
- а в `validation` там уже встречается строка

Без явной схемы `datasets` иногда выводит для такого поля тип `null`, а потом не может привести строку к `null`.

Используй готовый загрузчик с зафиксированными `features`:

```python
from training.llm_sft.dataset_loader import load_budget_query_sft_dataset

dataset = load_budget_query_sft_dataset(cache_dir="/tmp/hf-datasets-cache")
```

## Сценарии

Датасет покрывает:

- метрики `limits`, `cash_payments`, `agreement_amount`, `contract_amount`, `contract_payment`
- бюджетные показатели `obligations`, `obligations_without_bo`, `remaining_limits`
- фильтры по `object_query`, `organization_query`, `budget_query`
- фильтры по `source_groups`, `kfsr_code`, `kcsr_code`, `kvr_code`, `purpose_code`, `funding_source`
- даты
- группировки по месяцам, годам, объектам, организациям, источникам и показателям
- одиночные и множественные метрики
