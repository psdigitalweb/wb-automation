from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app.schemas.wb_competitor_reviews import (
    AddCompetitorTargetsRequest,
    CollectCompetitorReviewsRequest,
)
from app.wb.competitor_reviews_client import (
    CompetitorReviewCollection,
    WBCompetitorReviewsError,
    _basket_number,
    parse_feedbacks,
)


def test_parse_feedbacks_includes_text_from_all_root_card_variants() -> None:
    payload = {
        "feedbacks": [
            {
                "id": "a",
                "nmId": 10,
                "productValuation": 5,
                "createdDate": "2026-07-20T10:00:00Z",
                "text": "  Хорошая   кружка ",
                "pros": "",
                "cons": "",
            },
            {
                "id": "b",
                "nmId": 10,
                "productValuation": 4,
                "text": "",
                "pros": "",
                "cons": "",
            },
            {
                "id": "c",
                "nmId": 11,
                "productValuation": 1,
                "text": "Другой вариант",
            },
        ]
    }

    reviews, collected_count = parse_feedbacks(payload, 10)

    assert collected_count == 3
    assert [review.external_id for review in reviews] == ["a", "c"]
    assert reviews[0].text == "Хорошая кружка"
    assert reviews[0].created_at == datetime.fromisoformat("2026-07-20T10:00:00+00:00")


def test_parse_feedbacks_rejects_missing_feedback_list() -> None:
    try:
        parse_feedbacks({}, 10)
    except WBCompetitorReviewsError as exc:
        assert exc.code == "invalid_feedbacks_payload"
    else:
        raise AssertionError("invalid payload must fail")


def test_public_basket_shard_mapping_for_known_product() -> None:
    assert _basket_number(291945877) == 18


def test_client_collection_contract_with_mocked_storefront(monkeypatch) -> None:
    from app.wb import competitor_reviews_client as provider

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "card.wb.ru":
            return httpx.Response(
                200,
                json={
                    "products": [
                        {
                            "id": 291945877,
                            "root": 117785381,
                            "name": "Кружка",
                            "brand": "ZAKKA",
                            "subjectId": 812,
                            "reviewRating": 4.9,
                            "feedbacks": 222,
                        }
                    ]
                },
            )
        if host == "basket-18.wbbasket.ru":
            return httpx.Response(
                200,
                json={"subj_name": "Кружки", "imt_name": "Кружка Bunny"},
            )
        if host == "feedbacks1.wb.ru":
            return httpx.Response(
                200,
                json={
                    "feedbacks": [
                        {
                            "id": "one",
                            "nmId": 291945877,
                            "productValuation": 5,
                            "createdDate": "2026-07-20T10:00:00Z",
                            "text": "Удобная кружка",
                        },
                        {
                            "id": "variant",
                            "nmId": 291945878,
                            "productValuation": 1,
                            "text": "Другой вариант",
                        },
                    ]
                },
            )
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        provider,
        "make_async_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=transport,
            headers=kwargs.get("headers"),
            follow_redirects=True,
        ),
    )

    result = asyncio.run(
        provider.WBCompetitorReviewsClient(max_retries=1).collect(291945877)
    )

    assert result.category_name == "Кружки"
    assert result.title == "Кружка Bunny"
    assert result.collected_reviews_count == 2
    assert result.calculated_avg_rating == 3.0
    assert [review.external_id for review in result.reviews] == ["one", "variant"]


def test_client_finds_card_json_after_wb_basket_move(monkeypatch) -> None:
    from app.wb import competitor_reviews_client as provider

    requested_baskets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "card.wb.ru":
            return httpx.Response(
                200,
                json={
                    "products": [
                        {
                            "id": 756221104,
                            "root": 891350963,
                            "name": "Кружка",
                            "feedbacks": 1,
                        }
                    ]
                },
            )
        if host.startswith("basket-"):
            requested_baskets.append(host)
            if host == "basket-35.wbbasket.ru":
                return httpx.Response(200, json={"subj_name": "Кружки"})
            return httpx.Response(404, json={})
        if host == "feedbacks1.wb.ru":
            return httpx.Response(
                200,
                json={"feedbacks": [{"id": "rating-only", "nmId": 756221104}]},
            )
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        provider,
        "make_async_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=transport,
            headers=kwargs.get("headers"),
            follow_redirects=True,
        ),
    )

    result = asyncio.run(
        provider.WBCompetitorReviewsClient(max_retries=1).collect(756221104)
    )

    assert result.category_name == "Кружки"
    assert requested_baskets[0] == "basket-39.wbbasket.ru"
    assert requested_baskets[-1] == "basket-35.wbbasket.ru"


