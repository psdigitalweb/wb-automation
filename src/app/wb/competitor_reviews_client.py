"""Privacy-minimized client for public WB storefront product/review data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.utils.httpx_client import make_async_client


CARD_URL = "https://card.wb.ru/cards/v4/detail"
MAX_RESPONSE_BYTES = 25 * 1024 * 1024


class WBCompetitorReviewsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompetitorReview:
    external_id: str
    rating: int | None
    created_at: datetime | None
    text: str | None
    pros: str | None
    cons: str | None


@dataclass(frozen=True)
class CompetitorReviewCollection:
    nm_id: int
    root_id: int
    title: str | None
    brand: str | None
    subject_id: int | None
    category_name: str | None
    wb_review_rating: float | None
    wb_feedback_count: int | None
    collected_reviews_count: int
    calculated_avg_rating: float | None
    reviews: list[CompetitorReview]


def _text(value: Any) -> str | None:
    value = " ".join(str(value or "").split()).strip()
    return value[:5000] or None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _basket_number(nm_id: int) -> int:
    """Current public CDN shard mapping; callers tolerate category lookup failure."""

    short_id = int(nm_id) // 100_000
    boundaries = (
        (143, 1),
        (287, 2),
        (431, 3),
        (719, 4),
        (1007, 5),
        (1061, 6),
        (1115, 7),
        (1169, 8),
        (1313, 9),
        (1601, 10),
        (1655, 11),
        (1919, 12),
        (2045, 13),
        (2189, 14),
        (2405, 15),
        (2621, 16),
        (2837, 17),
    )
    for upper, basket in boundaries:
        if short_id <= upper:
            return basket
    return 18 + max(0, (short_id - 2838) // 216)


def _card_json_url(nm_id: int, basket: int | None = None) -> str:
    basket = basket or _basket_number(nm_id)
    return (
        f"https://basket-{basket:02d}.wbbasket.ru/"
        f"vol{nm_id // 100000}/part{nm_id // 1000}/{nm_id}/info/ru/card.json"
    )


def parse_feedbacks(payload: Any, nm_id: int) -> tuple[list[CompetitorReview], int]:
    """Parse the complete WB root-card corpus, including all product variants."""

    source = payload.get("feedbacks") if isinstance(payload, dict) else None
    if not isinstance(source, list):
        raise WBCompetitorReviewsError("invalid_feedbacks_payload", "WB returned no feedback list")
    collected_reviews = 0
    result: list[CompetitorReview] = []
    seen: set[str] = set()
    for item in source:
        if not isinstance(item, dict):
            continue
        collected_reviews += 1
        text_value = _text(item.get("text"))
        pros = _text(item.get("pros"))
        cons = _text(item.get("cons"))
        if not any((text_value, pros, cons)):
            continue
        external_id = _text(item.get("id"))
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        rating = _integer(item.get("productValuation"))
        if rating is not None and rating not in range(1, 6):
            rating = None
        result.append(
            CompetitorReview(
                external_id=external_id,
                rating=rating,
                created_at=_datetime(item.get("createdDate")),
                text=text_value,
                pros=pros,
                cons=cons,
            )
        )
    result.sort(
        key=lambda value: value.created_at.timestamp() if value.created_at else float("-inf"),
        reverse=True,
    )
    return result, collected_reviews


class WBCompetitorReviewsClient:
    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.proxy_url = proxy_url
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://www.wildberries.ru/",
        }

    async def _json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        not_found_ok: bool = False,
    ) -> dict[str, Any] | None:
        last_code = "request_failed"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 404 and not_found_ok:
                    return None
                if response.status_code == 200:
                    if len(response.content) > MAX_RESPONSE_BYTES:
                        raise WBCompetitorReviewsError(
                            "response_too_large",
                            "WB response exceeded the safe size limit",
                        )
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise WBCompetitorReviewsError(
                            "invalid_json_payload",
                            "WB returned a non-object JSON response",
                        )
                    return payload
                last_code = f"http_{response.status_code}"
                if response.status_code not in {429} and response.status_code < 500:
                    break
            except WBCompetitorReviewsError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_code = type(exc).__name__
            if attempt < self.max_retries:
                await asyncio.sleep(min(float(attempt), 3.0))
        raise WBCompetitorReviewsError(last_code, "WB storefront request failed")

    async def _feedback_payload(
        self,
        client: httpx.AsyncClient,
        root_id: int,
        *,
        expect_reviews: bool,
    ) -> dict[str, Any]:
        last_error: WBCompetitorReviewsError | None = None
        for shard in range(1, 6):
            try:
                payload = await self._json(
                    client,
                    f"https://feedbacks{shard}.wb.ru/feedbacks/v2/{root_id}",
                    not_found_ok=True,
                )
                if payload is not None and isinstance(payload.get("feedbacks"), list):
                    if payload["feedbacks"] or not expect_reviews:
                        return payload
            except WBCompetitorReviewsError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise WBCompetitorReviewsError(
            "feedbacks_not_found",
            "WB returned no review corpus for this product",
        )

    async def _card_detail_payload(
        self,
        client: httpx.AsyncClient,
        nm_id: int,
    ) -> dict[str, Any] | None:
        """Find card.json while WB transitions products between CDN baskets."""

        calculated = _basket_number(nm_id)
        candidates = [calculated]
        for delta in range(1, 9):
            candidates.extend((calculated - delta, calculated + delta))
        for basket in dict.fromkeys(value for value in candidates if value > 0):
            detail = await self._json(
                client,
                _card_json_url(nm_id, basket),
                not_found_ok=True,
            )
            if detail is not None:
                return detail
        return None

    async def collect(self, nm_id: int) -> CompetitorReviewCollection:
        nm_id = int(nm_id)
        timeout = httpx.Timeout(self.timeout_seconds)
        async with make_async_client(
            proxy_url=self.proxy_url,
            timeout=timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            card = await self._json(
                client,
                CARD_URL,
                params={
                    "appType": "1",
                    "curr": "rub",
                    "dest": "-1257786",
                    "spp": "30",
                    "ab_testing": "false",
                    "nm": str(nm_id),
                },
            )
            products = card.get("products") if card else None
            product = products[0] if isinstance(products, list) and products else None
            if not isinstance(product, dict) or _integer(product.get("id")) != nm_id:
                raise WBCompetitorReviewsError("product_not_found", "Product was not found on WB")
            root_id = _integer(product.get("root"))
            if not root_id:
                raise WBCompetitorReviewsError("invalid_product_root", "WB product has no group identifier")

            category_name = _text(product.get("entity") or product.get("subjectName"))
            title = _text(product.get("name"))
            try:
                detail = await self._card_detail_payload(client, nm_id)
                if detail:
                    category_name = _text(detail.get("subj_name")) or category_name
                    title = _text(detail.get("imt_name")) or title
            except WBCompetitorReviewsError:
                pass

            wb_feedback_count = _integer(product.get("feedbacks"))
            feedback_payload = await self._feedback_payload(
                client,
                root_id,
                expect_reviews=bool(wb_feedback_count),
            )
            reviews, collected_reviews = parse_feedbacks(feedback_payload, nm_id)
            ratings = [review.rating for review in reviews if review.rating is not None]
            avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
            return CompetitorReviewCollection(
                nm_id=nm_id,
                root_id=root_id,
                title=title,
                brand=_text(product.get("brand")),
                subject_id=_integer(product.get("subjectId")),
                category_name=category_name,
                wb_review_rating=_float(product.get("reviewRating") or product.get("rating")),
                wb_feedback_count=wb_feedback_count,
                collected_reviews_count=collected_reviews,
                calculated_avg_rating=avg_rating,
                reviews=reviews,
            )
