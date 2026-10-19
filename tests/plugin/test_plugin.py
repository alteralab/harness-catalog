"""플러그인: Harbor 0.24 실물 모델(TrialResult·VerifierResult·AgentContext·ExceptionInfo)과 가짜 Sink로 호출을 기록한다."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from harbor.models.agent.context import AgentContext
from harbor.models.trial.result import ExceptionInfo, TrialResult
from harbor.models.verifier.result import VerifierResult
from harbor_langfuse.plugin import (
    SKILL_REF_ENV,
    LangfusePlugin,
    RunContext,
    TrialRecord,
    read_cases,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class FakeSink:
    def __init__(self) -> None:
        self.datasets: list[tuple[str, Mapping[str, str]]] = []
        self.runs: list[tuple[RunContext, tuple[TrialRecord, ...]]] = []
        self.flushed = 0

    def ensure_dataset(self, name: str, items: Mapping[str, str]) -> None:
        self.datasets.append((name, dict(items)))

    def record_run(self, run: RunContext, trials: tuple[TrialRecord, ...]) -> None:
        self.runs.append((run, trials))

    def flush(self) -> None:
        self.flushed += 1


def make_evals(tmp_path: Path) -> Path:
    """git 저장소 안의 skills/yt-subs/evals — scenario_sha를 실측할 수 있게."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    evals = tmp_path / "skills" / "yt-subs" / "evals"
    for case, text in (("fetch-subs", "Get the subtitles."), ("no-trigger-weather", "What is the weather?")):
        (evals / case).mkdir(parents=True)
        (evals / case / "instruction.md").write_text(text)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "evals"], check=True)
    return evals


def trial(task: str, name: str, reward: float | None, *, tokens: tuple[int, int, float] | None = None, exc: ExceptionInfo | None = None, multi_step: bool = False) -> TrialResult:
    base: dict[str, Any] = {
        "id": uuid4(), "task_name": task, "trial_name": name, "trial_uri": f"file:///{name}", "task_checksum": "x",
        "task_id": SimpleNamespace(path=task), "config": SimpleNamespace(), "agent_info": SimpleNamespace(name="claude-code", version="1"),
        "verifier_result": VerifierResult(rewards={"reward": reward}) if reward is not None else None, "exception_info": exc,
    }
    ctx = AgentContext(n_input_tokens=tokens[0], n_output_tokens=tokens[1], cost_usd=tokens[2]) if tokens else None
    if multi_step and ctx is not None:
        base["step_results"] = [SimpleNamespace(agent_result=ctx), SimpleNamespace(agent_result=ctx)]
    else:
        base["agent_result"] = ctx
    return TrialResult.model_construct(**base)


def job_for(evals: Path, *, skills: list[str], agent: str = "claude-code", model: str = "claude-sonnet-5", name: str = "job-1") -> SimpleNamespace:
    # Harbor JobConfig의 필드 이름 그대로: datasets[].path, agents[].name·model_name·skills (Harbor는 skills를 캐시 경로로 바꾼다)
    return SimpleNamespace(config=SimpleNamespace(job_name=name, datasets=[SimpleNamespace(path=str(evals))], agents=[SimpleNamespace(name=agent, model_name=model, skills=skills)]))


@pytest.mark.anyio
async def test_job_start_and_end_record_runs(tmp_path: Path) -> None:
    evals = make_evals(tmp_path)
    assert [c for c, _ in read_cases(evals)] == ["fetch-subs", "no-trigger-weather"]
    job = job_for(evals, skills=[str(tmp_path / "harbor-cache" / "skills" / "abc")])  # Harbor가 바꿔 넣는 캐시 경로 — sha는 환경 변수에서
    result = SimpleNamespace(trial_results=[
        trial("fetch-subs", "t1", 1.0, tokens=(10, 5, 0.01)),
        trial("no-trigger-weather", "t2", 0.0, tokens=(7, 3, 0.02), exc=ExceptionInfo(exception_type="Timeout", exception_message="slow", exception_traceback="", occurred_at=datetime.now(UTC)), multi_step=True),
    ])
    sink = FakeSink()
    plugin = LangfusePlugin(sink, catalog="team-catalog", environ={SKILL_REF_ENV: "abc123"})
    await plugin.on_job_start(job)  # type: ignore[arg-type]
    await plugin.on_job_end(result)  # type: ignore[arg-type]
    assert sink.datasets == [("team-catalog/yt-subs", {"fetch-subs": "Get the subtitles.", "no-trigger-weather": "What is the weather?"})]
    (run, trials), = sink.runs
    assert run.run_name == "job-1" and run.metadata["skill"] == "yt-subs" and run.metadata["sha"] == "abc123"
    assert run.metadata["harness"] == "claude-code" and run.metadata["baseline"] == "false" and len(run.metadata["scenario_sha"]) == 40
    t1, t2 = trials
    assert t1.passed and t1.input_tokens == 10 and t1.output_tokens == 5 and t1.instruction == "Get the subtitles." and t1.verifier_output == '{"reward": 1.0}'
    assert not t2.passed and t2.exception == "Timeout: slow" and t2.input_tokens == 14 and t2.cost_usd == pytest.approx(0.04)  # 다단계 합산
    assert sink.flushed == 1


@pytest.mark.anyio
async def test_baseline_when_no_skill_injected(tmp_path: Path) -> None:
    evals = make_evals(tmp_path)
    sink = FakeSink()
    plugin = LangfusePlugin(sink, catalog="c")
    await plugin.on_job_start(job_for(evals, skills=[], agent="codex", model="", name="baseline"))  # type: ignore[arg-type]
    await plugin.on_job_end(SimpleNamespace(trial_results=[]))  # type: ignore[arg-type]
    assert sink.datasets[0][0] == "c/yt-subs" and plugin.run is not None and plugin.run.metadata["baseline"] == "true" and plugin.run.metadata["sha"] == ""
