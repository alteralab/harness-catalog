"""pin evals 의 레지스트리 스텁이 진짜 레지스트리와 같은 모양을 내고, 그 응답을 `hc pin`(pin.py)이 그대로 받아 설치까지 가는지 — 스텁을 실제 서브프로세스로 띄워 MCP 클라이언트로 부른다.

의존성 mcp==2.3.0 은 uv 가 PEP 723 머리에서 받는다(캐시되면 네트워크 없음).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from harness_catalog_cli import pin
from harness_catalog_server.driving.responses import ErrorResponse, GetSkillResponse, SearchSkillsResponse, SearchToolsResponse

STUB_DIR = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates/skills/pin/evals/pin-project-scope/environment/stub"


@pytest.mark.anyio
async def test_stub_get_skill_archive_feeds_hc_pin(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    uv = shutil.which("uv")
    assert uv, "uv is required"
    params = StdioServerParameters(command=uv, args=["run", "--script", str(STUB_DIR / "registry_stub.py"), str(STUB_DIR / "fixture")], env={**os.environ})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        assert sorted(t.name for t in listed.tools) == ["get_skill", "get_tool", "search_skills", "search_tools"]
        hits = await session.call_tool("search_skills", {"query": "자막"})
        assert not hits.is_error
        SearchSkillsResponse.model_validate(hits.structured_content)  # 서버 pydantic 모델이 그대로 받는다 — 스텁 모양의 드리프트는 여기서 깨진다
        skills = cast(list[dict[str, Any]], cast(dict[str, Any], hits.structured_content)["skills"])
        assert [s["name"] for s in skills] == ["yt-subs"] and len(skills[0]["sha"]) == 40 and skills[0]["has_scripts"] is False
        got = await session.call_tool("get_skill", {"id": "yt-subs", "sha": skills[0]["sha"], "archive": True})
        assert not got.is_error
        payload = cast(dict[str, Any], got.structured_content)
        GetSkillResponse.model_validate(payload)
        SearchToolsResponse.model_validate((await session.call_tool("search_tools", {"query": "x"})).structured_content)
        assert payload["body"].startswith("# yt-subs") and {f["path"] for f in payload["files"]} == {"SKILL.md", "references/langs.md"}
        assert payload["archive"]["headers"]["Authorization"].startswith("Bearer ") and payload["archive"]["digest"] == f"git-tree:{payload['sha']}"
        # 스텁이 살아 있는 동안(HTTP 스레드) hc pin 의 결정적 꼬리를 그대로 — 받기·대조·풀기·PINNED·링크
        rec = pin.parse_response(payload)
        target = pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path, now=datetime(2026, 10, 18, tzinfo=UTC))
        assert target == tmp_path / ".agents" / "skills" / "yt-subs"
        assert (target / "SKILL.md").read_text().startswith("---\nname: yt-subs") and (target / "references" / "langs.md").is_file()
        assert (target / "PINNED").read_text() == f"yt-subs {payload['sha']} 2026-10-18T00:00:00Z\n"
        assert (tmp_path / ".claude" / "skills" / "yt-subs").is_symlink()
        missing = await session.call_tool("get_skill", {"id": "nope"})
        assert missing.is_error and ErrorResponse.model_validate(json.loads(missing.content[0].text)).code == "not_found"  # type: ignore[union-attr]
        wrong = await session.call_tool("get_skill", {"id": "yt-subs", "sha": "0" * 40})
        assert wrong.is_error and ErrorResponse.model_validate(wrong.structured_content).code == "unknown_version"
