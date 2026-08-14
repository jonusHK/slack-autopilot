#!/usr/bin/env python3
"""검출 — 상태별로 다음 손이 필요한 노드를 찾는다 (engine.md §2).

두 모드가 같은 코드를 쓴다. 규칙이 하나여야 상태 기계가 갈라지지 않는다.

  triage  ▶️ 있고 💬 없음  — 새 지시(사람의 입구)
  merge   🚀 있고 ✅ 없음  — 병합 지시(사람의 두 번째이자 마지막 입구)

**부모 메시지와 스레드 답글을 구분하지 않는다**(D-006) — ❓ 로 보류된 항목에 사람이 답글로
결정을 적고 ▶️ 를 달면 그 답글이 새 지시가 되고, 🚀 는 PR 링크가 담긴 **봇 답글**에 붙는다.

출력: JSON 배열(stdout). 유휴면 `[]` — 호출부는 이걸 보고 즉시 종료해야 한다(토큰 낭비 금지).

사용:
  SLACK_BOT_TOKEN=… python3 bin/detect.py --channel "$SLACK_CHANNEL_ID_SAI" [--mode triage] [--days 14]

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
import slack_api as slack

# (있어야 하는 것, 하나라도 있으면 제외할 것들)
#
# triage 가 💬 만 보면 **끝난 일을 다시 집는다** — ✅(완료)·❌(실패)가 붙었는데 어떤 이유로든
# 💬 가 없는 노드가 그렇다(사람이 떼거나, 클레임 전에 상태가 바뀐 경우). 종료 상태는 전부
# 제외해야 "다음 손이 필요한 것"이라는 정의가 성립한다.
MODES = {
    "triage": (emoji.TRIGGER, (emoji.CLAIM, emoji.DONE, emoji.FAILED)),
    "merge": (emoji.MERGE, (emoji.DONE,)),
}


def _node(msg, channel, kind, parent_ts=None):
    return {
        "kind": kind,                       # "message" | "reply"
        "channel": channel,
        "ts": msg["ts"],
        "parent_ts": parent_ts,
        "user": msg.get("user"),
        "is_bot": bool(msg.get("bot_id")),
        "text": msg.get("text", ""),
        "reactions": sorted(slack.reactions_of(msg)),
        "permalink_hint": f"{channel}/p{msg['ts'].replace('.', '')}",
    }


def detect(channel, days, mode="triage"):
    """최근 `days` 안의 노드 중 다음 손이 필요한 것을 찾는다.

    **창은 하나다.** 스캔 범위와 판정 기준을 가르면 "오래된 메시지 자체에 오늘 ▶️" 가 조용히
    누락된다(실제로 겪었다). 부모가 오래된 스레드의 **새 답글**은 답글 자신이 창 안이므로 잡힌다.
    """
    require, excludes = MODES[mode]
    now = time.time()
    cutoff = now - days * 86400
    found = []

    def take(msg, kind, parent_ts=None):
        if float(msg["ts"]) < cutoff:
            return                           # 창 밖
        rx = slack.reactions_of(msg)
        if require in rx and not (rx & set(excludes)):
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
    ap.add_argument("--channel", required=True)
    ap.add_argument("--mode", choices=sorted(MODES), default="triage")
    ap.add_argument("--days", type=int, default=14,
                    help="검출 창(기본 14일). 스캔·판정 공용 — 가르면 사각지대가 생긴다")
    args = ap.parse_args()

    try:
        nodes = detect(args.channel, args.days, args.mode)
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
