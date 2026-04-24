# Meaning Extraction MVP — Real Data Check

* Date: 2026-04-20 18:17:35 +03:00
* Base URL: `http://localhost:8000`
* Project ID: `1`

## 1) Debug endpoint discovery

OpenAPI check (PowerShell):
```powershell
(Invoke-RestMethod -Uri http://localhost:8000/openapi.json).paths.PSObject.Properties.Name | Where-Object { $_ -like '*/seo/meaning-extraction/debug' }
```

Found endpoint: `/api/v1/projects/{project_id}/seo/meaning-extraction/debug`

## 2) Local run instructions

If API is not running, start it (PowerShell):
```powershell
docker compose -f infra\\docker\\docker-compose.yml up -d --build api
```
Then open Swagger UI: `http://localhost:8000/docs`

## 3) How real DB data was selected

### 3.1 Categories (subjects)
Subjects list endpoint:
```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/v1/projects/1/marketplaces/wildberries/products/subjects
```

### 3.2 SKUs (nm_id) selection
Products source endpoint (paged):
```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/v1/products/with-latest-price?limit=200&offset=0
# ... then iterate offset until enough items for each subject_name
```

### 3.3 Query clusters (cluster_key) selection
Query pipeline debug endpoint used to obtain real cluster_key values:
```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/v1/projects/1/seo/query-pipeline/debug?category_id=<CATEGORY_ID>&tab=clusters&page=1&page_size=3
```

---

## Category `821` — Тарелки

### Category data snapshot
* `subject_name`: `Тарелки`
* `skus_count` (from subjects endpoint): `25`
* Query pipeline diagnostics: `total_queries=28258`, `total_clusters=9500`

### cluster_key picked (top 3 from query-pipeline debug)
Command used:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/query-pipeline/debug?category_id=821&tab=clusters&page=1&page_size=3" | Select-Object -ExpandProperty clusters | Select-Object -First 3
```
Selected clusters (meta):
```json
[
  {
    "cluster_key": "qcl:v1:9b57c8019c8d21a071e601c1b63e6be2afa1d13b",
    "label": "тарелки набор",
    "query_count": 92
  },
  {
    "cluster_key": "qcl:v1:8ffb40f540622fa193732405d5a2f7ad05ae2523",
    "label": "тарелки для супа",
    "query_count": 64
  },
  {
    "cluster_key": "qcl:v1:216ce4d1ab5562122979c6631069de620f13a8ee",
    "label": "тарелка для микроволновки",
    "query_count": 56
  }
]
```

### category_meaning
Command used (example):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=12812676&cluster_key=qcl%3Av1%3A9b57c8019c8d21a071e601c1b63e6be2afa1d13b"
```
Result:
```json
{
  "project_id": 1,
  "category_id": 821,
  "version": "v1_mvp",
  "functional": {
    "product_types": [
      "тарелка",
      "подарок"
    ],
    "use_cases": [
      "для завтраков",
      "для микроволновки",
      "для друзей",
      "для детей"
    ],
    "attributes": [
      "керамика",
      "китай",
      "тарелка",
      "хрупкое",
      "домашние",
      "повседневная",
      "подарки",
      "true",
      "росс",
      "использование",
      "любимой",
      "повода",
      "подруге",
      "свч",
      "день",
      "дома",
      "рождения",
      "ра01",
      "универсальный",
      "десертная",
      "детская",
      "принт",
      "ребенка",
      "марта",
      "круглая",
      "посудомоечной",
      "белый",
      "машины",
      "разрешено",
      "год",
      "картонная",
      "коробка",
      "котик",
      "новый",
      "фигурная",
      "розовый",
      "черный",
      "false",
      "еда",
      "маме"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```

