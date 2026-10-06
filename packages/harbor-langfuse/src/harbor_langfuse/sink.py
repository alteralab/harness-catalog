"""Langfuse 실물 Sink — SDK v4.17(실측 2026-10-07). dataset run은 `run_experiment`로 만든다: Harbor가 이미 돌린 결과를
task(항목 → 검증기 출력)와 evaluator(항목 → passed)로 되돌려 주면 Langfuse가 trace·run item·score를 함께 기록한다.
(`api.dataset_run_items.create`는 Cloud에서 2026-11-16 폐기 예정이라 쓰지 않는다 — SDK의 deprecation 문구.)

Langfuse Cloud에 대한 왕복 실측은 pilot Q14(e)의 몫이다 — 그 전까지 이 파일은 시그니처 실측 기준이다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast

from langfuse import Langfuse
from langfuse.experiment import Evaluation

from .plugin import SCORE_NAME, RunContext, TrialRecord


def _case_of(item: Any) -> str | None:
    meta = cast(Mapping[str, Any] | None, getattr(item, "metadata", None))
    return str(meta["case"]) if isinstance(meta, Mapping) and "case" in meta else None


class LangfuseSink:
    def __init__(self, client: Langfuse) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> LangfuseSink:
        missing = [k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Langfuse credentials missing: {', '.join(missing)}")
        return cls(Langfuse())

    def ensure_dataset(self, name: str, items: Mapping[str, str]) -> None:
        self._client.create_dataset(name=name)  # 있으면 그대로(멱등)
        existing = {c for c in (_case_of(i) for i in self._client.get_dataset(name).items) if c is not None}
        for case, instruction in items.items():
            if case not in existing:
                self._client.create_dataset_item(dataset_name=name, input=instruction, metadata={"case": case})

    def record_run(self, run: RunContext, trials: tuple[TrialRecord, ...]) -> None:
        by_case = {t.case: t for t in trials}
        items = [i for i in self._client.get_dataset(run.dataset).items if _case_of(i) in by_case]

        def task(*, item: Any, **_: Any) -> str:
            t = by_case[str(_case_of(item))]
            return t.verifier_output

        def passed(*, item: Any = None, **_: Any) -> Evaluation:
            t = by_case[str(_case_of(item))] if item is not None else None
            return Evaluation(name=SCORE_NAME, value=bool(t.passed) if t else False, data_type="BOOLEAN", comment=t.exception if t else None,
                              metadata={"trial_uri": t.trial_uri, "input_tokens": t.input_tokens, "output_tokens": t.output_tokens, "cost_usd": t.cost_usd} if t else None)

        self._client.run_experiment(name=run.dataset, run_name=run.run_name, data=items, task=task, evaluators=[passed], metadata=dict(run.metadata), max_concurrency=1)

    def flush(self) -> None:
        self._client.flush()
