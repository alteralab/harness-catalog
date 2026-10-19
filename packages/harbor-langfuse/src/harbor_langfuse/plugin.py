"""Harbor JobPlugin → Langfuse. 잡 시작에 dataset·item·run을 준비하고, 잡 끝에 트라이얼마다 trace·run item·score(passed)를 남긴다.

Harbor는 TYPE_CHECKING에서만 import한다(플러그인 로딩은 Harbor가 하고, 시험은 가짜 잡 객체로 돈다). Langfuse 호출은 Sink 포트 뒤에 둔다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from harbor.job import Job
    from harbor.models.job.result import JobResult

SCORE_NAME = "passed"
SKILL_REF_ENV = "HARNESS_SKILL_REF"  # 주입한 스킬 원천의 ref(커밋 SHA). Harbor는 스킬 원천을 캐시 경로로 바꿔 Job에 넘기므로 호출자가 준다


class TrialRecord(NamedTuple):
    """트라이얼 하나를 Langfuse에 남기는 데 필요한 것."""

    case: str  # evals/<case>
    trial_name: str
    trial_uri: str
    instruction: str
    verifier_output: str  # rewards 전체(JSON) — Harbor 0.24의 VerifierResult에는 rewards뿐이다
    reward: float | None
    passed: bool
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    exception: str | None


class RunContext(NamedTuple):
    """잡 하나 = dataset run 하나."""

    dataset: str  # <catalog>/<skill>
    run_name: str
    metadata: Mapping[str, str]
    cases: tuple[tuple[str, str], ...]  # (case, instruction)


class Sink(Protocol):
    """Langfuse 쪽 요구 포트. 실물은 LangfuseSink, 시험은 가짜."""

    def ensure_dataset(self, name: str, items: Mapping[str, str]) -> None: ...
    def record_run(self, run: RunContext, trials: tuple[TrialRecord, ...]) -> None: ...
    def flush(self) -> None: ...


def read_cases(dataset_path: Path) -> tuple[tuple[str, str], ...]:
    """evals/<case>/instruction.md마다 (case, instruction)."""
    out: list[tuple[str, str]] = []
    for case_dir in sorted(p for p in dataset_path.iterdir() if p.is_dir()):
        instruction = case_dir / "instruction.md"
        if instruction.is_file():
            out.append((case_dir.name, instruction.read_text()))
    return tuple(out)


def dataset_name(dataset_path: Path, catalog: str) -> str:
    """evals/의 부모가 스킬 디렉토리다: skills/<skill>/evals → <catalog>/<skill>."""
    return f"{catalog}/{dataset_path.parent.name}"


def scenario_sha(dataset_path: Path) -> str:
    """evals/ 디렉토리의 git tree SHA(저장소 안이면). 아니면 빈 문자열."""
    proc = subprocess.run(["git", "-C", str(dataset_path), "rev-parse", "HEAD:./"], capture_output=True, text=True, check=False, timeout=30)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def run_context(job: Any, *, catalog: str, environ: Mapping[str, str] = os.environ) -> RunContext:
    """Harbor Job에서 run 재료를 읽는다(필드 이름은 Harbor 0.24 실측: config.datasets[].path, agents[].name·model_name·skills).

    Harbor는 스킬 원천(`org/repo@ref`)을 Job.create()에서 로컬 캐시 경로로 바꾸므로 `sha`는 환경 변수 HARNESS_SKILL_REF로 받는다.
    skills 목록이 비면 baseline(스킬 없이)이다.
    """
    cfg = job.config
    dataset_path = Path(str(cfg.datasets[0].path)) if getattr(cfg, "datasets", None) else Path(".")
    agent = cfg.agents[0] if getattr(cfg, "agents", None) else None
    skills: list[object] = list(getattr(agent, "skills", None) or [])
    metadata = {
        "skill": dataset_path.parent.name,
        "sha": environ.get(SKILL_REF_ENV, "") if skills else "",
        "scenario_sha": scenario_sha(dataset_path),
        "model": str(getattr(agent, "model_name", "") or ""),
        "harness": str(getattr(agent, "name", "") or ""),
        "baseline": "false" if skills else "true",
    }
    return RunContext(dataset_name(dataset_path, catalog), str(cfg.job_name), metadata, read_cases(dataset_path))


def trial_records(job_result: Any, run: RunContext) -> tuple[TrialRecord, ...]:
    instructions = dict(run.cases)
    out: list[TrialRecord] = []
    for t in job_result.trial_results:
        vr = t.verifier_result
        rewards: Mapping[str, object] = dict(getattr(vr, "rewards", None) or {}) if vr is not None else {}
        raw = rewards.get("reward")
        reward = float(raw) if isinstance(raw, (int, float)) else None
        # 단일 단계는 agent_result, 다단계는 step_results[].agent_result — Harbor가 합산 함수를 준다
        totals = t.compute_token_cost_totals() if hasattr(t, "compute_token_cost_totals") else (None, None, None, None)
        exc = t.exception_info
        out.append(TrialRecord(
            case=t.task_name, trial_name=t.trial_name, trial_uri=t.trial_uri, instruction=instructions.get(t.task_name, ""),
            verifier_output=json.dumps(rewards, ensure_ascii=False, default=str), reward=reward, passed=reward is not None and reward >= 1.0,
            input_tokens=totals[0], output_tokens=totals[2], cost_usd=totals[3],
            exception=f"{exc.exception_type}: {exc.exception_message}" if exc is not None else None,
        ))
    return tuple(out)


class LangfusePlugin:
    """Harbor BaseJobPlugin 계약(on_job_start·on_job_end)을 만족한다. 상속 대신 덕 타이핑 — Harbor를 import하지 않기 위해."""

    def __init__(self, sink: Sink | None = None, *, catalog: str | None = None, environ: Mapping[str, str] | None = None, **_: Any) -> None:
        self._sink = sink
        self._environ: Mapping[str, str] = environ if environ is not None else os.environ
        self._catalog = catalog or self._environ.get("HARNESS_CATALOG_NAME", "catalog")
        self._run: RunContext | None = None

    @property
    def run(self) -> RunContext | None:
        """현재 잡의 run 재료(on_job_start 뒤)."""
        return self._run

    def _get_sink(self) -> Sink:
        if self._sink is None:
            from .sink import LangfuseSink

            self._sink = LangfuseSink.from_env()
        return self._sink

    async def on_job_start(self, job: Job) -> None:
        self._run = run_context(job, catalog=self._catalog, environ=self._environ)
        self._get_sink().ensure_dataset(self._run.dataset, dict(self._run.cases))

    async def on_job_end(self, job_result: JobResult) -> None:
        if self._run is None:
            return
        sink = self._get_sink()
        sink.record_run(self._run, trial_records(job_result, self._run))
        sink.flush()
