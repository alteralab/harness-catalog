---
title: 올리는 절차
description: 브랜치, 검사, evals, PR, 병합, 색인까지 아홉 단계.
audience: 스킬 저자
---

# 올리는 절차

쓴 스킬을 브랜치에 담아 PR로 올리고, 레지스트리가 색인할 때까지의 차례입니다. 스킬 내용은 [스킬의 모양과 팀 규약](skill.md)이 먼저입니다.

1. [`search_skills`](../using/find.md)로 같은 일을 하는 스킬이 없는지 봅니다. 있으면 새로 만들지 말고 고칩니다([lifecycle.md](lifecycle.md)).
2. `main`을 최신으로 하고 브랜치를 땁니다. `git switch -c skill/<name>`.
3. `skills/<name>/`을 [스킬의 모양](skill.md)대로 씁니다.
4. `pre-commit install`을 한 번 해 둡니다. 커밋마다 `harness-catalog check --rev INDEX`가 돕니다. 직접 돌리려면 `hc check . --rev HEAD`.
5. evals를 스킬 있이·없이 두 번 돌립니다([evals.md](evals.md)).
6. 커밋하고 PR을 엽니다. 본문에 Langfuse run 링크를 적습니다.
7. CI의 `check`가 초록인지 봅니다. 붉으면 [checks.md](checks.md)대로 고칩니다.
8. 병합은 사람이 git 호스트에서 합니다. 병합한 사람이 이 판의 인증자입니다.
9. 레지스트리가 한 주기(기본 60초) 안에 받아 색인합니다. `search_skills(<이름>)`에 나타나면 끝입니다.

`main`에 직접 push하거나 강제 push하지 않습니다. 브랜치 보호는 걸려 있지 않고 규율입니다.
