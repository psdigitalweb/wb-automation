# Category expressive input preview (reviews-only vs reviews+titles)

Date: 2026-04-21

## 1) Category selection
- project_id: `1`
- category_id: `821`
- category_name: `Тарелки`
- sku_total (products in category): `25`
- sku_with_reviews (any rating): `8`
- reviews_total (all ratings): `51`
- reviews_rating>=4 (non-empty text/pros/cons): `8`

## 2) Preview counts (after truncation + dedup)
- reviews count after dedup: `8`
- titles count after dedup: `5`

## 3) 10 sample reviews
```
Прекрасная тарелочка, запакована хорошо, приехала целая и невредимая 🥰💗
весной буду ей пользоваться вместе с кружечкой из этой же серии с зайчиками, получился весенний комплект посудки ✨
Спасибо большое за товар!)

Тарелка пришла целая, упакована хорошо.

Стерт местами принт, расстроилась, заказывала на подарок

понравилось все

Есть небольшая дырочка, брала на подарок

Прекрасная тарелочка

Тарелка, как на картинке, печать рисунка качественная, упаковано в пупырку и коробочку. Пришло все целое. Спасибо продавцу за качественный товар.

Сама тарелка хорошая.Но упаковка немного разочаровала, как будто она по пути пару раз упала. А так всё хорошо.

```

## 4) 10 sample titles
```
Тарелка керамическая/с рисунком/милая
Тарелка керамическая "Bunny"
Тарелка керамическая "Coffee time"
Тарелка керамическая "Я наевси пустых обещаний"
Тарелка керамическая Lunch time
```

## 5) Payload A (reviews-only) — exact
```json
{
  "category_name": "Тарелки",
  "reviews": [
    "Прекрасная тарелочка, запакована хорошо, приехала целая и невредимая 🥰💗\nвесной буду ей пользоваться вместе с кружечкой из этой же серии с зайчиками, получился весенний комплект посудки ✨\nСпасибо большое за товар!)",
    "Тарелка пришла целая, упакована хорошо.",
    "Стерт местами принт, расстроилась, заказывала на подарок",
    "понравилось все",
    "Есть небольшая дырочка, брала на подарок",
    "Прекрасная тарелочка",
    "Тарелка, как на картинке, печать рисунка качественная, упаковано в пупырку и коробочку. Пришло все целое. Спасибо продавцу за качественный товар.",
    "Сама тарелка хорошая.Но упаковка немного разочаровала, как будто она по пути пару раз упала. А так всё хорошо."
  ]
}
```

## 6) Payload B (reviews + titles) — exact
```json
{
  "category_name": "Тарелки",
  "reviews": [
    "Прекрасная тарелочка, запакована хорошо, приехала целая и невредимая 🥰💗\nвесной буду ей пользоваться вместе с кружечкой из этой же серии с зайчиками, получился весенний комплект посудки ✨\nСпасибо большое за товар!)",
    "Тарелка пришла целая, упакована хорошо.",
    "Стерт местами принт, расстроилась, заказывала на подарок",
    "понравилось все",
    "Есть небольшая дырочка, брала на подарок",
    "Прекрасная тарелочка",
    "Тарелка, как на картинке, печать рисунка качественная, упаковано в пупырку и коробочку. Пришло все целое. Спасибо продавцу за качественный товар.",
    "Сама тарелка хорошая.Но упаковка немного разочаровала, как будто она по пути пару раз упала. А так всё хорошо."
  ],
  "titles": [
    "Тарелка керамическая/с рисунком/милая",
    "Тарелка керамическая \"Bunny\"",
    "Тарелка керамическая \"Coffee time\"",
    "Тарелка керамическая \"Я наевси пустых обещаний\"",
    "Тарелка керамическая Lunch time"
  ]
}
```

## 7) Prompt A (reviews-only) — exact
```
TASK=category_expressive_from_reviews
You will receive JSON payload with:
- category_name
- reviews[] (primary evidence)

Rules:
- Do not invent. If no signals, return empty vibes.
- Every vibe MUST have evidence_spans (exact substrings from reviews).
- evidence_spans must be <= 80 chars and contain no newlines.
- Return JSON only.

Return schema:
{
  "version": "v1",
  "task": "category",
  "category_name": "Тарелки",
  "vibes": [
    {
      "label": "other",
      "confidence": 0.0,
      "evidence_spans": ["..."],
      "notes": ""
    }
  ],
  "summary": "",
  "warnings": []
}

```

## 8) Prompt B (reviews + titles) — exact
```
TASK=category_expressive_from_reviews_plus_titles
You will receive JSON payload with:
- category_name
- reviews[] (PRIMARY evidence)
- titles[] (SECONDARY support)

Rules:
- Reviews are PRIMARY evidence.
- Titles are SECONDARY support only.
- No conclusion may rely on titles alone if unsupported by reviews.
- Do not invent. If no signals, return empty vibes.
- Every vibe MUST have evidence_spans (exact substrings from reviews).
- evidence_spans must be <= 80 chars and contain no newlines.
- Return JSON only.

Return schema:
{
  "version": "v1",
  "task": "category",
  "category_name": "Тарелки",
  "vibes": [
    {
      "label": "other",
      "confidence": 0.0,
      "evidence_spans": ["..."],
      "notes": ""
    }
  ],
  "summary": "",
  "warnings": []
}

```

## 9) Size estimates

| Item | chars | approx_tokens |
| --- | ---: | ---: |
| payload A JSON | 755 | 189 |
| payload B JSON | 996 | 249 |
| prompt A | 589 | 148 |
| prompt B | 769 | 193 |