def test_request_schemas_dedupe_nmids() -> None:
    add_request = AddCompetitorTargetsRequest(nm_ids=[10, 10, 11])
    collect_request = CollectCompetitorReviewsRequest(nm_ids=[11, 11])

    assert add_request.nm_ids == [10, 11]
    assert collect_request.nm_ids == [11]


def test_get_targets_is_read_only(monkeypatch) -> None:
    from app.routers import wb_competitor_reviews as api

    delay_calls: list[int] = []
    monkeypatch.setattr(api, "list_targets", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        api.collect_competitor_reviews_task,
        "delay",
        lambda run_id: delay_calls.append(run_id),
    )

    response = asyncio.run(
        api.get_competitor_targets(
            project_id=1,
            _membership={"role": "viewer"},
        )
    )

    assert response.items == []
    assert delay_calls == []


def test_delete_targets_removes_only_requested_project_targets(monkeypatch) -> None:
    from app.routers import wb_competitor_reviews as api

    deleted_calls: list[tuple[int, list[int]]] = []
    monkeypatch.setattr(
        api,
        "list_targets",
        lambda *_args, **_kwargs: [
            {"nm_id": 10, "analysis_status": "ready"},
            {"nm_id": 11, "analysis_status": None},
        ],
    )
    monkeypatch.setattr(api, "get_active_run", lambda _project_id: None)
    monkeypatch.setattr(
        api,
        "delete_targets",
        lambda project_id, nm_ids: deleted_calls.append((project_id, nm_ids)) or nm_ids,
    )

    response = asyncio.run(
        api.delete_competitor_targets(
            project_id=7,
            nm_ids=[10, 11, 10],
            _membership={"role": "member"},
        )
    )

    assert response.deleted_nm_ids == [10, 11]
    assert response.deleted_count == 2
    assert deleted_calls == [(7, [10, 11])]


def test_delete_targets_rejects_active_analysis(monkeypatch) -> None:
    from app.routers import wb_competitor_reviews as api

    monkeypatch.setattr(
        api,
        "list_targets",
        lambda *_args, **_kwargs: [{"nm_id": 10, "analysis_status": "running"}],
    )
    monkeypatch.setattr(api, "get_active_run", lambda _project_id: None)

    with pytest.raises(api.HTTPException) as exc_info:
        asyncio.run(
            api.delete_competitor_targets(
                project_id=1,
                nm_ids=[10],
                _membership={"role": "member"},
            )
        )

    assert exc_info.value.status_code == 409


def test_collect_endpoint_enqueues_only_after_explicit_command(monkeypatch) -> None:
    from datetime import timezone

    from app.routers import wb_competitor_reviews as api

    now = datetime.now(timezone.utc)
    run = {
        "id": 9,
        "status": "queued",
        "requested_nm_ids": [10],
        "completed_nm_ids": [],
        "failed_nm_ids": [],
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "error_message": None,
    }
    delay_calls: list[int] = []
    monkeypatch.setattr(
        api,
        "list_targets",
        lambda *_args, **_kwargs: [{"nm_id": 10}],
    )
    monkeypatch.setattr(api, "get_active_run", lambda _project_id: None)
    monkeypatch.setattr(api, "create_run", lambda *_args, **_kwargs: run)
    monkeypatch.setattr(
        api.collect_competitor_reviews_task,
        "delay",
        lambda run_id: delay_calls.append(run_id),
    )

    response = asyncio.run(
        api.collect_competitor_targets(
            CollectCompetitorReviewsRequest(nm_ids=[10]),
            project_id=1,
            membership={"role": "member", "user_id": 7},
        )
    )

    assert response.run.id == 9
    assert delay_calls == [9]


