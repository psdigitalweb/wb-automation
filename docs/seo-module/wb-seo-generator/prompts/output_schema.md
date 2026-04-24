# Output Schema — формат выхода LLM

LLM возвращает текстовый ответ со строго определёнными разделителями. Парсер разрезает его по разделителям и валидирует pydantic-моделью `GeneratedCard`.

---

## Разделители

Ответ состоит из четырёх секций в фиксированном порядке, каждая открывается разделителем вида:

```
===== НАЗВАНИЕ =====
===== ХАРАКТЕРИСТИКИ =====
===== ОПИСАНИЕ =====
===== ОТЧЁТ =====
```

Разделитель — ровно пять знаков равенства с каждой стороны, с пробелами вокруг текста. Парсер НЕ должен использовать регулярки для поиска — только `str.split(разделитель)`. Если какой-то из разделителей отсутствует в ответе — это ошибка парсинга, уходит в retry с сообщением LLM «ты не использовал один из обязательных разделителей: X».

---

## Содержимое секций

### НАЗВАНИЕ

Одна строка текста, без префиксов и суффиксов.

```
Рюкзак женский городской для ноутбука 14 нейлон
```

### ХАРАКТЕРИСТИКИ

Минимум 8 пар `<поле>: <значение>`, по одной на строку. Разделитель между полем и значением — двоеточие с пробелом. Пустые строки игнорируются парсером.

```
Материал: нейлон 600D с водоотталкивающей пропиткой
Объём, л: 14
Вес, г: 480
...
```

### ОПИСАНИЕ

Связный текст, разбитый на 6 блоков. Блоки отделены ровно одной пустой строкой. Блоки не озаглавлены (без «Блок 1», «Блок 2» и т.п.).

### ОТЧЁТ

Четыре поля в YAML-совместимом формате:

```
охват_кластеров: 9
использованные_запросы: ["...", "..."]
не_использованные_запросы: ["...", "..."]
скрытые_зоны_задействованы: ["..."]
```

Парсер использует `yaml.safe_load` после извлечения секции.

---

## Pydantic-модель

```python
from pydantic import BaseModel, Field


class Report(BaseModel):
    coverage: int = Field(alias="охват_кластеров", ge=0)
    used_queries: list[str] = Field(alias="использованные_запросы", default_factory=list)
    unused_queries: list[str] = Field(alias="не_использованные_запросы", default_factory=list)
    hidden_zones: list[str] = Field(alias="скрытые_зоны_задействованы", default_factory=list)

    model_config = {"populate_by_name": True}


class Characteristic(BaseModel):
    field: str
    value: str


class GeneratedCard(BaseModel):
    title: str                    # Название
    characteristics: list[Characteristic]
    description: str              # Описание
    report: Report

    def description_blocks(self) -> list[str]:
        """6 блоков описания, разделённых пустой строкой."""
        return [block.strip() for block in self.description.split("\n\n") if block.strip()]

    def char_by_field(self, field_name: str) -> str | None:
        for c in self.characteristics:
            if c.field.lower() == field_name.lower():
                return c.value
        return None

    def all_text(self) -> str:
        """Весь текст карточки для проверок «ключ встречается не более 3 раз»."""
        chars_text = " ".join(f"{c.field} {c.value}" for c in self.characteristics)
        return f"{self.title}\n{chars_text}\n{self.description}"
```

---

## Парсер (эталонная реализация)

```python
from __future__ import annotations
import yaml


SECTION_DELIMITERS = [
    "===== НАЗВАНИЕ =====",
    "===== ХАРАКТЕРИСТИКИ =====",
    "===== ОПИСАНИЕ =====",
    "===== ОТЧЁТ =====",
]


class ParseError(Exception):
    pass


def parse_llm_output(raw: str) -> GeneratedCard:
    sections = _split_sections(raw)
    title = sections["НАЗВАНИЕ"].strip()
    chars = _parse_characteristics(sections["ХАРАКТЕРИСТИКИ"])
    description = sections["ОПИСАНИЕ"].strip()
    report = _parse_report(sections["ОТЧЁТ"])
    return GeneratedCard(
        title=title,
        characteristics=chars,
        description=description,
        report=report,
    )


def _split_sections(raw: str) -> dict[str, str]:
    # Проверяем наличие всех разделителей
    for delim in SECTION_DELIMITERS:
        if delim not in raw:
            raise ParseError(f"отсутствует обязательный разделитель: {delim}")

    parts: dict[str, str] = {}
    remaining = raw
    for delim in SECTION_DELIMITERS:
        _, _, after = remaining.partition(delim)
        remaining = after

    # Вторым проходом разрезаем правильно
    for i, delim in enumerate(SECTION_DELIMITERS):
        section_name = delim.strip("= ").strip()
        start_idx = raw.find(delim) + len(delim)
        end_idx = (
            raw.find(SECTION_DELIMITERS[i + 1])
            if i + 1 < len(SECTION_DELIMITERS)
            else len(raw)
        )
        parts[section_name] = raw[start_idx:end_idx]
    return parts


def _parse_characteristics(block: str) -> list[Characteristic]:
    result: list[Characteristic] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ParseError(f"характеристика без двоеточия: {line}")
        field, _, value = line.partition(":")
        result.append(Characteristic(field=field.strip(), value=value.strip()))
    if len(result) < 8:
        raise ParseError(f"характеристик меньше 8: {len(result)}")
    return result


def _parse_report(block: str) -> Report:
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        raise ParseError(f"отчёт не парсится как YAML: {e}") from e
    if not isinstance(data, dict):
        raise ParseError("отчёт должен быть словарём")
    return Report.model_validate(data)
```

---

## Что делать, если LLM вернула мусор

Если парсер упал — это ошибка формата, а не контента. Retry с дополнением к `user`-сообщению:

```
Предыдущий ответ не удалось распарсить. Ошибка: <сообщение парсера>.
Соблюдай формат с четырьмя разделителями ===== ... ===== и структурой из системного промпта.
Не добавляй никакого текста до или после секций.
```

Если после 2 retry формат всё ещё битый — SKU помечается как `failed` с причиной `parse_error`, обработка продолжается со следующего.
