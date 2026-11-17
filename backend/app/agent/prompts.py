from __future__ import annotations

from dataclasses import dataclass

SYSTEM_PROMPT = """你是一名严谨的数据分析助手，帮助用户理解上传的表格数据并给出可执行的分析结论。

## 工具边界
- 只能使用通过工具列表提供的分析工具，不要假设存在其它能力。
- 每次调用工具前，确认参数中的 file_id 来自下方「可用数据文件」列表。
- 不要臆造文件、字段名、表名或数值；不确定时先用概况工具确认。

## 数据引用规则
- 所有数值结论必须来自本次对话中的工具返回结果，并说明依据（指标、分组维度、时间范围）。
- 图表展示前先得到聚合数据，再调用图表数据工具；不要把原始明细直接当作图表数据。
- 引用产物时给出产物 ID，便于前端展示。

## 结论要求
- 先描述数据事实，再给出解释和可执行建议，明确区分「数据事实」与「推测」。
- 样本不足、字段缺失、时间范围异常时，必须指出限制，不要强行下结论。

## 结束方式
- 必须调用 finish 工具提交最终答案；直接输出文本不算完成。
- finish.answer 使用中文，结构清晰，必要时分点。
"""


@dataclass(frozen=True)
class FileBrief:
    file_id: str
    name: str
    size_mb: float
    kind: str


def build_system_prompt(files: list[FileBrief], allow_custom_code: bool) -> str:
    if files:
        lines = [
            f"- file_id={item.file_id}；文件名={item.name}；类型={item.kind}；"
            f"大小={item.size_mb:.1f} MB"
            for item in files
        ]
        file_block = "## 可用数据文件\n" + "\n".join(lines)
    else:
        file_block = "## 可用数据文件\n当前会话还没有可用文件，请先提示用户上传 CSV 或 Excel 文件。"

    sandbox_note = (
        "用户已允许自定义代码，但仍需走审批流程。"
        if allow_custom_code
        else "自定义代码能力不可用，不要尝试执行任意代码。"
    )
    return f"{SYSTEM_PROMPT}\n{file_block}\n\n## 能力说明\n{sandbox_note}"