def test_collect_service_keeps_per_target_failures_isolated(monkeypatch) -> None:
    from app.services import wb_competitor_reviews as service

    collection = CompetitorReviewCollection(
        nm_id=10,
        root_id=1,
        title="Товар",
        brand="Бренд",
        subject_id=2,
        category_name="Категория",
        wb_review_rating=4.8,
        wb_feedback_count=10,
        collected_reviews_count=2,
        calculated_avg_rating=5.0,
        reviews=[],
    )

    class FakeClient:
        async def collect(self, nm_id: int):
            if nm_id == 11:
                raise WBCompetitorReviewsError("product_not_found", "missing")
            return collection

    events: list[tuple] = []
    monkeypatch.setattr(
        service,
        "get_run_by_id",
        lambda _run_id: {
            "id": 5,
            "project_id": 1,
            "status": "queued",
            "requested_nm_ids": [10, 11],
        },
    )
    monkeypatch.setattr(service, "mark_run_running", lambda run_id: events.append(("run", run_id)))
    monkeypatch.setattr(
        service,
        "mark_target_collecting",
        lambda project_id, nm_id: events.append(("collecting", nm_id)),
    )
    monkeypatch.setattr(
        service,
        "save_collection",
        lambda project_id, nm_id, value: events.append(("saved", nm_id)),
    )
    monkeypatch.setattr(
        service,
        "mark_target_failed",
        lambda project_id, nm_id, **kwargs: events.append(("failed", nm_id, kwargs["code"])),
    )
    finished: list[dict] = []
    monkeypatch.setattr(
        service,
        "finish_run",
        lambda run_id, **kwargs: finished.append({"run_id": run_id, **kwargs}),
    )

    result = asyncio.run(
        service.collect_competitor_review_run(5, client=FakeClient())
    )

    assert result["completed_nm_ids"] == [10]
    assert result["failed_nm_ids"] == [11]
    assert ("failed", 11, "product_not_found") in events
    assert finished[0].get("failed", False) is False


def test_competitor_analysis_pipeline_uses_chunk_themes_and_exact_quotes(monkeypatch) -> None:
    from app.services.competitor_analysis import service
    from app.services.competitor_analysis.client import StructuredResponse

    reviews = [
        {"review_id": "r_0001", "rating": 5, "text": "Очень удобный контейнер", "pros": None, "cons": None},
        {"review_id": "r_0002", "rating": 4, "text": "Контейнер удобный для школы", "pros": None, "cons": None},
    ]
    analysis_input = SimpleNamespace(
        input_hash="same",
        nm_id=10,
        title="Контейнер",
        category_name="Ланч-боксы",
        reviews=reviews,
        chunks=[reviews],
        review_fields={
            "r_0001": ("Очень удобный контейнер",),
            "r_0002": ("Контейнер удобный для школы",),
        },
    )
    chunk_content = {
        "themes": [
            {
                "label": "Удобство",
                "sentiment": "positive",
                "category": "product",
                "summary": "Покупателям удобно пользоваться контейнером.",
                "review_ids": ["r_0001", "r_0002"],
            }
        ]
    }
    final_content = {
        "schema_version": "wb_competitor_analysis_v1",
        "overall_conclusion": "Контейнер считают удобным.",
        "strengths": [
            {
                "label": "Удобство",
                "category": "product",
                "summary": "Подходит для повседневного использования.",
                "confidence": "high",
                "source_theme_ids": ["t_01_01"],
                "evidence": [{"review_id": "r_0001", "quote": "Очень удобный"}],
            }
        ],
        "weaknesses": [],
        "opportunities": [],
        "conflicts": [],
    }

    class FakeClient:
        def __init__(self, content, cost):
            self.content = content
            self.cost = cost

        def generate(self, **_kwargs):
            return StructuredResponse(
                model="test",
                content=self.content,
                usage={"cost": self.cost, "prompt_tokens": 10, "completion_tokens": 10},
                provider_request_id=None,
            )

    ready: list[dict] = []
    monkeypatch.setattr(
        service,
        "get_competitor_analysis_run",
        lambda _run_id: {
            "id": 7,
            "project_id": 1,
            "nm_id": 10,
            "status": "queued",
            "input_hash": "same",
            "max_cost_usd": 0.2,
        },
    )
    monkeypatch.setattr(service, "build_competitor_analysis_input", lambda *_: analysis_input)
    monkeypatch.setattr(service, "mark_competitor_analysis_running", lambda *_: None)
    monkeypatch.setattr(
        service,
        "finish_competitor_analysis_ready",
        lambda run_id, **kwargs: ready.append({"run_id": run_id, **kwargs}),
    )

    result = service.execute_competitor_analysis(
        7,
        nano_client=FakeClient(chunk_content, 0.001),
        terra_client=FakeClient(final_content, 0.04),
    )

    assert result["status"] == "ready"
    assert ready[0]["actual_cost_usd"] == pytest.approx(0.041)
    assert ready[0]["result"]["strengths"][0]["support_count"] == 2
    assert ready[0]["result"]["strengths"][0]["evidence"][0]["quote"] == "Очень удобный"


