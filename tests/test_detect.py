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

# 허용된 사람(▶️·🚀 를 붙일 권한이 있는 ID)과 그렇지 않은 사람.
OWNER, STRANGER = "U_OWNER", "U_STRANGER"
ALLOW = {OWNER}

# 검출은 이제 신선도를 보므로 시계를 고정한다. 픽스처의 ts 는 이 값 기준의 초 오프셋이다.
NOW = 1_800_000_000.0


class FakeClock:
    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now


def t(seconds_ago=0):
    """NOW 기준 ts 문자열."""
    return f"{NOW - seconds_ago:.6f}"


class ClockFixed(unittest.TestCase):
    """detect 의 시계를 고정한다 — 실제 시각에 따라 결과가 달라지면 테스트가 아니다."""

    def setUp(self):
        self._time = detect.time
        detect.time = FakeClock(NOW)

    def tearDown(self):
        detect.time = self._time


def msg(ts, text, reactions=(), by=OWNER, **extra):
    """`reactions` 는 이름 목록. 누가 붙였는지는 `by` 로 지정한다(기본은 허용된 사람)."""
    m = {"ts": ts, "text": text, "user": "U1",
         "reactions": [{"name": r, "users": [by]} for r in reactions]}
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


class DetectRules(ClockFixed):

    def test_트리거만_있는_메시지가_잡힌다(self):
        Fake([msg(t(90), "고쳐줘", [emoji.TRIGGER])]).install()
        nodes = detect.detect(CH, 7, allow_users=ALLOW)
        self.assertEqual([n["ts"] for n in nodes], [t(90)])
        self.assertEqual(nodes[0]["kind"], "message")

    def test_클레임된_메시지는_제외된다(self):
        Fake([msg(t(90), "고쳐줘", [emoji.TRIGGER, emoji.CLAIM])]).install()
        self.assertEqual(detect.detect(CH, 7, allow_users=ALLOW), [])

    def test_끝난_노드는_클레임이_없어도_제외된다(self):
        """✅·❌ 는 종료 상태다 — 💬 만 보면 끝난 일을 다시 집는다(실제로 겪었다)."""
        for done in (emoji.DONE, emoji.FAILED):
            Fake([msg(t(90), "이미 끝난 지시", [emoji.TRIGGER, done])]).install()
            self.assertEqual(detect.detect(CH, 7, allow_users=ALLOW), [], f"{done} 가 붙었는데 다시 잡혔다")

    def test_트리거_없으면_잡히지_않는다(self):
        Fake([msg(t(90), "그냥 메모", []),
              msg(t(80), "질문", [emoji.NEEDS_DECISION])]).install()
        self.assertEqual(detect.detect(CH, 7, allow_users=ALLOW), [])

    def test_스레드_답글도_같은_규칙으로_잡힌다(self):
        """D-006 — ❓ 로 보류된 항목에 사람이 결정을 답글로 적고 ▶️ 를 다는 경로."""
        parent = msg(t(90), "QA 목록", [emoji.NEEDS_DECISION], reply_count=2)
        Fake([parent], {t(90): [
            parent,
            msg(t(80), "봇: 판단 지점 A/B", []),
            msg(t(70), "A 로 가자", [emoji.TRIGGER]),
        ]}).install()
        nodes = detect.detect(CH, 7, allow_users=ALLOW)
        self.assertEqual([n["ts"] for n in nodes], [t(70)])
        self.assertEqual(nodes[0]["kind"], "reply")
        self.assertEqual(nodes[0]["parent_ts"], t(90))

    def test_부모와_답글이_동시에_잡힐_수_있다(self):
        parent = msg(t(90), "QA 목록", [emoji.TRIGGER], reply_count=1)
        Fake([parent], {t(90): [parent, msg(t(60), "추가 지시", [emoji.TRIGGER])]}).install()
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7, allow_users=ALLOW)], [t(90), t(60)])

    def test_오래된_것부터_정렬된다(self):
        """같은 스레드의 지시 순서가 뒤집히면 나중 결정이 먼저 반영된다."""
        Fake([msg(t(100), "세번째", [emoji.TRIGGER]),
              msg(t(300), "첫번째", [emoji.TRIGGER]),
              msg(t(200), "두번째", [emoji.TRIGGER])]).install()
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7, allow_users=ALLOW)],
                         [t(300), t(200), t(100)])

    def test_입퇴장_시스템메시지는_무시된다(self):
        Fake([msg(t(90), "님이 채널에 참여함", [emoji.TRIGGER], subtype="channel_join")]).install()
        self.assertEqual(detect.detect(CH, 7, allow_users=ALLOW), [])


