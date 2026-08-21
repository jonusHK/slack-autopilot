#!/usr/bin/env python3
"""검출 — 상태별로 다음 손이 필요한 노드를 찾는다 (engine.md §2).

두 모드가 같은 코드를 쓴다. 규칙이 하나여야 상태 기계가 갈라지지 않는다.

  triage  ▶️ 있고 💬 없음  — 새 지시(사람의 입구)
  merge   🚀 있고 ✅ 없음  — 병합 지시(사람의 두 번째이자 마지막 입구)

**부모 메시지와 스레드 답글을 구분하지 않는다**(D-006) — ❓ 로 보류된 항목에 사람이 답글로
결정을 적고 ▶️ 를 달면 그 답글이 새 지시가 되고, 🚀 는 PR 링크가 담긴 **봇 답글**에 붙는다.

출력: JSON 배열(stdout). 유휴면 `[]` — 호출부는 이걸 보고 즉시 종료해야 한다(토큰 낭비 금지).

사용:
  SLACK_BOT_TOKEN=… python3 bin/detect.py --channel "$SLACK_CHANNEL_ID" [--mode triage] [--days 14]

창은 **하나**다(기본 14일). 스캔 범위와 판정 기준을 가르지 않는다 — 갈랐더니 "오래된 메시지
자체에 오늘 ▶️ 를 달면 안 잡힌다"는 사각지대가 생겼고, 증상이 침묵이라 보이지도 않았다.
슬랙 API 는 **이모지를 언제 달았는지 알려주지 않으므로** 메시지 나이로 근사할 수밖에 없는데,
그 근사가 틀리는 쪽을 줄이는 편이 낫다. 중복 처리는 신선도가 아니라 💬 클레임이 막는다.
"""

import argparse
import json
import sys
import time

import emoji
import projects
import slack_api as slack

# (있어야 하는 것, 하나라도 있으면 제외할 것들)
#
# triage 가 💬 만 보면 **끝난 일을 다시 집는다** — ✅(완료)·❌(실패)가 붙었는데 어떤 이유로든
# 💬 가 없는 노드가 그렇다(사람이 떼거나, 클레임 전에 상태가 바뀐 경우). 종료 상태는 전부
# 제외해야 "다음 손이 필요한 것"이라는 정의가 성립한다.
MODES = {
    "triage": (emoji.TRIGGER, (emoji.CLAIM, emoji.DONE, emoji.FAILED)),
    # merge 도 ❌ 를 종료로 본다. 한때 ✅ 만 봤는데, 그러면 **사람이 접을 방법이 없다** —
    # "이 건은 안 하겠다"고 ❌ 를 붙여도 매 실행 다시 잡혀 같은 안내가 반복됐다(실제로
    # 닷새간 다섯 번). 🚀 를 떼는 것이 유일한 출구였고 그건 아무도 모른다.
    "merge": (emoji.MERGE, (emoji.DONE, emoji.FAILED)),
}


def _node(msg, channel, kind, parent_ts=None, project=None, repo=None):
    return {
        "kind": kind,                       # "message" | "reply"
        "project": project,                 # 어느 프로젝트의 노드인가(순회 모드에서만)
        "repo": repo,                       # 그 프로젝트의 대상 레포
        "channel": channel,
        "ts": msg["ts"],
        "parent_ts": parent_ts,
        "user": msg.get("user"),
        "is_bot": bool(msg.get("bot_id")),
        "text": msg.get("text", ""),
        "reactions": sorted(slack.reactions_of(msg)),
        "permalink_hint": f"{channel}/p{msg['ts'].replace('.', '')}",
    }


