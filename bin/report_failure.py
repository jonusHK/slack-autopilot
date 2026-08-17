#!/usr/bin/env python3
"""셋업 실패를 채널에 한 줄 남긴다 — **실패를 보이게 하는 것**이 목적이다.

유휴는 조용해야 하지만(토큰 낭비 금지) **실패까지 조용하면 눈이 없다.** 2026-08-14 에
그 대가를 치렀다: 루틴이 두 번 연속 아무 일도 하지 않았는데, 증상이 "무반응" 하나뿐이라
원인(프롬프트의 `. ./.env` 가 VM 에서 체인을 끊음)을 찾는 데 두 라운드를 썼다.

- 슬랙에 못 닿는 실패는 여기서도 못 알린다(그때는 세션 결과가 유일한 기록이다).
- **스레드가 아니라 채널에** 남긴다. 특정 노드의 문제가 아니라 루틴 자체의 문제이기 때문이다.
- **같은 사유는 창(기본 6시간) 안에서 한 번만 알린다**(§ 중복 억제).

사용:
  python3 bin/report_failure.py --channel C… --reason "환경변수 누락: SLACK_CHANNEL_ID"
"""

import argparse
import sys
import time

import slack_api as slack

# 같은 사유를 다시 알리기까지 기다리는 시간. 20분 주기로 도는 트리거가 셋이라
# 이보다 짧으면 고치는 동안 채널이 같은 말로 덮인다.
DEDUP_HOURS = 6

# 사유를 비교할 때 앞에서 이만큼만 본다. 뒤에 붙는 시각·경로 같은 변동분이
# "다른 실패"로 보이게 만드는 것을 막는다.
COMPARE_CHARS = 60

MARKER = ":warning: 자동화 루틴이 시작하지 못했어요"


def already_reported(channel, reason, hours=DEDUP_HOURS, limit=40):
    """창 안에 같은 사유의 실패 알림이 이미 있는가.

    **모르면 알린다.** 조회에 실패했다고 침묵하면, 하필 슬랙이 흔들릴 때 실패가 통째로
    사라진다. 중복 한 번이 누락 한 번보다 싸다.
    """
    cutoff = time.time() - hours * 3600
    head = reason.strip()[:COMPARE_CHARS]
    try:
        for m in slack.history(channel, oldest=f"{cutoff:.6f}", limit=limit):
            text = m.get("text", "")
            if MARKER in text and head in text:
                return True
    except Exception:
        return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--reason", required=True, help="한 줄. 값·토큰을 넣지 않는다")
    ap.add_argument(
        "--dedup-hours",
        type=float,
        default=DEDUP_HOURS,
        help=f"같은 사유를 다시 알리기까지의 시간(기본 {DEDUP_HOURS}시간). 0 이면 항상 알린다.",
    )
    args = ap.parse_args()

    if args.dedup_hours > 0 and already_reported(args.channel, args.reason, args.dedup_hours):
        # 조용히 넘어가되 흔적은 남긴다 — 세션 로그에서 "왜 안 알렸나"를 볼 수 있어야 한다.
        print(f"같은 사유가 최근 {args.dedup_hours}시간 안에 이미 보고됨 — 생략", file=sys.stderr)
        return 0

    text = (
        f"{MARKER}\n"
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