### product_projection (3 SKUs)
#### nm_id `12812676` — Тарелка керамическая/с рисунком/милая
- source subject_name: `Тарелки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=12812676&cluster_key=qcl%3Av1%3A9b57c8019c8d21a071e601c1b63e6be2afa1d13b`
```json
{
  "project_id": 1,
  "category_id": 821,
  "nm_id": 12812676,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелка",
    "use_cases": [],
    "attributes": [
      "повседневная",
      "росс",
      "китай",
      "круглая",
      "тарелка",
      "керамика",
      "любимой",
      "использование",
      "свч",
      "посудомоечной",
      "домашние",
      "подарки",
      "еда",
      "хрупкое",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `33566074` — Тарелка керамическая "Breakfast".
- source subject_name: `Тарелки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=33566074&cluster_key=qcl%3Av1%3A8ffb40f540622fa193732405d5a2f7ad05ae2523`
```json
{
  "project_id": 1,
  "category_id": 821,
  "nm_id": 33566074,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелка",
    "use_cases": [],
    "attributes": [
      "маме",
      "еда",
      "хрупкое",
      "день",
      "рождения",
      "марта",
      "новый",
      "год",
      "китай",
      "тарелка",
      "керамика",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `33566075` — Тарелка керамическая "Breakfast".
- source subject_name: `Тарелки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=33566075&cluster_key=qcl%3Av1%3A216ce4d1ab5562122979c6631069de620f13a8ee`
```json
{
  "project_id": 1,
  "category_id": 821,
  "nm_id": 33566075,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелка",
    "use_cases": [],
    "attributes": [
      "тарелка",
      "маме",
      "еда",
      "китай",
      "керамика",
      "день",
      "рождения",
      "марта",
      "новый",
      "год",
      "хрупкое",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

### query_meaning (3 cluster_key)
#### cluster `qcl:v1:9b57c8019c8d21a071e601c1b63e6be2afa1d13b` — тарелки набор (query_count=92)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=12812676&cluster_key=qcl%3Av1%3A9b57c8019c8d21a071e601c1b63e6be2afa1d13b`
```json
{
  "project_id": 1,
  "category_id": 821,
  "cluster_key": "qcl:v1:9b57c8019c8d21a071e601c1b63e6be2afa1d13b",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелки",
    "use_cases": [],
    "attributes": [
      "набор"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:8ffb40f540622fa193732405d5a2f7ad05ae2523` — тарелки для супа (query_count=64)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=33566074&cluster_key=qcl%3Av1%3A8ffb40f540622fa193732405d5a2f7ad05ae2523`
```json
{
  "project_id": 1,
  "category_id": 821,
  "cluster_key": "qcl:v1:8ffb40f540622fa193732405d5a2f7ad05ae2523",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелки",
    "use_cases": [
      "для супа"
    ],
    "attributes": []
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:216ce4d1ab5562122979c6631069de620f13a8ee` — тарелка для микроволновки (query_count=56)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=821&nm_id=33566075&cluster_key=qcl%3Av1%3A216ce4d1ab5562122979c6631069de620f13a8ee`
```json
{
  "project_id": 1,
  "category_id": 821,
  "cluster_key": "qcl:v1:216ce4d1ab5562122979c6631069de620f13a8ee",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тарелки",
    "use_cases": [
      "для микроволновки"
    ],
    "attributes": []
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

### Quick conclusions
* Expressive layer: category vibes=0, product vibes=0, query vibes=0 (empty is expected when language markers are absent).
* Cold-start product projection: verify that `product_type` and top attributes are consistent with product titles; watch for boolean/technical tokens leaking into attributes.
* Query meaning: verify `product_type` + attributes align with cluster label candidate and members.

---

## Category `812` — Кружки

### Category data snapshot
* `subject_name`: `Кружки`
* `skus_count` (from subjects endpoint): `213`
* Query pipeline diagnostics: `total_queries=2671`, `total_clusters=1543`

### cluster_key picked (top 3 from query-pipeline debug)
Command used:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/query-pipeline/debug?category_id=812&tab=clusters&page=1&page_size=3" | Select-Object -ExpandProperty clusters | Select-Object -First 3
```
Selected clusters (meta):
```json
[
  {
    "cluster_key": "qcl:v1:8b2ce58bf1d458b429c02b8636014794281f2e87",
    "label": "кружка для чая",
    "query_count": 32
  },
  {
    "cluster_key": "qcl:v1:02f281ac4907c046e5bdde12918116ea851756c7",
    "label": "кружка с именем",
    "query_count": 16
  },
  {
    "cluster_key": "qcl:v1:5308a67d813715e6ee3b7347122bba8639dcc75c",
    "label": "кружка 500 мл",
    "query_count": 15
  }
]
```

### category_meaning
Command used (example):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187591&cluster_key=qcl%3Av1%3A8b2ce58bf1d458b429c02b8636014794281f2e87"
```
Result:
```json
{
  "project_id": 1,
  "category_id": 812,
  "version": "v1_mvp",
  "functional": {
    "product_types": [
      "кружка"
    ],
    "use_cases": [
      "для кофе",
      "для вас",
      "для самых",
      "для друзей",
      "для чая",
      "для этого",
      "для посудомоечной"
    ],
    "attributes": [
      "true",
      "день",
      "керамика",
      "китай",
      "кружка",
      "подруге",
      "любимой",
      "рождения",
      "хрупкое",
      "год",
      "новый",
      "подарки",
      "принт",
      "керамическая",
      "ра01",
      "росс",
      "марта",
      "повседневная",
      "домашние",
      "дома",
      "коробка",
      "использование",
      "свч",
      "универсальный",
      "машине",
      "посудомоечной",
      "картонная",
      "ребенка",
      "офис",
      "полезные",
      "чая",
      "кофе",
      "светло",
      "розовый",
      "сестре",
      "белый",
      "пакет",
      "воздушно",
      "голубой",
      "котик"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```

### product_projection (3 SKUs)
#### nm_id `17187591` — Кружка керамическая 370 мл
- source subject_name: `Кружки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187591&cluster_key=qcl%3Av1%3A8b2ce58bf1d458b429c02b8636014794281f2e87`
```json
{
  "project_id": 1,
  "category_id": 812,
  "nm_id": 17187591,
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [
      "для этого",
      "для вас",
      "для самых"
    ],
    "attributes": [
      "кружка",
      "дома",
      "кофе",
      "чая",
      "полезные",
      "подарки",
      "керамика",
      "новый",
      "год",
      "день",
      "рождения",
      "китай",
      "хрупкое",
      "белый",
      "подруге",
      "любимой",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `17187592` — Кружка керамическая 370 мл
- source subject_name: `Кружки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187592&cluster_key=qcl%3Av1%3A02f281ac4907c046e5bdde12918116ea851756c7`
```json
{
  "project_id": 1,
  "category_id": 812,
  "nm_id": 17187592,
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [
      "для этого",
      "для вас",
      "для самых"
    ],
    "attributes": [
      "китай",
      "чая",
      "полезные",
      "подарки",
      "кружка",
      "керамика",
      "хрупкое",
      "дома",
      "кофе",
      "подруге",
      "любимой",
      "новый",
      "год",
      "день",
      "рождения",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `17187593` — Кружка керамическая 370 мл
- source subject_name: `Кружки`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187593&cluster_key=qcl%3Av1%3A5308a67d813715e6ee3b7347122bba8639dcc75c`
```json
{
  "project_id": 1,
  "category_id": 812,
  "nm_id": 17187593,
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [
      "для этого",
      "для вас",
      "для самых"
    ],
    "attributes": [
      "кружка",
      "китай",
      "дома",
      "кофе",
      "новый",
      "год",
      "день",
      "рождения",
      "подруге",
      "любимой",
      "чая",
      "хрупкое",
      "керамика",
      "полезные",
      "подарки",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

### query_meaning (3 cluster_key)
#### cluster `qcl:v1:8b2ce58bf1d458b429c02b8636014794281f2e87` — кружка для чая (query_count=32)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187591&cluster_key=qcl%3Av1%3A8b2ce58bf1d458b429c02b8636014794281f2e87`
```json
{
  "project_id": 1,
  "category_id": 812,
  "cluster_key": "qcl:v1:8b2ce58bf1d458b429c02b8636014794281f2e87",
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [
      "для чая"
    ],
    "attributes": []
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:02f281ac4907c046e5bdde12918116ea851756c7` — кружка с именем (query_count=16)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187592&cluster_key=qcl%3Av1%3A02f281ac4907c046e5bdde12918116ea851756c7`
```json
{
  "project_id": 1,
  "category_id": 812,
  "cluster_key": "qcl:v1:02f281ac4907c046e5bdde12918116ea851756c7",
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [],
    "attributes": []
  },
  "expressive": {
    "vibes": [
      "кружка именем"
    ]
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:5308a67d813715e6ee3b7347122bba8639dcc75c` — кружка 500 мл (query_count=15)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=812&nm_id=17187593&cluster_key=qcl%3Av1%3A5308a67d813715e6ee3b7347122bba8639dcc75c`
```json
{
  "project_id": 1,
  "category_id": 812,
  "cluster_key": "qcl:v1:5308a67d813715e6ee3b7347122bba8639dcc75c",
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [],
    "attributes": [
      "500 мл"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

### Quick conclusions
* Expressive layer: category vibes=0, product vibes=0, query vibes=1 (empty is expected when language markers are absent).
* Cold-start product projection: verify that `product_type` and top attributes are consistent with product titles; watch for boolean/technical tokens leaking into attributes.
* Query meaning: verify `product_type` + attributes align with cluster label candidate and members.

---

## Category `745` — Тетради

### Category data snapshot
* `subject_name`: `Тетради`
* `skus_count` (from subjects endpoint): `266`
* Query pipeline diagnostics: `total_queries=1038`, `total_clusters=489`

### cluster_key picked (top 3 from query-pipeline debug)
Command used:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/query-pipeline/debug?category_id=745&tab=clusters&page=1&page_size=3" | Select-Object -ExpandProperty clusters | Select-Object -First 3
```
Selected clusters (meta):
```json
[
  {
    "cluster_key": "qcl:v1:3e18514bc22fa4e3232eacac953b0585fdd89215",
    "label": "тетради в клетку",
    "query_count": 12
  },
  {
    "cluster_key": "qcl:v1:ec9ba928ca042df03bb6016c243320b54af72673",
    "label": "тетрадь 48 листов в клетку",
    "query_count": 12
  },
  {
    "cluster_key": "qcl:v1:fc7c16795d2e8e2df9c5649a7672f42c31993ff5",
    "label": "тетрадь на кольцах",
    "query_count": 12
  }
]
```

### category_meaning
Command used (example):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847637&cluster_key=qcl%3Av1%3A3e18514bc22fa4e3232eacac953b0585fdd89215"
```
Result:
```json
{
  "project_id": 1,
  "category_id": 745,
  "version": "v1_mvp",
  "functional": {
    "product_types": [
      "набор",
      "тетрадей",
      "тетрадь",
      "формат",
      "листов",
      "обложке"
    ],
    "use_cases": [
      "для личных",
      "для девочек",
      "для школы",
      "для учебы",
      "для тех",
      "для письма"
    ],
    "attributes": [
      "китай",
      "школа",
      "офис",
      "клетка",
      "еаэс",
      "ра04",
      "true",
      "тетрадь",
      "принт",
      "набор",
      "false",
      "закругленные",
      "углы",
      "тетрадей",
      "полей",
      "повседневная",
      "розовый",
      "голубой",
      "клетку",
      "светло"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```

### product_projection (3 SKUs)
#### nm_id `21847637` — Тетрадь в клетку, размер 25,8х18,7 см, 36 листов
- source subject_name: `Тетради`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847637&cluster_key=qcl%3Av1%3A3e18514bc22fa4e3232eacac953b0585fdd89215`
```json
{
  "project_id": 1,
  "category_id": 745,
  "nm_id": 21847637,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": [
      "тетрадь",
      "клетка",
      "китай",
      "светло",
      "розовый",
      "false"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `21847638` — Тетрадь в клетку, размер 25,8х18,7 см, 36 листов
- source subject_name: `Тетради`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847638&cluster_key=qcl%3Av1%3Aec9ba928ca042df03bb6016c243320b54af72673`
```json
{
  "project_id": 1,
  "category_id": 745,
  "nm_id": 21847638,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": [
      "тетрадь",
      "клетка",
      "китай",
      "розовый",
      "false"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

#### nm_id `21847639` — Тетрадь в клетку, размер 25,8х18,7 см, 36 листов
- source subject_name: `Тетради`
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847639&cluster_key=qcl%3Av1%3Afc7c16795d2e8e2df9c5649a7672f42c31993ff5`
```json
{
  "project_id": 1,
  "category_id": 745,
  "nm_id": 21847639,
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": [
      "тетрадь",
      "клетка",
      "китай",
      "голубой",
      "false"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```
Flags:
```json
{
  "weak_expressive_signal": true,
  "strong_expressive_signal": false,
  "used_category_prior": false,
  "applied_sku_vibes": false
}
```

### query_meaning (3 cluster_key)
#### cluster `qcl:v1:3e18514bc22fa4e3232eacac953b0585fdd89215` — тетради в клетку (query_count=12)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847637&cluster_key=qcl%3Av1%3A3e18514bc22fa4e3232eacac953b0585fdd89215`
```json
{
  "project_id": 1,
  "category_id": 745,
  "cluster_key": "qcl:v1:3e18514bc22fa4e3232eacac953b0585fdd89215",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": []
  },
  "expressive": {
    "vibes": [
      "тетрадь клетку"
    ]
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:ec9ba928ca042df03bb6016c243320b54af72673` — тетрадь 48 листов в клетку (query_count=12)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847638&cluster_key=qcl%3Av1%3Aec9ba928ca042df03bb6016c243320b54af72673`
```json
{
  "project_id": 1,
  "category_id": 745,
  "cluster_key": "qcl:v1:ec9ba928ca042df03bb6016c243320b54af72673",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": []
  },
  "expressive": {
    "vibes": [
      "тетрадь листов клетку"
    ]
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

#### cluster `qcl:v1:fc7c16795d2e8e2df9c5649a7672f42c31993ff5` — тетрадь на кольцах (query_count=12)
- command: `http://localhost:8000/api/v1/projects/1/seo/meaning-extraction/debug?category_id=745&nm_id=21847639&cluster_key=qcl%3Av1%3Afc7c16795d2e8e2df9c5649a7672f42c31993ff5`
```json
{
  "project_id": 1,
  "category_id": 745,
  "cluster_key": "qcl:v1:fc7c16795d2e8e2df9c5649a7672f42c31993ff5",
  "version": "v1_mvp",
  "functional": {
    "product_type": "тетрадь",
    "use_cases": [],
    "attributes": []
  },
  "expressive": {
    "vibes": [
      "тетрадь кольцах"
    ]
  }
}
```
Flags:
```json
{
  "expressive_vibes_are_mvp_proxy": true,
  "expressive_vibes_source": "language_markers"
}
```

### Quick conclusions
* Expressive layer: category vibes=0, product vibes=0, query vibes=3 (empty is expected when language markers are absent).
* Cold-start product projection: verify that `product_type` and top attributes are consistent with product titles; watch for boolean/technical tokens leaking into attributes.
* Query meaning: verify `product_type` + attributes align with cluster label candidate and members.

---

## Overall summary

### What looks good
- QueryMeaning functional fields generally match cluster label candidates (product_type + one key attribute).
- ProductProjection functional `product_type` is present for all sampled SKUs.

### What looks suspicious
- CategoryMeaning/ProductProjection attributes sometimes include technical/boolean tokens (e.g. `true`/`false`) and truncated fragments; likely originates from raw characteristics serialization.
- Expressive vibes are mostly empty on real data for sampled clusters/SKUs; may be fine as MVP proxy, but needs validation on categories where language markers exist.

### What to check next
- Pick a category with stronger adjective-rich queries and re-run to see non-empty `language_markers -> vibes` proxy behavior.
- Inspect which product fields contribute tokens to CategoryMeaning attributes (to explain `true/false` leaks) before changing rules.
- For 1 category, sample 10 clusters across head/mid/tail to see if QueryMeaning stability degrades in tail.
