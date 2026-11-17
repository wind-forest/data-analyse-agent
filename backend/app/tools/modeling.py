from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from sklearn.base import clone
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit

from app.errors import AppError
from app.services import artifact_service, dataset_service, run_service, storage
from app.services.spark_runner import run_job
from app.tools.base import ToolContext, ToolResult

MODEL_TIMEOUT_SECONDS = 300
FEATURE_WINDOWS = [1, 7, 14, 28]
CLASSIFICATION_SAMPLE_LIMIT = 200_000
HIGH_CARDINALITY_LIMIT = 20


class TrainArgs(BaseModel):
    file_id: uuid.UUID
    task: Literal["regression", "classification"] = "regression"
    target: str | None = None
    feature_set: Literal["auto"] | list[str] = "auto"
    model_family: Literal["auto", "tree", "linear", "boosting"] = "auto"
    horizon: int = Field(default=7, ge=1, le=30)


def _regression_candidates(family: str) -> list[tuple[str, Any]]:
    pool = {
        "linear": ("ridge", Ridge(alpha=1.0)),
        "tree": (
            "random_forest",
            RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1),
        ),
        "boosting": (
            "hist_gradient_boosting",
            HistGradientBoostingRegressor(random_state=42),
        ),
    }
    if family == "auto":
        return list(pool.values())
    return [pool[family]]


def _classification_candidates(family: str) -> list[tuple[str, Any]]:
    pool = {
        "linear": ("logistic_regression", LogisticRegression(max_iter=500)),
        "tree": (
            "random_forest",
            RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1),
        ),
        "boosting": (
            "hist_gradient_boosting",
            HistGradientBoostingClassifier(random_state=42),
        ),
    }
    if family == "auto":
        return list(pool.values())
    return [pool[family]]


