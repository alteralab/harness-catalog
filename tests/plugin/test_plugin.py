"""플러그인: 가짜 Job·JobResult 표본과 가짜 Sink로 호출을 기록한다(Harbor·Langfuse 없이)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from harbor_langfuse.plugin import LangfusePlugin, RunContext, TrialRecord, read_cases


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
    evals = tmp_path / "skills" / "yt-subs" / "evals"
    for case, text in (("fetch-subs", "Get the subtitles."), ("no-trigger-weather", "What is the weather?")):
        (evals / case).mkdir(parents=True)
        (evals / case / "instruction.md").write_text(text)
    return evals


@pytest.mark.anyio
async def test_job_start_and_end_record_runs(tmp_path: Path) -> None:
    evals = make_evals(tmp_path)
    assert [c for c, _ in read_cases(evals)] == ["fetch-subs", "no-trigger-weather"]
    job = SimpleNamespace(config=SimpleNamespace(
        job_name="2026-10-07-yt-subs", datasets=[SimpleNamespace(path=str(evals))],
        agents=[SimpleNamespace(name="claude-code", model_name="claude-sonnet-5", skills=["alteralab/catalog@abc123"])],
    ))
    result = SimpleNamespace(trial_results=[
        SimpleNamespace(task_name="fetch-subs", trial_name="t1", trial_uri="file:///t1", verifier_result=SimpleNamespace(rewards={"reward": 1.0}, stdout="ok"),
                        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.01), exception_info=None),
        SimpleNamespace(task_name="no-trigger-weather", trial_name="t2", trial_uri="file:///t2", verifier_result=SimpleNamespace(rewards={"reward": 0.0}, stdout="used skill"),
                        agent_result=None, exception_info=SimpleNamespace(exception_type="Timeout", exception_message="slow")),
    ])
    sink = FakeSink()
    plugin = LangfusePlugin(sink, catalog="team-catalog")
    await plugin.on_job_start(job)  # type: ignore[arg-type]
    await plugin.on_job_end(result)  # type: ignore[arg-type]
    assert sink.datasets == [("team-catalog/yt-subs", {"fetch-subs": "Get the subtitles.", "no-trigger-weather": "What is the weather?"})]
    (run, trials), = sink.runs
    assert run.run_name == "2026-10-07-yt-subs" and run.metadata["skill"] == "yt-subs" and run.metadata["sha"] == "abc123"
    assert run.metadata["harness"] == "claude-code" and run.metadata["baseline"] == "false"
    t1, t2 = trials
    assert t1.passed and t1.input_tokens == 10 and t1.instruction == "Get the subtitles."
    assert not t2.passed and t2.exception == "Timeout: slow"
    assert sink.flushed == 1


@pytest.mark.anyio
async def test_baseline_when_no_skill_injected(tmp_path: Path) -> None:
    evals = make_evals(tmp_path)
    job = SimpleNamespace(config=SimpleNamespace(job_name="baseline", datasets=[SimpleNamespace(path=str(evals))], agents=[SimpleNamespace(name="codex", model_name="", skills=[])]))
    sink = FakeSink()
    plugin = LangfusePlugin(sink, catalog="c")
    await plugin.on_job_start(job)  # type: ignore[arg-type]
    await plugin.on_job_end(SimpleNamespace(trial_results=[]))  # type: ignore[arg-type]
    assert sink.datasets[0][0] == "c/yt-subs" and plugin.run is not None and plugin.run.metadata["baseline"] == "true"
