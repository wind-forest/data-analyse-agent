from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from app.errors import AppError
from app.tools.modeling import _classification_matrix, _recursive_forecast
from app.tools.registry import execute_tool, list_tool_schemas


def _generate_actions(days: int = 120, per_day: int = 12) -> bytes:
    songs = [
        "03c6699ea836decbc5c8fc2dbae7bd3b",
        "effb071415be51f11e845884e67c0f8c",
        "f87ff481d85d2f95335ab602f38a7655",
    ]
    lines: list[str] = []
    start = date(2025, 1, 1)
    for offset in range(days):
        current = start + timedelta(days=offset)
        count = per_day + (10 if current.weekday() >= 5 else 0)
        stamp = int(datetime.combine(current, time(12, 0)).timestamp())
        for index in range(count):
            user_id = f"{index % 40:032x}"
            lines.append(
                f"{user_id},{songs[index % len(songs)]},"
                f"{stamp},1,{current.strftime('%Y%m%d')}"
            )
    return ("\n".join(lines) + "\n").encode()


def _generate_songs() -> bytes:
    return (
        b"03c6699ea836decbc5c8fc2dbae7bd3b,c81f89cf7edd24930641afa2e411b09c,20110910,100,1,1\n"
        b"effb071415be51f11e845884e67c0f8c,c81f89cf7edd24930641afa2e411b09c,20120910,200,1,2\n"
        b"f87ff481d85d2f95335ab602f38a7655,78fedfdf13fc820e363e39986ff91e94,20130910,150,2,1\n"
    )


async def _seed_files(client) -> dict[str, str]:
    session = (await client.post("/api/sessions", json={"title": "工具验证"})).json()
    session_id = session["id"]
    actions = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("actions.csv", _generate_actions(), "text/csv")},
    )
    songs = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("songs.csv", _generate_songs(), "text/csv")},
    )
    assert actions.status_code == 201
    assert songs.status_code == 201
    return {
        "session_id": session_id,
        "actions_id": actions.json()["id"],
        "songs_id": songs.json()["id"],
    }


def test_tool_schemas_expose_registered_tools() -> None:
    names = {item["function"]["name"] for item in list_tool_schemas()}
    assert names == {
        "profile_dataset",
        "aggregate_plays",
        "build_time_features",
        "train_predictive_model",
        "evaluate_model",
        "generate_chart_data",
        "query_session_memory",
        "execute_python_snippet",
    }


def test_sandbox_tool_only_exposed_when_allowed(monkeypatch) -> None:
    from app.tools.registry import agent_tool_schemas

    monkeypatch.setattr("app.sandbox.manager.is_available", lambda: True)
    hidden = {item["function"]["name"] for item in agent_tool_schemas(False)}
    shown = {item["function"]["name"] for item in agent_tool_schemas(True)}

    assert "execute_python_snippet" not in hidden
    assert "execute_python_snippet" in shown
    assert "finish" in shown


async def test_tool_validation_error(client, db_session) -> None:
    from app.tools.base import ToolContext

    ctx = ToolContext(db=db_session, session_id=uuid.uuid4())
    with pytest.raises(AppError) as exc:
        await execute_tool("aggregate_plays", {"group_by": []}, ctx)
    assert exc.value.code in {"TOOL_VALIDATION_ERROR", "INVALID_FILE"}


def test_classification_matrix_encodes_categories() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "target": ["a", "b", "a", "b", "a", "b"],
            "amount": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "region": ["east", "west", "east", "west", "east", "west"],
            "sparse_id": [f"id-{i}" for i in range(6)],
        }
    )
    matrix, labels = _classification_matrix(frame, "target")
    assert "amount" in matrix.columns
    assert "region_east" in matrix.columns
    assert "sparse_id" not in matrix.columns
    assert set(labels.unique()) == {"a", "b"}


def test_recursive_forecast_produces_contiguous_days() -> None:
    import pandas as pd

    class ConstantModel:
        def predict(self, frame):
            return [100.0] * len(frame)

    dates = pd.date_range("2025-01-01", periods=60, freq="D")
    frame = pd.DataFrame({"date": dates, "plays": [100.0] * 60})
    features = [f"lag_{lag}" for lag in (1, 7, 14, 28)] + [
        f"rolling_mean_{window}" for window in (1, 7, 14, 28)
    ] + ["day_of_week", "month"]

    forecast = _recursive_forecast(ConstantModel(), frame, features, 7)
    assert len(forecast) == 7
    assert forecast[0]["date"] == "2025-03-02"
    assert forecast[-1]["date"] == "2025-03-08"
    assert all(item["plays"] == 100.0 for item in forecast)


@pytest.mark.slow
def test_time_features_rolling_mean_excludes_target_day() -> None:
    import sys
    from pathlib import Path

    from pyspark.sql import SparkSession

    spark_jobs = Path(__file__).resolve().parents[1] / "app" / "spark_jobs"
    if str(spark_jobs) not in sys.path:
        sys.path.insert(0, str(spark_jobs))
    from build_time_features import _daily_frame

    spark = (
        SparkSession.builder.master("local[1]")
        .appName("time-features-rolling-window")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "1")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    try:
        rows = (
            [("20250101", 1)] * 10
            + [("20250102", 1)] * 20
            + [("20250103", 1)] * 30
        )
        frame = _daily_frame(spark.createDataFrame(rows, ["Ds", "action_type"]), [1])
        values = {
            str(row["date"]): row["rolling_mean_1"] for row in frame.collect()
        }
        assert values["2025-01-01"] is None
        assert values["2025-01-02"] == 10.0
        assert values["2025-01-03"] == 20.0
    finally:
        spark.stop()


@pytest.mark.slow
async def test_profile_aggregate_and_chart(client, db_session) -> None:
    from app.tools.base import ToolContext

    seeded = await _seed_files(client)
    ctx = ToolContext(
        db=db_session, session_id=uuid.UUID(seeded["session_id"])
    )

    profile = await execute_tool(
        "profile_dataset", {"file_id": seeded["actions_id"]}, ctx
    )
    assert profile.data["dataset_kind"] == "actions"
    assert profile.data["row_count"] > 1000

    aggregated = await execute_tool(
        "aggregate_plays",
        {
            "file_id": seeded["actions_id"],
            "group_by": ["artist_id"],
            "metric": "plays",
            "top_n": 5,
        },
        ctx,
    )
    assert aggregated.artifact_ids
    assert "artist_id" in aggregated.summary

    chart = await execute_tool(
        "generate_chart_data",
        {
            "chart_type": "bar",
            "source_ref": str(aggregated.artifact_ids[0]),
            "x": "artist_id",
            "y": "value",
        },
        ctx,
    )
    assert chart.data["points"] == 2


@pytest.mark.slow
async def test_time_features_training_and_evaluation(client, db_session) -> None:
    from app.tools.base import ToolContext

    seeded = await _seed_files(client)
    ctx = ToolContext(
        db=db_session, session_id=uuid.UUID(seeded["session_id"])
    )

    features = await execute_tool(
        "build_time_features",
        {"file_id": seeded["actions_id"], "granularity": "day"},
        ctx,
    )
    assert features.data["row_count"] >= 100

    trained = await execute_tool(
        "train_predictive_model",
        {"file_id": seeded["actions_id"], "task": "regression", "horizon": 7},
        ctx,
    )
    metrics = trained.data["metrics"]
    assert "mae" in metrics and "rmse" in metrics

    evaluated = await execute_tool(
        "evaluate_model", {"model_id": trained.data["model_id"]}, ctx
    )
    assert evaluated.data["task"] == "regression"
    assert len(evaluated.data["forecast"]) == 7