class MergeTerminal(ClockFixed):
    """병합 모드의 종료 상태 — 사람이 접을 수 있어야 한다."""

    def test_완료면_다시_잡지_않는다(self):
        Fake([msg(t(60), "PR 링크", [emoji.MERGE, emoji.DONE])]).install()
        self.assertEqual(detect.detect(CH, 7, mode="merge", allow_users=ALLOW), [])

    def test_실패로_접은_것도_다시_잡지_않는다(self):
        """❌ 는 '이 건은 안 한다'는 사람의 의사다 — 무시하면 같은 안내가 반복된다."""
        Fake([msg(t(60), "PR 링크", [emoji.MERGE, emoji.FAILED])]).install()
        self.assertEqual(detect.detect(CH, 7, mode="merge", allow_users=ALLOW), [])

    def test_둘_다_없으면_잡는다(self):
        Fake([msg(t(60), "PR 링크", [emoji.MERGE])]).install()
        self.assertEqual(len(detect.detect(CH, 7, mode="merge", allow_users=ALLOW)), 1)


class ReactorPermission(ClockFixed):
    """▶️·🚀 는 **누가 붙였는지가 곧 권한**이다 — 이름만 맞아도 안 된다."""

    def test_허용된_사람이_붙이면_잡는다(self):
        Fake([msg(t(60), "고쳐줘", [emoji.TRIGGER], by=OWNER)]).install()
        self.assertEqual(len(detect.detect(CH, 7, allow_users=ALLOW)), 1)

    def test_다른_사람이_붙이면_없는_것으로_본다(self):
        """채널 멤버 누구나 봇에게 코드를 쓰게 만들 수 있으면 게이트가 없는 것이다."""
        Fake([msg(t(60), "고쳐줘", [emoji.TRIGGER], by=STRANGER)]).install()
        self.assertEqual(detect.detect(CH, 7, allow_users=ALLOW), [])

    def test_둘_다_붙였으면_잡는다(self):
        """허용된 사람이 붙인 사실은 남의 반응이 섞여도 사라지지 않는다."""
        m = msg(t(60), "고쳐줘", [], by=OWNER)
        m["reactions"] = [{"name": emoji.TRIGGER, "users": [STRANGER, OWNER]}]
        Fake([m]).install()
        self.assertEqual(len(detect.detect(CH, 7, allow_users=ALLOW)), 1)

    def test_병합도_같은_규칙을_받는다(self):
        """🚀 는 되돌리기 어려운 쪽이라 더 중요하다."""
        Fake([msg(t(60), "PR 링크", [emoji.MERGE], by=STRANGER)]).install()
        self.assertEqual(detect.detect(CH, 7, mode="merge", allow_users=ALLOW), [])

    def test_허용_목록이_비면_아무것도_집지_않고_터진다(self):
        """빠뜨렸을 때 '전부 허용'으로 뒤집히면 변수 하나가 문이 된다."""
        Fake([msg(t(60), "고쳐줘", [emoji.TRIGGER], by=OWNER)]).install()
        for empty in (None, set(), ""):
            with self.assertRaises(ValueError):
                detect.detect(CH, 7, allow_users=empty)


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
            emoji.assert_bot_may_add("tada")


