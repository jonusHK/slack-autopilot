#!/usr/bin/env python3
"""검출 — ▶️ 있고 💬 없는 작업 노드을 찾는다 (engine.md §2).

**부모 메시지와 스레드 답글을 구분하지 않는다**(D-006) — ❓ 로 보류된 항목에 사람이 답글로
결정을 적고 ▶️ 를 달면 그 답글이 새 지시가 되기 때문이다.

출력: JSON 배열(stdout). 유휴면 `[]` — 호출부는 이걸 보고 즉시 종료해야 한다(토큰 낭비 금지).

사용:
  SLACK_BOT_TOKEN=… python3 bin/detect.py --channel "$SLACK_CHANNEL_ID_SAI" [--days 7]
"""

import argparse
import json
import sys
import time

import emoji
import slack_api as slack


def _node(msg, channel, kind, parent_ts=None):
    return {
        "kind": kind,                       # "message" | "reply"
        "channel": channel,
        "ts": msg["ts"],
        "parent_ts": parent_ts,
        "user": msg.get("user"),
        "text": msg.get("text", ""),
        "reactions": sorted(slack.reactions_of(msg)),
        "permalink_hint": f"{channel}/p{msg['ts'].replace('.', '')}",
    }


def detect(channel, days):
    oldest = time.time() - days * 86400
    found = []

    for msg in slack.history(channel, oldest=f"{oldest:.6f}"):
        if msg.get("subtype") in {"channel_join", "channel_leave"}:
            continue

        rx = slack.reactions_of(msg)
        if emoji.TRIGGER in rx and emoji.CLAIM not in rx:
            found.append(_node(msg, channel, "message"))

        # 스레드가 있으면 답글도 같은 규칙으로 본다(D-006).
        thread_ts = msg.get("thread_ts") or (msg["ts"] if msg.get("reply_count") else None)
        if not thread_ts:
            continue
        for reply in slack.replies(channel, thread_ts):
            if reply["ts"] == thread_ts:
                continue                     # 부모는 위에서 이미 판정
            rrx = slack.reactions_of(reply)
            if emoji.TRIGGER in rrx and emoji.CLAIM not in rrx:
                found.append(_node(reply, channel, "reply", parent_ts=thread_ts))

    # 오래된 것부터 — 같은 스레드에서 지시 순서가 뒤집히지 않게.
    found.sort(key=lambda n: float(n["ts"]))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    try:
        nodes = detect(args.channel, args.days)
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
