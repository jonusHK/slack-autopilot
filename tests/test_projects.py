#!/usr/bin/env python3
"""프로젝트 선언 테스트 — 환경변수만 갈아끼운다(슬랙·git 없음).

선언이 틀렸을 때 **조용히 넘어가는 것**이 가장 위험하다: 엉뚱한 채널을 조회하거나,
허용 목록 없이 전부 허용으로 뒤집히거나, 프로젝트 하나가 빠진 채 돈다.
실행: python3 tests/test_projects.py
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import projects  # noqa: E402

VARS = ["AUTOPILOT_PROJECTS", "SLACK_CHANNEL_ID", "TARGET_REPO",
        "SLACK_HUMAN_USERS", "SLACK_CHANNEL_ID_A", "TARGET_REPO_A",
        "SLACK_HUMAN_USERS_A", "SLACK_CHANNEL_ID_B", "TARGET_REPO_B"]


class Declaration(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in VARS}
        for k in VARS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def env(self, **kw):
        for k, v in kw.items():
            os.environ[k] = v

    def test_선언이_없으면_접미사_없는_단일_프로젝트다(self):
        """프로젝트 하나만 붙인 설치가 그대로 돌아가야 한다."""
        self.env(SLACK_CHANNEL_ID="C1", TARGET_REPO="o/r", SLACK_HUMAN_USERS="U1")
        got = projects.load()
        self.assertEqual([p["name"] for p in got], ["main"])
        self.assertEqual(got[0]["channel"], "C1")
        self.assertEqual(got[0]["allow_users"], {"U1"})

    def test_접미사_목록만큼_순회한다(self):
        self.env(AUTOPILOT_PROJECTS="A,B", SLACK_HUMAN_USERS="U1",
                 SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a",
                 SLACK_CHANNEL_ID_B="CB", TARGET_REPO_B="o/b")
        got = projects.load()
        self.assertEqual([p["name"] for p in got], ["a", "b"])
        self.assertEqual([p["repo"] for p in got], ["o/a", "o/b"])

    def test_선언_순서를_지킨다(self):
        """오래된 것부터 처리하려면 목록 순서가 예측 가능해야 한다."""
        self.env(AUTOPILOT_PROJECTS="B,A", SLACK_HUMAN_USERS="U1",
                 SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a",
                 SLACK_CHANNEL_ID_B="CB", TARGET_REPO_B="o/b")
        self.assertEqual([p["name"] for p in projects.load()], ["b", "a"])

    def test_프로젝트별_허용목록이_전역을_이긴다(self):
        """채널이 다르면 주인이 다를 수 있다."""
        self.env(AUTOPILOT_PROJECTS="A", SLACK_HUMAN_USERS="U_GLOBAL",
                 SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a",
                 SLACK_HUMAN_USERS_A="U_A1,U_A2")
        self.assertEqual(projects.load()[0]["allow_users"], {"U_A1", "U_A2"})

    def test_프로젝트별_목록이_없으면_전역을_쓴다(self):
        self.env(AUTOPILOT_PROJECTS="A", SLACK_HUMAN_USERS="U_GLOBAL",
                 SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a")
        self.assertEqual(projects.load()[0]["allow_users"], {"U_GLOBAL"})

    def test_채널이_비면_터진다(self):
        """빈 값으로 엉뚱한 채널을 조회하는 것보다 안 도는 편이 낫다."""
        self.env(AUTOPILOT_PROJECTS="A", TARGET_REPO_A="o/a", SLACK_HUMAN_USERS="U1")
        with self.assertRaises(SystemExit):
            projects.load()

    def test_레포가_비면_터진다(self):
        self.env(AUTOPILOT_PROJECTS="A", SLACK_CHANNEL_ID_A="CA", SLACK_HUMAN_USERS="U1")
        with self.assertRaises(SystemExit):
            projects.load()

    def test_허용목록이_어느_쪽에도_없으면_터진다(self):
        """전부 허용으로 뒤집히면 변수 하나가 곧 문이 된다(D-010)."""
        self.env(AUTOPILOT_PROJECTS="A", SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a")
        with self.assertRaises(SystemExit):
            projects.load()

    def test_공백만_있는_값은_없는_것으로_본다(self):
        """복붙 사고로 공백이 남는 일이 흔하다 — 통과시키면 빈 채널을 조회한다."""
        self.env(AUTOPILOT_PROJECTS="A", SLACK_CHANNEL_ID_A="   ",
                 TARGET_REPO_A="o/a", SLACK_HUMAN_USERS="U1")
        with self.assertRaises(SystemExit):
            projects.load()

    def test_목록의_빈_항목은_건너뛴다(self):
        """`A,,B` 나 뒤에 붙은 쉼표가 유령 프로젝트를 만들지 않게."""
        self.env(AUTOPILOT_PROJECTS="A,,", SLACK_HUMAN_USERS="U1",
                 SLACK_CHANNEL_ID_A="CA", TARGET_REPO_A="o/a")
        self.assertEqual([p["name"] for p in projects.load()], ["a"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