def _feature_importance(
    model: Any, feature_names: list[str], X_valid: pd.DataFrame, y_valid: pd.Series
) -> dict[str, float] | None:
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        coefficients = np.asarray(model.coef_, dtype=float)
        values = (
            np.abs(coefficients).mean(axis=0)
            if coefficients.ndim > 1
            else np.abs(coefficients)
        )
    else:
        try:
            result = permutation_importance(
                model, X_valid, y_valid, n_repeats=3, random_state=42
            )
        except Exception:  # noqa: BLE001 - 解释性失败不应让训练整体失败
            return None
        values = np.asarray(result.importances_mean, dtype=float)

    if len(values) != len(feature_names):
        return None
    ranked = sorted(
        zip(feature_names, (float(value) for value in values), strict=False),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return {name: round(value, 6) for name, value in ranked[:15]}


def _recursive_forecast(
    model: Any,
    frame: pd.DataFrame,
    feature_names: list[str],
    horizon: int,
) -> list[dict[str, Any]]:
    history = frame["plays"].astype(float).tolist()
    last_date = pd.to_datetime(frame["date"]).max().date()
    forecast: list[dict[str, Any]] = []

    for step in range(1, horizon + 1):
        target_date = last_date + timedelta(days=step)
        values: dict[str, float] = {}
        for lag in FEATURE_WINDOWS:
            values[f"lag_{lag}"] = float(history[-lag])
        for window in FEATURE_WINDOWS:
            values[f"rolling_mean_{window}"] = float(np.mean(history[-window:]))
        # Spark dayofweek: 周日=1 … 周六=7
        values["day_of_week"] = float((target_date.weekday() + 1) % 7 + 1)
        values["month"] = float(target_date.month)

        row = pd.DataFrame([{name: values.get(name, 0.0) for name in feature_names}])
        prediction = max(float(model.predict(row.astype(float))[0]), 0.0)
        forecast.append(
            {"date": target_date.isoformat(), "plays": round(prediction, 2)}
        )
        history.append(prediction)

    return forecast


async def _train_regression(
    args: TrainArgs, ctx: ToolContext, dataset, run, work
) -> dict[str, Any]:
    features_path = work / "features.parquet"
    await run_job(
        "build_time_features",
        {
            "path": str(dataset.path),
            "spec": dataset.spec.to_dict(),
            "granularity": "day",
            "windows": FEATURE_WINDOWS,
            "output_path": str(features_path),
        },
        work,
        MODEL_TIMEOUT_SECONDS,
    )

    frame = pd.read_parquet(features_path).sort_values("date").dropna()
    if len(frame) < 40:
        raise AppError(
            "INSUFFICIENT_DATA",
            f"可用于训练的历史天数为 {len(frame)}，至少需要 40 天",
            400,
        )

    feature_names = [column for column in frame.columns if column not in {"date", "plays"}]
    X = frame[feature_names].astype(float)
    y = frame["plays"].astype(float)

    splitter = TimeSeriesSplit(n_splits=3)
    selection: list[dict[str, Any]] = []
    fitted: dict[str, Any] = {}

    for name, estimator in _regression_candidates(args.model_family):
        folds: list[dict[str, float]] = []
        last_valid_index = None
        for train_index, valid_index in splitter.split(X):
            candidate = clone(estimator)
            candidate.fit(X.iloc[train_index], y.iloc[train_index])
            predictions = candidate.predict(X.iloc[valid_index])
            folds.append(
                {
                    "mae": round(
                        float(mean_absolute_error(y.iloc[valid_index], predictions)), 4
                    ),
                    "rmse": round(
                        float(
                            math.sqrt(
                                mean_squared_error(y.iloc[valid_index], predictions)
                            )
                        ),
                        4,
                    ),
                }
            )
            last_valid_index = valid_index
        mean_mae = float(np.mean([item["mae"] for item in folds]))
        selection.append({"model": name, "mean_mae": round(mean_mae, 4)})
        fitted[name] = (clone(estimator), folds, last_valid_index)

    best_name = min(selection, key=lambda item: item["mean_mae"])["model"]
    best_estimator, best_folds, best_valid_index = fitted[best_name]
    best_estimator.fit(X, y)

    model_path = storage.artifact_dir(ctx.session_id, run.id) / "model.joblib"
    joblib.dump(
        {
            "task": "regression",
            "model": best_estimator,
            "features": feature_names,
            "target": "plays",
        },
        model_path,
    )

    importance = _feature_importance(
        best_estimator,
        feature_names,
        X.iloc[best_valid_index],
        y.iloc[best_valid_index],
    )

    return {
        "task": "regression",
        "target": "plays",
        "model_family": best_name,
        "model_path": storage.to_relative(model_path),
        "features": feature_names,
        "metrics": {
            "mae": round(float(np.mean([item["mae"] for item in best_folds])), 4),
            "rmse": round(float(np.mean([item["rmse"] for item in best_folds])), 4),
        },
        "folds": best_folds,
        "selection": selection,
        "feature_importance": importance,
        "sample_size": len(frame),
        "train_range": {
            "start": str(pd.to_datetime(frame["date"]).min().date()),
            "end": str(pd.to_datetime(frame["date"]).max().date()),
        },
        "forecast": _recursive_forecast(
            best_estimator, frame, feature_names, args.horizon
        ),
    }


def _classification_matrix(
    frame: pd.DataFrame, target: str
) -> tuple[pd.DataFrame, pd.Series]:
    y = frame[target].astype(str)
    feature_frame = frame.drop(columns=[target])
    numeric = feature_frame.apply(pd.to_numeric, errors="coerce")
    numeric = numeric.loc[:, numeric.notna().any()]

    categoricals = [
        column
        for column in feature_frame.columns
        if column not in numeric.columns
        and 2 <= feature_frame[column].nunique(dropna=True) <= HIGH_CARDINALITY_LIMIT
    ]
    encoded = pd.get_dummies(
        feature_frame[categoricals].astype(str), dummy_na=False
    ).astype(float)

    matrix = pd.concat([numeric.fillna(0.0), encoded], axis=1)
    matrix = matrix.loc[:, matrix.nunique() > 1]
    if matrix.shape[1] == 0:
        raise AppError("INSUFFICIENT_DATA", "没有可用于分类训练的特征列", 400)
    return matrix, y


async def _train_classification(
    args: TrainArgs, ctx: ToolContext, dataset, run, work
) -> dict[str, Any]:
    if not args.target:
        raise AppError("INVALID_ARGUMENT", "分类任务必须指定 target 列", 400)

    frame_path = work / "supervised.parquet"
    await run_job(
        "supervised_frame",
        {
            "path": str(dataset.path),
            "spec": dataset.spec.to_dict(),
            "target": args.target,
            "limit": CLASSIFICATION_SAMPLE_LIMIT,
            "output_path": str(frame_path),
        },
        work,
        MODEL_TIMEOUT_SECONDS,
    )

    frame = pd.read_parquet(frame_path)
    if args.target not in frame.columns:
        raise AppError("INVALID_ARGUMENT", f"目标列不存在: {args.target}", 400)

    X, y = _classification_matrix(frame, args.target)
    class_counts = y.value_counts()
    if len(class_counts) < 2:
        raise AppError("INSUFFICIENT_DATA", "目标列至少需要 2 个类别", 400)
    if len(class_counts) > 50:
        raise AppError("INVALID_ARGUMENT", "目标列类别过多，当前最多支持 50 类", 400)
    if int(class_counts.min()) < 3:
        raise AppError("INSUFFICIENT_DATA", "每个类别至少需要 3 个样本", 400)

    n_splits = min(3, int(class_counts.min()))
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    selection: list[dict[str, Any]] = []
    fitted: dict[str, tuple[Any, list[dict[str, float]], np.ndarray, np.ndarray]] = {}

    for name, estimator in _classification_candidates(args.model_family):
        folds: list[dict[str, float]] = []
        last_true = last_pred = None
        for train_index, valid_index in splitter.split(X, y):
            candidate = clone(estimator)
            candidate.fit(X.iloc[train_index], y.iloc[train_index])
            predictions = candidate.predict(X.iloc[valid_index])
            folds.append(
                {
                    "accuracy": round(
                        float(accuracy_score(y.iloc[valid_index], predictions)), 4
                    ),
                    "macro_f1": round(
                        float(
                            f1_score(
                                y.iloc[valid_index], predictions, average="macro"
                            )
                        ),
                        4,
                    ),
                }
            )
            last_true = y.iloc[valid_index].to_numpy()
            last_pred = predictions
        selection.append(
            {
                "model": name,
                "mean_macro_f1": round(
                    float(np.mean([item["macro_f1"] for item in folds])), 4
                ),
            }
        )
        fitted[name] = (clone(estimator), folds, last_true, last_pred)

    best_name = max(selection, key=lambda item: item["mean_macro_f1"])["model"]
    best_estimator, best_folds, best_true, best_pred = fitted[best_name]
    best_estimator.fit(X, y)

    model_path = storage.artifact_dir(ctx.session_id, run.id) / "model.joblib"
    joblib.dump(
        {
            "task": "classification",
            "model": best_estimator,
            "features": list(X.columns),
            "target": args.target,
        },
        model_path,
    )

    labels = sorted(y.unique().tolist())
    matrix = confusion_matrix(best_true, best_pred, labels=labels).tolist()
    importance = _feature_importance(best_estimator, list(X.columns), X, y)

    return {
        "task": "classification",
        "target": args.target,
        "model_family": best_name,
        "model_path": storage.to_relative(model_path),
        "features": list(X.columns),
        "classes": labels,
        "metrics": {
            "accuracy": round(
                float(np.mean([item["accuracy"] for item in best_folds])), 4
            ),
            "macro_f1": round(
                float(np.mean([item["macro_f1"] for item in best_folds])), 4
            ),
        },
        "folds": best_folds,
        "selection": selection,
        "confusion_matrix": {"labels": labels, "matrix": matrix},
        "feature_importance": importance,
        "sample_size": len(X),
    }


async def train_predictive_model(args: TrainArgs, ctx: ToolContext) -> ToolResult:
    dataset = await dataset_service.resolve_dataset(
        ctx.db, ctx.session_id, args.file_id
    )
    if dataset.spec.kind != "actions" and args.task == "regression":
        raise AppError("INVALID_FILE", "回归预测需要用户行为表", 400)

    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "train_predictive_model",
        args.model_dump(mode="json"),
        file_id=args.file_id,
    )

    try:
        work = storage.work_dir(ctx.session_id, run.id)
        if args.task == "regression":
            payload = await _train_regression(args, ctx, dataset, run, work)
            summary = (
                f"回归模型 {payload['model_family']}：MAE={payload['metrics']['mae']}、"
                f"RMSE={payload['metrics']['rmse']}，已生成未来 {len(payload['forecast'])} 天预测"
            )
        else:
            payload = await _train_classification(args, ctx, dataset, run, work)
            summary = (
                f"分类模型 {payload['model_family']}：accuracy="
                f"{payload['metrics']['accuracy']}、macro_f1={payload['metrics']['macro_f1']}"
            )

        artifact = await artifact_service.create_artifact(
            ctx.db, run.id, "model", payload
        )
        await run_service.finish_run(ctx.db, run, result_path=str(work))
    except AppError as exc:
        await run_service.finish_run(ctx.db, run, status="failed", error=exc.message)
        raise

    return ToolResult(
        run_id=run.id,
        summary=summary,
        artifact_ids=[artifact.id],
        data={
            "model_id": str(artifact.id),
            "task": payload["task"],
            "model_family": payload["model_family"],
            "metrics": payload["metrics"],
            "target": payload["target"],
        },
    )
