#!/usr/bin/env python3
"""프롬프트 규칙 테스트 — VM 에서만 드러나는 함정을 커밋 시점에 잡는다.

2026-08-14 에 같은 종류로 두 번 죽었다. 둘 다 **로컬에서는 통과하고 VM 에서만 깨지는** 것이라
사람 눈으로는 안 걸렸다:

1. `cd … && set -a && . ./.env && set +a` — VM 에는 `.env` 가 없어 && 체인이 거기서 끊긴다.
   로컬에는 파일이 있으니 테스트가 통과한다.
2. `git clone https://github.com/...` — VM 에 GitHub 자격이 없어 프라이빗 레포에서 죽는다
   (`could not read Username`). 로컬에는 자격이 있으니 역시 통과한다.

그래서 **로컬에서 되는 것이 VM 에서 된다고 가정하지 않는다**를 기계로 강제한다.
실행: python3 tests/test_prompts.py
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = sorted((ROOT / "prompts").glob("*.md"))


def command_lines(path):
    """실행되는 줄만 돌려준다 — 코드 펜스 안, 또는 명령으로 시작하는 줄.

    산문에서 "이렇게 쓰지 말라"고 **인용한** 예시까지 잡으면 문서를 못 쓴다.
    """
    inside = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside and not line.lstrip().startswith("#"):
            yield i, line          # 주석은 설명이지 실행이 아니다


class PromptRules(unittest.TestCase):

    def setUp(self):
        self.assertTrue(PROMPTS, "prompts/*.md 를 하나도 못 찾았다")

    def test_깃허브_클론은_gh_로만_한다(self):
        """VM 에 GitHub 자격이 없다 — 프록시 경로를 타는 것은 `gh` 뿐이다.

        맨 `git clone https://github.com/...` 은 프라이빗 레포에서
        `fatal: could not read Username` 으로 죽는다.
        """
        bad = re.compile(r"git\s+clone\s+https://github\.com")
        for p in PROMPTS:
            for i, line in command_lines(p):
                if bad.search(line) and "쓰지 않는다" not in line:
                    self.fail(f"{p.name}:{i} — git clone 대신 `gh repo clone` 을 쓸 것\n  {line.strip()}")

    def test_env_파일을_필수로_읽지_않는다(self):
        """VM 에는 `.env` 가 없다(gitignore, 값은 환경에서 온다).

        `&&` 체인 안에서 소싱하면 파일이 없을 때 **그 뒤가 통째로 안 돈다**.
        존재 확인으로 감싸고 실패를 흡수해야 한다.
        """
        for p in PROMPTS:
            for i, line in command_lines(p):
                if ". ./.env" not in line:
                    continue
                self.assertIn("[ -f .env ]", line,
                              f"{p.name}:{i} — .env 소싱은 존재 확인으로 감쌀 것\n  {line.strip()}")
                self.assertIn("|| true", line,
                              f"{p.name}:{i} — 파일이 없을 때 실패로 취급되지 않게 `|| true`\n  {line.strip()}")

    def test_부트스트랩은_실패를_알리게_되어_있다(self):
        """레포를 못 받으면 명세도 못 읽는다 — 그때 침묵하면 원인을 볼 눈이 없다.

        오늘 그 침묵으로 여러 라운드를 태웠다. 부트스트랩만은 레포에 의존하지 않는 경로로
        알려야 한다(curl).
        """
        boot = (ROOT / "prompts" / "bootstrap.md").read_text(encoding="utf-8")
        self.assertIn("chat.postMessage", boot, "클론 실패를 알릴 경로가 없다")
        self.assertIn("에러의 첫 줄", boot, "실패 메시지에 원문 에러를 넣으라는 지시가 없다")

    def test_토큰을_출력하지_말라는_지시가_있다(self):
        joined = "\n".join(p.read_text(encoding="utf-8") for p in PROMPTS)
        self.assertIn("토큰 값", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
