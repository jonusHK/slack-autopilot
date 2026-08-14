#!/usr/bin/env python3
"""검출 — 상태별로 다음 손이 필요한 노드를 찾는다 (engine.md §2).

두 모드가 같은 코드를 쓴다. 규칙이 하나여야 상태 기계가 갈라지지 않는다.

  triage  ▶️ 있고 💬 없음  — 새 지시(사람의 입구)
  merge   🚀 있고 ✅ 없음  — 병합 지시(사람의 두 번째이자 마지막 입구)

**부모 메시지와 스레드 답글을 구분하지 않는다**(D-006) — ❓ 로 보류된 항목에 사람이 답글로
결정을 적고 ▶️ 를 달면 그 답글이 새 지시가 되고, 🚀 는 PR 링크가 담긴 **봇 답글**에 붙는다.

출력: JSON 배열(stdout). 유휴면 `[]` — 호출부는 이걸 보고 즉시 종료해야 한다(토큰 낭비 금지).

사용:
  SLACK_BOT_TOKEN=… python3 bin/detect.py --channel "$SLACK_CHANNEL_ID_SAI" [--mode triage] [--days 7]

신선도(`--days`)는 **노드 자신** 기준이다. 부모가 오래된 스레드라도 오늘 달린 답글은 잡힌다 —
훑는 범위(`--lookback-days`, 기본 days*4)를 따로 두는 이유가 그것이다.
"""

import argparse
import json
import sys
import time

import emoji
import slack_api as slack

# (있어야 하는 것, 없어야 하는 것)
MODES = {
    "triage": (emoji.TRIGGER, emoji.CLAIM),
    "merge": (emoji.MERGE, emoji.DONE),
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


def detect(channel, days, mode="triage", lookback_days=None):
    """최근 `days` 안에 **노드 자신**이 있는 것을 찾는다.

    신선도 판정은 노드 기준이지 부모 기준이 아니다. 종전에는 부모가 창 밖이면 스레드를 아예
    열지 않아서, **오래된 ❓ 스레드에 오늘 결정을 답글로 달아도 영영 안 잡혔다** — 재투입
    루프(D-006)가 그 지점에서 조용히 끊긴다. 그래서 훑는 범위(`lookback_days`)와 노드의
    신선도(`days`)를 가른다.
    """
    require, exclude = MODES[mode]
    now = time.time()
    fresh_after = now - days * 86400
    scan_after = now - (lookback_days or days * 4) * 86400
    found = []

    def take(msg, kind, parent_ts=None):
        if float(msg["ts"]) < fresh_after:
            return                           # 노드 자신이 낡았다
        rx = slack.reactions_of(msg)
        if require in rx and exclude not in rx:
            found.append(_node(msg, channel, kind, parent_ts))

    for msg in slack.history(channel, oldest=f"{scan_after:.6f}"):
        if msg.get("subtype") in {"channel_join", "channel_leave"}:
            continue
        take(msg, "message")

        # 스레드가 있으면 답글도 같은 규칙으로 본다(D-006).
        thread_ts = msg.get("thread_ts") or (msg["ts"] if msg.get("reply_count") else None)
        if not thread_ts:
            continue
        # 최근 답글이 없는 스레드는 열지 않는다 — 훑는 범위를 넓힌 대가를 여기서 돌려받는다.
        latest = msg.get("latest_reply")
        if latest and float(latest) < fresh_after:
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
    ap.add_argument("--days", type=int, default=7,
                    help="노드 자신이 이 기간 안에 있어야 잡는다(신선도)")
    ap.add_argument("--lookback-days", type=int, default=None,
                    help="훑는 범위(기본 days*4). 오래된 스레드의 새 답글을 놓치지 않게 "
                         "부모는 더 멀리까지 본다 — 최근 답글이 없는 스레드는 열지 않는다")
    args = ap.parse_args()

    try:
        nodes = detect(args.channel, args.days, args.mode, args.lookback_days)
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
