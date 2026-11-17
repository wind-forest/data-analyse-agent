from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.errors import AppError
from app.tools import (
    aggregate,
    chart,
    evaluate,
    memory,
    modeling,
    profile,
    sandbox_tool,
    time_features,
)
from app.tools.base import ToolContext, ToolDefinition, ToolResult
from app.tools.finish import FINISH_TOOL

TOOLS: dict[str, ToolDefinition] = {
    "profile_dataset": ToolDefinition(
        name="profile_dataset",
        description="查看数据集概况：行数、字段类型、缺失率、基础统计、样本行",
        args_model=profile.ProfileArgs,
        handler=profile.profile_dataset,
    ),
    "aggregate_plays": ToolDefinition(
        name="aggregate_plays",
        description="按维度聚合播放/下载/收藏次数或活跃用户数，支持时间范围和过滤",
        args_model=aggregate.AggregateArgs,
        handler=aggregate.aggregate_plays,
    ),
    "build_time_features": ToolDefinition(
        name="build_time_features",
        description="构建按天/小时/星期的播放量时间序列及滞后、滚动特征",
        args_model=time_features.TimeFeatureArgs,
        handler=time_features.build_time_features,
    ),
    "train_predictive_model": ToolDefinition(
        name="train_predictive_model",
        description="训练回归或分类模型；回归可预测未来若干天的播放量",
        args_model=modeling.TrainArgs,
        handler=modeling.train_predictive_model,
    ),
    "evaluate_model": ToolDefinition(
        name="evaluate_model",
        description="查看已训练模型的验证指标、特征重要性和预测结果",
        args_model=evaluate.EvaluateArgs,
        handler=evaluate.evaluate_model,
    ),
    "generate_chart_data": ToolDefinition(
        name="generate_chart_data",
        description="基于表格产物生成柱状、折线或散点图所需的聚合数据",
        args_model=chart.ChartArgs,
        handler=chart.generate_chart_data,
    ),
    "query_session_memory": ToolDefinition(
        name="query_session_memory",
        description="查询本会话已完成的分析步骤和会话摘要，避免重复计算",
        args_model=memory.MemoryArgs,
        handler=memory.query_session_memory,
    ),
    "execute_python_snippet": ToolDefinition(
        name="execute_python_snippet",
        description="在隔离沙箱中执行受限 Python 代码（需要用户审批）",
        args_model=sandbox_tool.SnippetArgs,
        handler=sandbox_tool.execute_python_snippet,
        risk="high",
    ),
}


def list_tool_schemas() -> list[dict[str, Any]]:
    return [
        definition.schema()
        for definition in TOOLS.values()
        if definition.enabled
    ]


def agent_tool_schemas(allow_custom_code: bool = False) -> list[dict[str, Any]]:
    """暴露给 Agent 的工具；finish 始终存在，高风险工具按需注册。"""
    from app.sandbox.manager import is_available

    definitions = [
        item
        for name, item in TOOLS.items()
        if item.enabled and name != "execute_python_snippet"
    ]
    if allow_custom_code and is_available():
        definitions.append(TOOLS["execute_python_snippet"])
    definitions.append(FINISH_TOOL)
    return [item.schema() for item in definitions]


def tool_risk(name: str) -> str:
    definition = TOOLS.get(name)
    return definition.risk if definition else "low"


async def execute_tool(
    name: str, raw_args: dict[str, Any], ctx: ToolContext
) -> ToolResult:
    definition = TOOLS.get(name)
    if definition is None or not definition.enabled:
        raise AppError("TOOL_NOT_AVAILABLE", f"工具不可用: {name}", 400)

    try:
        args = definition.args_model.model_validate(raw_args)
    except ValidationError as exc:
        raise AppError(
            "TOOL_VALIDATION_ERROR",
            f"工具 {name} 参数校验失败",
            422,
            {"errors": exc.errors(include_url=False)},
        ) from exc

    return await definition.handler(args, ctx)