def test_competitor_analysis_repairs_evidence_from_unselected_theme() -> None:
    from app.services.competitor_analysis.contracts import CompetitorAnalysisModelOutput
    from app.services.competitor_analysis.service import _normalize_final

    output = CompetitorAnalysisModelOutput.model_validate(
        {
            "schema_version": "wb_competitor_analysis_v1",
            "overall_conclusion": "Товар считают удобным.",
            "strengths": [
                {
                    "label": "Удобство",
                    "category": "product",
                    "summary": "Удобен в использовании.",
                    "confidence": "high",
                    "source_theme_ids": ["t_01_01"],
                    "evidence": [
                        {"review_id": "r_0086", "quote": "Отзыв из другой темы"}
                    ],
                }
            ],
            "weaknesses": [],
            "opportunities": [],
            "conflicts": [],
        }
    )
    themes = {
        "t_01_01": {"review_ids": ["r_0001"]},
        "t_02_01": {"review_ids": ["r_0086"]},
    }

    result, validation = _normalize_final(
        output,
        themes=themes,
        review_fields={
            "r_0001": ("Действительно удобный товар для ежедневного использования.",),
            "r_0086": ("Отзыв из другой темы",),
        },
        reviews_count=2,
    )

    assert result["strengths"][0]["evidence"] == [
        {
            "review_id": "r_0001",
            "quote": "Действительно удобный товар для ежедневного использования.",
        }
    ]
    assert validation["evidence_items_dropped"] == 1
    assert validation["fallback_evidence_added"] == 1


def test_competitor_analysis_stops_before_terra_when_budget_is_too_low(monkeypatch) -> None:
    from app.services.competitor_analysis import service
    from app.services.competitor_analysis.client import StructuredResponse

    reviews = [
        {"review_id": "r_0001", "rating": 5, "text": "Хороший товар", "pros": None, "cons": None},
        {"review_id": "r_0002", "rating": 5, "text": "Удобный товар", "pros": None, "cons": None},
    ]
    analysis_input = SimpleNamespace(
        input_hash="same",
        nm_id=10,
        title="Товар",
        category_name=None,
        reviews=reviews,
        chunks=[reviews],
        review_fields={"r_0001": ("Хороший товар",), "r_0002": ("Удобный товар",)},
    )

    class NanoClient:
        def generate(self, **_kwargs):
            return StructuredResponse(
                model="nano",
                content={
                    "themes": [
                        {
                            "label": "Удобство",
                            "sentiment": "positive",
                            "category": "product",
                            "summary": "Товар считают удобным.",
                            "review_ids": ["r_0001", "r_0002"],
                        }
                    ]
                },
                usage={"cost": 0.001},
                provider_request_id=None,
            )

    failed: list[dict] = []
    monkeypatch.setattr(
        service,
        "get_competitor_analysis_run",
        lambda _run_id: {
            "project_id": 1,
            "nm_id": 10,
            "status": "queued",
            "input_hash": "same",
            "max_cost_usd": 0.05,
        },
    )
    monkeypatch.setattr(service, "build_competitor_analysis_input", lambda *_: analysis_input)
    monkeypatch.setattr(service, "mark_competitor_analysis_running", lambda *_: None)
    monkeypatch.setattr(
        service,
        "finish_competitor_analysis_failed",
        lambda run_id, **kwargs: failed.append({"run_id": run_id, **kwargs}),
    )

    result = service.execute_competitor_analysis(
        8,
        nano_client=NanoClient(),
        terra_client=SimpleNamespace(generate=lambda **_kwargs: pytest.fail("terra must not run")),
    )

    assert result["error_code"] == "budget_exceeded"
    assert failed[0]["actual_cost_usd"] == pytest.approx(0.001)
