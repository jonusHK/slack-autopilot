#!/usr/bin/env python3
"""프로젝트 목록 — 어느 채널이 어느 레포에 대응하는가.

**엔진 레포에는 프로젝트 이름을 두지 않는다**(D-001 ④). 그래서 목록도 파일이 아니라
환경변수가 선언한다. 한때 `config.json` 에 `projects` 배열이 있었지만 **읽는 코드가
하나도 없었고**, 그 사이 트리거 프롬프트에 프로젝트별 변수명이 하드코딩됐다 —
설정 파일이 있다는 사실이 오히려 "순회가 구현돼 있다"는 착각을 만들었다(D-011).

선언 방법 — 접미사 목록 하나다.

    AUTOPILOT_PROJECTS=SAI,SHOP

접미사마다 아래 이름으로 값을 찾는다.

    SLACK_CHANNEL_ID_{S}    (필수)
    TARGET_REPO_{S}         (필수)
    SLACK_HUMAN_USERS_{S}   (없으면 전역 SLACK_HUMAN_USERS)

`AUTOPILOT_PROJECTS` 가 없으면 접미사 없는 단일 프로젝트(`SLACK_CHANNEL_ID` ·
`TARGET_REPO`)로 본다 — 프로젝트 하나만 붙인 설치가 그대로 돌아가게.
"""

import os

GLOBAL_USERS = "SLACK_HUMAN_USERS"


def _need(name):
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"환경변수 {name} 이 비어 있습니다 — 프로젝트 선언을 확인하세요.")
    return v


def _users(suffix):
    """허용 사용자. 프로젝트별 목록이 있으면 그것, 없으면 전역.

    **비어 있으면 터진다.** 목록이 없을 때 "전부 허용"으로 뒤집히면 변수 하나를
    빠뜨린 것이 곧 아무나 봇을 부리는 문이 된다(D-010).
    """
    per = f"{GLOBAL_USERS}_{suffix}" if suffix else None
    raw = (os.environ.get(per) if per else None) or os.environ.get(GLOBAL_USERS) or ""
    users = {u.strip() for u in raw.split(",") if u.strip()}
    if not users:
        want = f"{per} 또는 {GLOBAL_USERS}" if per else GLOBAL_USERS
        raise SystemExit(f"허용 사용자 목록이 비어 있습니다 — {want} 를 설정하세요.")
    return users


def load():
    """[{name, channel, repo, allow_users}] — 선언 순서대로."""
    raw = (os.environ.get("AUTOPILOT_PROJECTS") or "").strip()
    suffixes = [s.strip() for s in raw.split(",") if s.strip()] or [""]

    out = []
    for s in suffixes:
        tail = f"_{s}" if s else ""
        out.append({
            "name": s.lower() or "main",
            "channel": _need(f"SLACK_CHANNEL_ID{tail}"),
            "repo": _need(f"TARGET_REPO{tail}"),
            "allow_users": _users(s),
        })
    return out


if __name__ == "__main__":
    import json
    import sys

    # 값은 찍지 않는다 — 채널 ID·레포는 식별자다. 무엇이 선언됐는지만 보여준다.
    print(json.dumps([{"name": p["name"], "allow_users": len(p["allow_users"])}
                      for p in load()], ensure_ascii=False), file=sys.stdout)
