"""검색 벤치마크의 합성 말뭉치 — 스킬·도구 N개와 정답 있는 질의 집합을 시드 하나로 결정적으로 만든다(§11 2026-10-19 검색 벤치마크).

진짜 카탈로그에는 넣지 않는다. 어려운 경우를 일부러 만든다:
  - 같은 영역(도메인)에서 대상·동작만 다른 near-duplicate 묶음 — 상위 3이 흐려지는 자리
  - 질의는 발동 낱말 그대로 / 동의어로 바꿔 / 영어로 / kata 가 쓸 과제 문장으로 — 어휘 불일치
  - description 품질 두 벌: 좋은 것(발동 낱말·쓰지 말 상황 포함)과 막연한 것 — review 점검표 A1·A3 의 값을 재는 용도
템플릿 생성이라 실제 저자 글보다 규칙적이다. 그 한계는 README 에 적는다. LLM 보강 집합은 다음 단계.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha1

from harness_catalog_core.model import IndexSnapshot, SkillEntry, ToolEntry

# 도메인 → (대상들, 동작들). 한국어 표기 / 영어 표기 / 동의어(질의에만 쓴다)
DOMAINS: dict[str, dict[str, list[tuple[str, str, list[str]]]]] = {
    "youtube": {
        "objects": [("자막", "subtitles", ["캡션", "자막 텍스트"]), ("댓글", "comments", ["리플", "코멘트"]), ("썸네일", "thumbnail", ["미리보기 이미지"]), ("재생목록", "playlist", ["플레이리스트"]), ("조회수", "view count", ["뷰 수"])],
        "actions": [("추출한다", "extract", ["뽑는다", "가져온다"]), ("요약한다", "summarize", ["정리한다"]), ("내려받는다", "download", ["저장한다"]), ("번역한다", "translate", ["옮긴다"])],
    },
    "git": {
        "objects": [("커밋", "commits", ["변경 이력"]), ("태그", "tags", ["릴리스 태그"]), ("브랜치", "branches", ["가지"]), ("PR", "pull requests", ["풀 리퀘스트", "머지 요청"]), ("diff", "diff", ["변경점", "차이"])],
        "actions": [("종류별로 묶는다", "group by kind", ["분류한다"]), ("정리한다", "list", ["나열한다", "모은다"]), ("비교한다", "compare", ["견준다"]), ("정리해 노트로 만든다", "draft notes from", ["노트로 쓴다"])],
    },
    "docs": {
        "objects": [("README", "README", ["읽어보기 문서"]), ("API 문서", "API reference", ["레퍼런스"]), ("회의록", "meeting notes", ["미팅 노트"]), ("변경 로그", "changelog", ["CHANGELOG", "체인지로그"]), ("위키 페이지", "wiki page", ["위키"])],
        "actions": [("초안을 쓴다", "draft", ["초안 잡는다"]), ("오타를 고친다", "fix typos in", ["맞춤법을 고친다"]), ("구조를 정리한다", "restructure", ["재구성한다"]), ("번역한다", "translate", ["옮긴다"])],
    },
    "data": {
        "objects": [("CSV", "CSV files", ["쉼표 파일"]), ("엑셀 시트", "spreadsheets", ["스프레드시트", "xlsx"]), ("JSON 로그", "JSON logs", ["로그 JSON"]), ("SQL 쿼리", "SQL queries", ["쿼리문"]), ("파케이 파일", "Parquet files", ["parquet"])],
        "actions": [("검증한다", "validate", ["점검한다"]), ("합친다", "merge", ["병합한다", "조인한다"]), ("요약 통계를 낸다", "profile", ["통계를 뽑는다"]), ("변환한다", "convert", ["바꾼다"])],
    },
    "infra": {
        "objects": [("도커 이미지", "docker images", ["컨테이너 이미지"]), ("compose 스택", "compose stacks", ["컴포즈"]), ("인증서", "TLS certificates", ["TLS 인증서", "cert"]), ("백업", "backups", ["스냅샷 백업"]), ("DNS 레코드", "DNS records", ["도메인 레코드"])],
        "actions": [("상태를 점검한다", "check the health of", ["헬스체크한다"]), ("판을 올린다", "upgrade", ["업그레이드한다"]), ("갱신한다", "renew", ["재발급한다"]), ("목록을 뽑는다", "inventory", ["인벤토리를 만든다"])],
    },
    "slack": {
        "objects": [("스레드", "threads", ["쓰레드"]), ("채널 메시지", "channel messages", ["채널 글"]), ("리마인더", "reminders", ["알림"]), ("파일", "shared files", ["첨부 파일"])],
        "actions": [("요약한다", "summarize", ["정리한다"]), ("검색한다", "search", ["찾는다"]), ("보낸다", "post", ["올린다"]), ("아카이브한다", "archive", ["보관한다"])],
    },
    "pdf": {
        "objects": [("표", "tables", ["테이블"]), ("본문", "text", ["텍스트"]), ("양식 필드", "form fields", ["폼"]), ("페이지", "pages", ["쪽"])],
        "actions": [("추출한다", "extract", ["뽑는다"]), ("채운다", "fill", ["입력한다"]), ("합친다", "merge", ["병합한다"]), ("나눈다", "split", ["분할한다"])],
    },
    "calendar": {
        "objects": [("일정", "events", ["약속", "미팅"]), ("빈 시간", "free slots", ["여유 시간"]), ("반복 일정", "recurring events", ["정기 일정"])],
        "actions": [("만든다", "create", ["잡는다"]), ("찾는다", "find", ["검색한다"]), ("옮긴다", "reschedule", ["일정을 바꾼다"]), ("정리한다", "clean up", ["취소한다"])],
    },
}
Term = tuple[str, str, list[str]]  # (한국어, 영어, 질의용 동의어들)
Combo = tuple[str, Term, Term, tuple[str, str]]  # (영역, 대상, 동작, 한정어)
QUALIFIERS = [("", ""), ("지난 주의 ", "last week's "), ("여러 개의 ", "multiple "), ("팀 공용 ", "team-wide "), ("비공개 ", "private ")]


@dataclass(frozen=True)
class Item:
    name: str
    kind: str  # "skill" | "tool"
    domain: str
    good_description: str
    vague_description: str
    triggers: tuple[str, ...]


@dataclass(frozen=True)
class Query:
    text: str
    target: str  # item name
    kind: str  # "skill" | "tool"
    style: str  # exact | synonym | cross-lang | task


def _slug(*parts: str) -> str:
    return sha1("|".join(parts).encode()).hexdigest()[:8]  # noqa: S324 — 이름 재료일 뿐


def make_items(n: int, seed: int = 7) -> list[Item]:
    """도메인 × 대상 × 동작 × 한정어를 결정적으로 돌며 n개. 짝수는 스킬, 홀수는 도구."""
    rng = random.Random(seed)
    combos: list[Combo] = []
    for domain, spec in DOMAINS.items():
        for obj in spec["objects"]:
            for act in spec["actions"]:
                for q in QUALIFIERS:
                    combos.append((domain, obj, act, q))
    rng.shuffle(combos)
    items: list[Item] = []
    for i, (domain, (ko, en, _), (ako, aen, _), (qko, qen)) in enumerate(combos[:n]):
        kind = "skill" if i % 2 == 0 else "tool"
        name = f"{domain}-{_slug(ko, ako, qko)}"
        trig1, trig2 = f"{qko}{ko} {ako[:-1] if ako.endswith('다') else ako}줘", f"{qen}{en} {aen}"
        if kind == "skill":
            good = f"{qko}{domain} {ko}을(를) {ako}. 사용자가 \"{trig1}\", \"{ko} {aen}\"이라고 할 때 쓴다. 다른 서비스의 {ko}은 이 스킬이 아니다."
        else:
            good = f"{qen}{en} of {domain}: {aen}. Input: identifiers of the {en}; output: the result as JSON. Not for other services' {en}."
        vague = f"{domain} 관련 도움을 준다." if kind == "skill" else f"Helps with {domain}."
        items.append(Item(name, kind, domain, good, vague, (trig1, trig2)))
    return items


def make_queries(items: list[Item], per_item: int = 4, seed: int = 11) -> list[Query]:
    """항목마다 네 가지 말: 설명의 언어로 발동 낱말 그대로 / 동의어로 / 다른 언어로 / 과제 문장(kata)."""
    rng = random.Random(seed)
    by_name: dict[str, Combo] = {}
    for domain, spec in DOMAINS.items():
        for obj in spec["objects"]:
            for act in spec["actions"]:
                for qko, qen in QUALIFIERS:
                    by_name[f"{domain}-{_slug(obj[0], act[0], qko)}"] = (domain, obj, act, (qko, qen))
    out: list[Query] = []
    for it in items:
        domain, (ko, en, ko_syn), (ako, aen, a_syn), (qko, qen) = by_name[it.name]
        # 설명의 언어로 쓴 것이 exact, 다른 언어로 쓴 것이 cross-lang(스킬 설명은 한국어, 도구 설명은 영어 — 실제 팀 카탈로그의 혼용을 흉내낸다)
        ko_exact = it.triggers[0]
        exact, cross = (ko_exact, f"{qen}{en} {aen} {domain}") if it.kind == "skill" else (f"{qen}{en} {aen} {domain}", ko_exact)
        synonym = f"{qko}{rng.choice(ko_syn)} {rng.choice(a_syn)}" if it.kind == "skill" else f"{qen}{rng.choice(ko_syn)} {aen}"
        task = f"{domain}의 {qko}{ko}을 {ako} 작업을 이 저장소에서 수행하라"
        for style, text in (("exact", exact), ("synonym", synonym), ("cross-lang", cross), ("task", task))[:per_item]:
            out.append(Query(text, it.name, it.kind, style))
    return out


def snapshot(items: list[Item], *, vague: bool = False, commit: str = "c" * 40) -> IndexSnapshot:
    now = datetime.now(UTC)
    skills = tuple(SkillEntry(it.name, it.vague_description if vague else it.good_description, None, {}, _slug(it.name).ljust(40, "0"), commit) for it in items if it.kind == "skill")
    tools = tuple(ToolEntry(it.name, it.vague_description if vague else it.good_description, "script", None, {}, _slug(it.name).ljust(40, "1"), commit) for it in items if it.kind == "tool")
    return IndexSnapshot(skills, commit, now, now, tools=tools)