class MergeMode(ClockFixed):
    """5단계 검출 — 🚀 있고 ✅ 없는 것(보통 PR 링크가 담긴 봇 답글)."""

    def test_병합_대기_노드가_잡힌다(self):
        parent = msg(t(90), "QA 목록", [emoji.TRIGGER, emoji.CLAIM], reply_count=1)
        Fake([parent], {t(90): [
            parent,
            msg(t(50), "PR 열었어요 https://github.com/o/r/pull/7",
                [emoji.PR_OPEN, emoji.MERGE]),
        ]}).install()
        nodes = detect.detect(CH, 7, mode="merge", allow_users=ALLOW)
        self.assertEqual([n["ts"] for n in nodes], [t(50)])

    def test_이미_병합된_것은_잡히지_않는다(self):
        parent = msg(t(90), "QA", [emoji.CLAIM], reply_count=1)
        Fake([parent], {t(90): [
            parent,
            msg(t(50), "PR", [emoji.PR_OPEN, emoji.MERGE, emoji.DONE]),
        ]}).install()
        self.assertEqual(detect.detect(CH, 7, mode="merge", allow_users=ALLOW), [])

    def test_모드가_서로를_침범하지_않는다(self):
        """▶️ 노드가 병합 검출에 섞이면 코드가 안 된 것을 병합하려 든다."""
        Fake([msg(t(90), "새 지시", [emoji.TRIGGER]),
              msg(t(80), "PR", [emoji.MERGE])]).install()
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7, mode="triage", allow_users=ALLOW)], [t(90)])
        self.assertEqual([n["ts"] for n in detect.detect(CH, 7, mode="merge", allow_users=ALLOW)], [t(80)])


class Freshness(ClockFixed):
    """신선도는 **노드 자신** 기준이다 — 부모 나이로 판정하면 재투입 루프가 끊긴다."""

    def ts(self, days_ago):
        return t(days_ago * 86400)

    def test_창_밖_스레드의_오늘_답글이_잡힌다(self):
        """부모가 창 밖이어도 **답글 자신이 창 안**이면 잡힌다(재투입 루프의 생명선)."""
        old, fresh = self.ts(30), self.ts(0)
        parent = msg(old, "옛 QA", [emoji.NEEDS_DECISION],
                     reply_count=1, latest_reply=fresh)
        Fake([parent], {old: [parent, msg(fresh, "A 로 가자", [emoji.TRIGGER])]}).install()
        nodes = detect.detect(CH, 14, allow_users=ALLOW)
        self.assertEqual([n["ts"] for n in nodes], [fresh])
        self.assertEqual(nodes[0]["parent_ts"], old)

    def test_창_안이면_오래된_메시지에_지금_달아도_잡힌다(self):
        """창을 가르던 시절의 사각지대 — 열흘 전 메시지에 오늘 ▶️ 를 달면 조용히 누락됐다.
        이모지를 언제 달았는지는 API 가 알려주지 않으므로, 창 안이면 잡는 쪽으로 둔다."""
        Fake([msg(self.ts(10), "옛 QA 목록", [emoji.TRIGGER])]).install()
        self.assertEqual(len(detect.detect(CH, 14, allow_users=ALLOW)), 1)

    def test_창_밖_노드는_잡히지_않는다(self):
        Fake([msg(self.ts(30), "아주 옛 지시", [emoji.TRIGGER])]).install()
        self.assertEqual(detect.detect(CH, 14, allow_users=ALLOW), [])

    def test_창_안에_답글이_없는_스레드는_열지_않는다(self):
        """불필요한 replies 호출 회피."""
        old = self.ts(30)
        opened = []

        parent = msg(old, "옛 QA", [], reply_count=1, latest_reply=old)
        f = Fake([parent], {old: [parent, msg(old, "옛 답글", [emoji.TRIGGER])]})
        f.install()
        real = slack.replies
        slack.replies = lambda channel, thread_ts, limit=200: (
            opened.append(thread_ts) or real(channel, thread_ts, limit))

        self.assertEqual(detect.detect(CH, 14, allow_users=ALLOW), [])
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