def detect(channel, days, mode="triage", allow_users=None, project=None, repo=None):
    """최근 `days` 안의 노드 중 다음 손이 필요한 것을 찾는다.

    **창은 하나다.** 스캔 범위와 판정 기준을 가르면 "오래된 메시지 자체에 오늘 ▶️" 가 조용히
    누락된다(실제로 겪었다). 부모가 오래된 스레드의 **새 답글**은 답글 자신이 창 안이므로 잡힌다.
    """
    require, excludes = MODES[mode]
    if not allow_users:
        # **허용 목록이 없으면 아무것도 집지 않는다** — 빠뜨렸을 때 꺼지는 쪽이 맞다.
        # "목록이 없으면 전부 허용"으로 뒤집으면, 변수 하나를 빠뜨린 것이 곧 아무나
        # 봇에게 코드를 쓰게 만드는 문이 된다.
        raise ValueError("허용 사용자 목록이 비어 있다 — --allow-users 를 넘겨라")
    allow_users = set(allow_users)
    now = time.time()
    cutoff = now - days * 86400
    found = []

    def take(msg, kind, parent_ts=None):
        if float(msg["ts"]) < cutoff:
            return                           # 창 밖
        rx = slack.reactions_of(msg)
        if not (require in rx and not (rx & set(excludes))):
            return
        # **사람 전용 이모지는 누가 붙였는지가 곧 권한이다.** 이름만 맞아도, 허용 목록
        # 밖의 사람이 붙인 것이면 없는 것으로 본다(채널 멤버 누구나 봇을 부리는 것을 막는다).
        if not (slack.reactors_of(msg).get(require, set()) & allow_users):
            return
        found.append(_node(msg, channel, kind, parent_ts))

    for msg in slack.history(channel, oldest=f"{cutoff:.6f}"):
        if msg.get("subtype") in {"channel_join", "channel_leave"}:
            continue
        take(msg, "message")

        # 스레드가 있으면 답글도 같은 규칙으로 본다(D-006).
        thread_ts = msg.get("thread_ts") or (msg["ts"] if msg.get("reply_count") else None)
        if not thread_ts:
            continue
        # 창 안에 답글이 하나도 없는 스레드는 열지 않는다(불필요한 replies 호출 회피).
        latest = msg.get("latest_reply")
        if latest and float(latest) < cutoff:
            continue
        for reply in slack.replies(channel, thread_ts):
            if reply["ts"] == thread_ts:
                continue                     # 부모는 위에서 이미 판정
            take(reply, "reply", parent_ts=thread_ts)

    # 오래된 것부터 — 같은 스레드에서 지시 순서가 뒤집히지 않게.
    found.sort(key=lambda n: float(n["ts"]))
    return found


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--channel", help="단일 채널(디버깅·단일 프로젝트 설치)")
    src.add_argument("--all-projects", action="store_true",
                     help="선언된 전 프로젝트를 순회한다(AUTOPILOT_PROJECTS). "
                          "루틴은 이 모드를 쓴다 — 프로젝트마다 트리거를 새로 만들지 않는다")
    ap.add_argument("--mode", choices=sorted(MODES), default="triage")
    ap.add_argument("--days", type=int, default=14,
                    help="검출 창(기본 14일). 스캔·판정 공용 — 가르면 사각지대가 생긴다")
    ap.add_argument("--allow-users",
                    help="▶️·🚀 를 붙일 수 있는 슬랙 사용자 ID(쉼표 구분). "
                         "--channel 과 함께 쓸 때 **필수**다(조용히 전부 허용되지 않게). "
                         "--all-projects 에서는 프로젝트 선언에서 읽는다")
    args = ap.parse_args()

    try:
        if args.all_projects:
            nodes = []
            for p in projects.load():
                nodes += detect(p["channel"], args.days, args.mode,
                                p["allow_users"], p["name"], p["repo"])
            nodes.sort(key=lambda n: float(n["ts"]))   # 프로젝트를 섞어도 오래된 것부터
        else:
            if not args.allow_users:
                ap.error("--channel 을 쓸 때는 --allow-users 도 필요하다")
            allow = {u.strip() for u in args.allow_users.split(",") if u.strip()}
            nodes = detect(args.channel, args.days, args.mode, allow)
    except ValueError as e:
        print(f"검출 실패: {e}", file=sys.stderr)
        return 2
    except slack.SlackError as e:
        print(f"검출 실패: {e}", file=sys.stderr)
        if e.error == "not_in_channel":
            print("  → 봇이 채널에 없다. setup.md §1.5(/invite 아님 — '에이전트 및 앱 추가').",
                  file=sys.stderr)
        return 2

    json.dump(nodes, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
