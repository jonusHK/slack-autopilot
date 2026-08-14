#!/usr/bin/env python3
"""셋업 실패를 채널에 한 줄 남긴다 — **실패를 보이게 하는 것**이 목적이다.

유휴는 조용해야 하지만(토큰 낭비 금지) **실패까지 조용하면 눈이 없다.** 2026-08-14 에
그 대가를 치렀다: 루틴이 두 번 연속 아무 일도 하지 않았는데, 증상이 "무반응" 하나뿐이라
원인(프롬프트의 `. ./.env` 가 VM 에서 체인을 끊음)을 찾는 데 두 라운드를 썼다.

- 슬랙에 못 닿는 실패는 여기서도 못 알린다(그때는 세션 결과가 유일한 기록이다).
- **스레드가 아니라 채널에** 남긴다. 특정 노드의 문제가 아니라 루틴 자체의 문제이기 때문이다.
- 하루에 같은 사유를 여러 번 떠들지 않게, 호출부가 **실행당 한 번만** 부른다.

사용:
  python3 bin/report_failure.py --channel C… --reason "환경변수 누락: SLACK_CHANNEL_ID"
"""

import argparse
import sys

import slack_api as slack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--reason", required=True, help="한 줄. 값·토큰을 넣지 않는다")
    args = ap.parse_args()

    text = (
        ":warning: 자동화 루틴이 시작하지 못했어요\n"
        f"• {args.reason}\n"
        "고칠 때까지 ▶️ 를 달아도 반응이 없어요."
    )
    try:
        slack.post(args.channel, text)
    except slack.SlackError as e:
        print(f"실패 보고조차 실패: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
