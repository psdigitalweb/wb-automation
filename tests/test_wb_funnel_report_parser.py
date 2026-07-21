from __future__ import annotations

import csv
import zipfile
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services.wb_funnel_quality import (
    CLICKS_EXCEED_IMPRESSIONS,
    CTR_EXCEEDS_100,
    REPORTED_CTR_MISMATCH,
    REPORTED_CTR_MISSING,
    ZERO_IMPRESSIONS_WITH_CLICKS,
    evaluate_daily_quality,
    sample_tier,
)
from app.services.wb_funnel_report_parser import WBFunnelReportError, parse_wb_funnel_report


HEADERS = [
    "Артикул продавца",
    "Артикул WB",
    "Название",
    "Удаленный товар",
    "Дата",
    "Показы",
    "CTR",
    "Переходы в карточку",
]


def _xlsx(path, rows, *, headers=HEADERS, sheet_name="Товары"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(["Детальный отчет"])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


@pytest.mark.parametrize(
    ("impressions", "clicks", "reported", "expected_flags"),
    [
        (100, 14, Decimal("14"), set()),
        (3, 1, Decimal("33"), set()),
        (1, 1, Decimal("100"), set()),
        (1, 26, Decimal("2600"), {CLICKS_EXCEED_IMPRESSIONS, CTR_EXCEEDS_100}),
        (0, 1, Decimal("0"), {ZERO_IMPRESSIONS_WITH_CLICKS, CLICKS_EXCEED_IMPRESSIONS}),
        (0, 0, Decimal("0"), set()),
    ],
)
def test_quality_scenarios(impressions, clicks, reported, expected_flags):
    _, flags = evaluate_daily_quality(
        impressions=impressions,
        card_clicks=clicks,
        reported_ctr=reported,
        is_deleted=False,
    )
    assert expected_flags.issubset(set(flags))


def test_reported_ctr_mismatch_and_missing():
    assert REPORTED_CTR_MISMATCH in evaluate_daily_quality(
        impressions=100, card_clicks=14, reported_ctr=Decimal("20"), is_deleted=False
    )[1]
    assert REPORTED_CTR_MISSING in evaluate_daily_quality(
        impressions=100, card_clicks=14, reported_ctr=None, is_deleted=False
    )[1]


def test_xlsx_parses_reordered_headers_whitespace_empty_ctr_and_deleted(tmp_path):
    headers = ["  Дата ", "Артикул WB", "Переходы   в карточку", "Показы", "Удалённый товар"]
    path = tmp_path / "report.xlsx"
    _xlsx(path, [["21.07.2026", 123, 14, 100, "Да"]], headers=headers)
    report = parse_wb_funnel_report(str(path))
    row = report.rows[0]
    assert row.nm_id == 123
    assert row.reported_ctr is None
    assert row.is_deleted is True
    assert REPORTED_CTR_MISSING in row.quality_flags


def test_csv_and_zip_are_supported(tmp_path):
    csv_path = tmp_path / "report.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(HEADERS)
        writer.writerow(["SKU", 123, "Title", "Нет", "2026-07-21", 100, 14, 14])
    direct = parse_wb_funnel_report(str(csv_path))
    assert direct.rows[0].reported_ctr == Decimal("14")

    zip_path = tmp_path / "report.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(csv_path, "nested/report.csv")
    zipped = parse_wb_funnel_report(str(zip_path))
    assert zipped.content_sha256 == direct.content_sha256


def test_invalid_zip_and_missing_products_sheet(tmp_path):
    invalid = tmp_path / "broken.zip"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(WBFunnelReportError, match="Invalid ZIP"):
        parse_wb_funnel_report(str(invalid))

    xlsx = tmp_path / "wrong.xlsx"
    _xlsx(xlsx, [["SKU", 1, "Title", "Нет", "2026-07-21", 1, 100, 1]], sheet_name="Other")
    with pytest.raises(WBFunnelReportError, match="Товары"):
        parse_wb_funnel_report(str(xlsx))


def test_sample_tier_boundaries():
    assert sample_tier(99) == "insufficient"
    assert sample_tier(100) == "indicative"
    assert sample_tier(399) == "indicative"
    assert sample_tier(400) == "reliable"
    assert sample_tier(999) == "reliable"
    assert sample_tier(1000) == "high_sample"
