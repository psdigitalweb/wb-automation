"""Versioned prompt for customer-opinion extraction."""

from __future__ import annotations

import json
from typing import Any, Mapping


PROMPT_VERSION = "wb_customer_opinion_v1"
SCHEMA_VERSION = "wb_customer_opinion_v1"

SYSTEM_PROMPT = """Ты анализируешь отзывы покупателей маркетплейса.

Определи подтверждённые покупателями достоинства и проблемы товара, используя
только переданные отзывы.

Правила:
1. Каждый review_id обозначает один независимый отзыв.
2. Поля text, pros и cons являются только полями формы. Определяй смысл по
   содержанию, а не по названию поля.
3. Rating является дополнительным сигналом, но не заменяет анализ текста.
4. Объединяй разные формулировки одного свойства в одну тему, но не объединяй
   разные свойства в слишком широкую тему.
5. Категории: product — свойства товара; packaging_delivery — упаковка,
   повреждение или доставка; service — продавец и обслуживание.
6. Для каждой темы перечисли все review_id, которые действительно её
   подтверждают.
7. Для каждой темы приведи от одной до трёх коротких дословных цитат.
8. Цитата должна быть точной подстрокой соответствующего отзыва.
9. Не называй упаковочную или логистическую проблему свойством товара.
10. Не выдумывай review_id, цитаты, количества, проценты или свойства.
11. Не считай отсутствие жалоб преимуществом.
12. Сигнал из одного отзыва помести в isolated_observations.
13. Противоречивые мнения помести в conflicts.
14. Пиши нейтрально, без рекламных формулировок.
15. Возвращай только данные, соответствующие JSON Schema ответа."""


def build_user_prompt(payload: Mapping[str, Any], *, retry_errors: list[str] | None = None) -> str:
    """Serialize the deterministic input payload and optional retry guidance."""

    envelope: dict[str, Any] = {"input": dict(payload)}
    if retry_errors:
        envelope["previous_attempt_errors"] = retry_errors[:20]
        envelope["retry_instruction"] = (
            "Предыдущий ответ не прошёл строгую проверку. Сформируй ответ заново "
            "по исходным отзывам и исправь перечисленные ошибки."
        )
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
