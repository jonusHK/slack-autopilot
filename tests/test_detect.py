#!/usr/bin/env python3
"""검출 규칙 테스트 — 슬랙을 부르지 않는다(픽스처 주입).

실 채널로는 "▶️ 가 없어서 0건"만 확인된다. 규칙이 맞는지는 여기서 본다.
실행: python3 tests/test_detect.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import detect            # noqa: E402
import emoji             # noqa: E402
import slack_api as slack  # noqa: E402

CH = "C_TEST"


def msg(ts, text, reactions=(), **extra):
    m = {"ts": ts, "text": text, "user": "U1",
         "reactions": [{"name": r} for r in reactions]}
    m.update(extra)
    return m


class Fake:
    """slack_api.history/replies 를 대체한다."""

    def __init__(self, messages, thread_map=None):
        self.messages = messages
        self.thread_map = thread_map or {}

    def install(self):
        slack.history = lambda channel, oldest=None, limit=200: self.messages
        slack.replies = lambda channel, thread_ts, limit=200: self.thread_map.get(thread_ts, [])


class DetectRules(unittest.TestCase):

    def test_트리거만_있는_메시지가_잡힌다(self):
        Fake([msg("100.1", "고쳐줘", [emoji.TRIGGER])]).install()
        nodes = detect.detect(CH, 7)
        self.assertEqual([n["ts"] for n in nodes], ["100.1"])
        self.assertEqual(nodes[0]["kind"], "message")

    def test_클레임된_메시지는_제외된다(self):
        Fake([msg("100.1", "고쳐줘", [emoji.TRIGGER, emoji.CLAIM])]).install()
        self.assertEqual(detect.detect(CH, 7), [])

    def test_트리거_없으면_잡히지_않는다(self):
        Fake([msg("100.1", "그냥 메모", []),
              msg("100.2", "질문", [emoji.NEEDS_DECISION])]).install()
        self.assertEqual(detect.detect(CH, 7), [])

    def test_스레드_답글도_같은_규칙으로_잡힌다(self):
        """D-006 — ❓ 로 보류된 항목에 사람이 결정을 답글로 적고 ▶️ 를 다는 경로."""
        parent = msg("100.1", "QA 목록", [emoji.NEEDS_DECISION], reply_count=2)
        Fake([parent], {"100.1": [
            parent,
            msg("100.2", "봇: 판단 지점 A/B", []),
            msg("100.3", "A 로 가자", [emoji.TRIGGER]),
        ]}).install()
        nodes = detect.detect(CH, 7)
        self.assertEqual([n["ts"] for n in nodes], ["100.3"])
        self.assertEqual(nodes[0]["kind"], "reply")
        self.assertEqual(nodes[0]["parent_ts"], "100.1")

    def test_부모와_답글이_동시에_잡힐_수_있다(self):
        parent = msg("100.1", "QA 목록", [emoji.TRIGGER], reply_count=1)
        Fake([parent], {"100.1": [parent, msg("100.5", "추가 지시", [emoji.TRIGGER])]}).install()
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7)], ["100.1", "100.5"])

    def test_오래된_것부터_정렬된다(self):
        """같은 스레드의 지시 순서가 뒤집히면 나중 결정이 먼저 반영된다."""
        Fake([msg("300.0", "세번째", [emoji.TRIGGER]),
              msg("100.0", "첫번째", [emoji.TRIGGER]),
              msg("200.0", "두번째", [emoji.TRIGGER])]).install()
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7)],
                         ["100.0", "200.0", "300.0"])

    def test_입퇴장_시스템메시지는_무시된다(self):
        Fake([msg("100.1", "님이 채널에 참여함", [emoji.TRIGGER], subtype="channel_join")]).install()
        self.assertEqual(detect.detect(CH, 7), [])


class EmojiGuard(unittest.TestCase):

    def test_봇은_사람_전용_이모지를_붙일_수_없다(self):
        """D-002 — 이 가드가 무한 루프를 막는 유일한 장치다."""
        for name in (emoji.TRIGGER, emoji.MERGE):
            with self.assertRaises(RuntimeError):
                emoji.assert_bot_may_add(name)

    def test_봇_이모지는_통과한다(self):
        for name in (emoji.CLAIM, emoji.PR_OPEN, emoji.NEEDS_DECISION,
                     emoji.DONE, emoji.FAILED):
            emoji.assert_bot_may_add(name)

    def test_정의되지_않은_이모지는_거부된다(self):
        with self.assertRaises(RuntimeError):
            emoji.assert_bot_may_add("eyes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
