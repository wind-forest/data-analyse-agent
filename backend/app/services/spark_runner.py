from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.errors import AppError

logger = logging.getLogger("app.spark")

JOB_DIR = Path(__file__).resolve().parents[1] / "spark_jobs"
MAX_LOG_CHARS = 8000


def _submit_command(job_path: Path, args_path: Path, result_path: Path) -> list[str]:
    cores = max(2, min(os.cpu_count() or 2, 8))
    return [
        "spark-submit",
        "--master",
        f"local[{cores}]",
        "--conf",
        "spark.ui.enabled=false",
        "--conf",
        "spark.driver.memory=2g",
        "--conf",
        f"spark.sql.shuffle.partitions={max(cores * 2, 8)}",
        "--conf",
        "spark.sql.execution.arrow.pyspark.enabled=true",
        "--conf",
        "spark.sql.session.timeZone=Asia/Shanghai",
        str(job_path),
        str(args_path),
        str(result_path),
    ]


async def run_job(
    job_name: str,
    payload: dict[str, Any],
    work_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """在独立进程中运行 Spark 作业，绝不阻塞 FastAPI 事件循环。"""
    job_path = JOB_DIR / f"{job_name}.py"
    if not job_path.exists():
        raise AppError("TOOL_EXECUTION_FAILED", f"Spark 作业不存在: {job_name}", 500)

    work_dir.mkdir(parents=True, exist_ok=True)
    args_path = work_dir / "job_args.json"
    result_path = work_dir / "job_result.json"
    args_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(JOB_DIR), env.get("PYTHONPATH", "")) if part
    )

    process = await asyncio.create_subprocess_exec(
        *_submit_command(job_path, args_path, result_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise AppError(
            "RUN_TIMEOUT", f"Spark 作业超过 {timeout_seconds} 秒被终止", 504
        )

    out_text = (stdout or b"").decode("utf-8", "replace")[-MAX_LOG_CHARS:]
    err_text = (stderr or b"").decode("utf-8", "replace")[-MAX_LOG_CHARS:]

    if process.returncode != 0:
        combined = f"{out_text}\n{err_text}".strip()
        logger.error("spark job %s failed: %s", job_name, combined[-MAX_LOG_CHARS:])
        raise AppError(
            "TOOL_EXECUTION_FAILED",
            f"Spark 作业执行失败（退出码 {process.returncode}）",
            500,
            {"output": combined[-3000:]},
        )

    if not result_path.exists():
        logger.error("spark job %s produced no result: %s", job_name, out_text)
        raise AppError("TOOL_EXECUTION_FAILED", "Spark 作业未产生结果文件", 500)

    return json.loads(result_path.read_text(encoding="utf-8"))
