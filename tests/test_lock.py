#!/usr/bin/env python3
"""락 회수 규칙 테스트 — git·gh 를 부르지 않는다(헬퍼 대체).

회수 판정이 틀리면 둘 중 하나가 난다: 살아 있는 작업을 뺏거나(중복 PR), 죽은 락이 노드를
영원히 잠근다(조용한 교착). 실행: python3 tests/test_lock.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import lock  # noqa: E402

REPO, PATH, BRANCH = "o/r", "/tmp/x", "auto/slack-100_1"


class LockCase(unittest.TestCase):
    """회수 판정을 git·네트워크 없이 재기 위한 공통 대체물."""


    def setUp(self):
        self._pr = lock.has_open_pr
        self._age = lock.branch_age_minutes
        self._ahead = lock.commits_ahead

    def tearDown(self):
        lock.has_open_pr = self._pr
        lock.branch_age_minutes = self._age
        lock.commits_ahead = self._ahead

    def fake(self, has_pr, age, ahead=1):
        lock.has_open_pr = lambda repo, branch: has_pr
        lock.branch_age_minutes = lambda path, branch: age
        lock.commits_ahead = lambda path, base, branch: ahead

    def stale(self, *, stale=120, empty=20):
        return lock.is_stale(REPO, PATH, BRANCH, stale, empty)


class StaleRule(LockCase):
    """커밋이 쌓인 브랜치 — 넉넉히 기다린다."""

    def test_PR_이_있으면_아무리_오래돼도_회수하지_않는다(self):
        """PR 을 열었다는 것은 그 실행이 최소한 거기까지 갔다는 뜻이다."""
        self.fake(has_pr=True, age=10_000)
        self.assertFalse(self.stale())

    def test_PR_없고_충분히_오래되면_죽은_락이다(self):
        self.fake(has_pr=False, age=121)
        self.assertTrue(self.stale())

    def test_PR_없어도_아직_이르면_살아있다고_본다(self):
        """자기 수정(최대 60분) 중인 작업을 뺏지 않기 위한 여유."""
        self.fake(has_pr=False, age=59)
        self.assertFalse(self.stale())

    def test_경계값은_회수한다(self):
        self.fake(has_pr=False, age=120)
        self.assertTrue(self.stale())

    def test_PR_조회가_실패하면_회수하지_않고_터진다(self):
        """판단 불가일 때 회수하면 남의 작업을 뺏는다 — 조용히 넘어가면 안 된다."""
        def boom(repo, branch):
            raise RuntimeError("gh 실패")

        lock.has_open_pr = boom
        with self.assertRaises(RuntimeError):
            self.stale()


class EmptyBranchRule(LockCase):
    """커밋이 0건인 빈 브랜치는 짧은 기준으로 본다 — 뺏을 작업이 없다."""

    def test_빈_브랜치는_20분이면_회수한다(self):
        self.fake(has_pr=False, age=21, ahead=0)
        self.assertTrue(self.stale())

    def test_같은_시간이라도_커밋이_있으면_회수하지_않는다(self):
        """21분은 자기 수정 한복판이다 — 일하고 있는 실행을 뺏으면 안 된다."""
        self.fake(has_pr=False, age=21, ahead=3)
        self.assertFalse(self.stale())

    def test_빈_브랜치도_너무_이르면_기다린다(self):
        """막 락을 잡고 클론·정책 읽기 중일 수 있다."""
        self.fake(has_pr=False, age=19, ahead=0)
        self.assertFalse(self.stale())

    def test_빈_브랜치라도_PR_이_있으면_회수하지_않는다(self):
        """빈 브랜치에 PR 이 달릴 일은 드물지만, PR 유무가 언제나 먼저다."""
        self.fake(has_pr=True, age=10_000, ahead=0)
        self.assertFalse(self.stale())


class BranchName(unittest.TestCase):

    def test_같은_노드는_늘_같은_이름이다(self):
        """멱등의 근거 — 재실행이 같은 락 키를 본다."""
        self.assertEqual(lock.branch_name("100.1"), lock.branch_name("100.1"))

    def test_점은_밑줄로_눕힌다(self):
        self.assertEqual(lock.branch_name("1786675913.239919"),
                         "auto/slack-1786675913_239919")


if __name__ == "__main__":
    unittest.main(verbosity=2)
