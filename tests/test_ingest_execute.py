from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.tasks.ingest_execute import _maybe_schedule_wb_card_stats_daily_continuation


def test_wb_card_stats_daily_auto_continue_multiday_preserves_fast_path_params():
    """A paused multi-day backfill must continue from range state with the same strategy params."""
    run = {
        "schedule_id": 7,
        "params_json": {
            "mode": "backfill",
            "date_from": "2026-04-25",
            "date_to": "2026-06-24",
            "use_fast_path": True,
            "max_seconds": 1200,
            "max_batches": 50,
        },
    }

    with patch(
        "app.tasks.ingest_execute.get_backfill_state",
        return_value={"status": "paused"},
    ) as get_state:
        with patch(
            "app.tasks.ingest_execute.try_increment_auto_continue_count",
            return_value=1,
        ) as inc_count:
            with patch(
                "app.tasks.ingest_execute.create_run_queued",
                return_value={"id": 456},
            ) as create_run:
                with patch(
                    "app.tasks.ingest_execute.execute_ingest.delay",
                    return_value=SimpleNamespace(id="celery-456"),
                ) as delay:
                    with patch(
                        "app.tasks.ingest_execute.set_run_celery_task_id",
                    ) as set_task_id:
                        _maybe_schedule_wb_card_stats_daily_continuation(
                            run_id=123,
                            run=run,
                            project_id=1,
                            marketplace_code="wildberries",
                            stats={"reason": "progress_saved"},
                        )

    get_state.assert_called_once()
    inc_count.assert_called_once()
    create_run.assert_called_once()
    created_kwargs = create_run.call_args.kwargs
    assert created_kwargs["project_id"] == 1
    assert created_kwargs["marketplace_code"] == "wildberries"
    assert created_kwargs["job_code"] == "wb_card_stats_daily"
    assert created_kwargs["schedule_id"] == 7
    assert created_kwargs["triggered_by"] == "auto_continue"
    assert created_kwargs["params_json"] == {
        "mode": "backfill",
        "date_from": "2026-04-25",
        "date_to": "2026-06-24",
        "use_fast_path": True,
        "max_seconds": 1200,
        "max_batches": 50,
    }
    delay.assert_called_once_with(456)
    set_task_id.assert_called_once_with(456, "celery-456")
