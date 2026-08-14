#!/usr/bin/env python3
"""상태 전이 — 노드에 이모지를 붙이고(선택) 스레드에 답글을 단다 (engine.md §1·§3).

클레임(💬)은 `reactions.add` 의 `already_reacted` 를 test-and-set 으로 쓴다 — 두 실행이
겹치면 한쪽만 True 를 받는다. **다만 이건 보조 장치다**: 구현 단계의 진짜 락은 원격 브랜치
push 다(engine.md §3). 분류만 하는 단계에서는 이 정도로 충분하다.

사용:
  python3 bin/mark.py --channel C… --ts 123.456 --emoji speech_balloon \
      [--reply-file body.md] [--thread-ts 123.000]
"""

import argparse
import sys

import emoji
import slack_api as slack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--ts", required=True, help="이모지를 붙일 메시지 ts")
    ap.add_argument("--emoji", required=True, help="emoji.py 의 이름(예: speech_balloon)")
    ap.add_argument("--reply-file", help="스레드에 남길 답글 본문 파일(UTF-8)")
    ap.add_argument("--thread-ts", help="답글을 달 스레드(미지정 시 --ts 를 스레드로)")
    args = ap.parse_args()

    try:
        emoji.assert_bot_may_add(args.emoji)     # D-002 강제
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    try:
        first = slack.add_reaction(args.channel, args.ts, args.emoji)
        if args.reply_file:
            with open(args.reply_file, encoding="utf-8") as f:
                body = f.read().strip()
            if body:
                slack.post(args.channel, body, thread_ts=args.thread_ts or args.ts)
    except slack.SlackError as e:
        print(f"전이 실패: {e}", file=sys.stderr)
        return 2

    # 클레임 경쟁에서 졌으면 호출부가 이 노드를 건너뛰게 한다.
    print("claimed" if first else "already")
    return 0 if first else 1


if __name__ == "__main__":
    sys.exit(main())
