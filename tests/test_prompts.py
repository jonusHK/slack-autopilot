#!/usr/bin/env python3
"""프롬프트 규칙 테스트 — VM 에서만 드러나는 함정을 커밋 시점에 잡는다.

2026-08-14 에 같은 종류로 두 번 죽었다. 둘 다 **로컬에서는 통과하고 VM 에서만 깨지는** 것이라
사람 눈으로는 안 걸렸다:

1. `cd … && set -a && . ./.env && set +a` — VM 에는 `.env` 가 없어 && 체인이 거기서 끊긴다.
   로컬에는 파일이 있으니 테스트가 통과한다.
2. `git clone https://github.com/...` — VM 에 GitHub 자격이 없어 프라이빗 레포에서 죽는다
   (`could not read Username`). 로컬에는 자격이 있으니 역시 통과한다. (엔진이 퍼블릭이 된 뒤
   이 검사는 D-014 의 "클론 줄은 허용 규칙과 글자까지 같다"로 바뀌었다.)
3. `python3 bin/detect.py` / `cd ~/slack-autopilot && …` — 로컬에선 그냥 돌지만 VM 의 auto mode
   분류기가 **실행마다 다르게** 거부한다(2026-09-18). 허용 규칙과 글자 단위로 맞는 형태만 허용.

그래서 **로컬에서 되는 것이 VM 에서 된다고 가정하지 않는다**를 기계로 강제한다.
실행: python3 tests/test_prompts.py
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = sorted((ROOT / "prompts").glob("*.md"))
BOOTSTRAP = ROOT / "prompts" / "bootstrap.md"
# 루틴 allowed_tools 정본 — 프롬프트의 명령은 이 규칙과 글자까지 같아야 한다(D-014).
RULES = set(json.loads((ROOT / "prompts" / "allowed_tools.json").read_text(encoding="utf-8"))["allowed_tools"])


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

    def test_엔진_클론은_허용_규칙과_글자까지_같다(self):
        """루틴 세션은 auto mode 분류기 아래서 돈다(D-014).

        엔진 클론은 분류기에 `[Untrusted Code Integration]` 으로 **실행마다 다르게** 거부됐다.
        허용 규칙은 분류기보다 먼저 결정적으로 판정되지만 명령과 **글자 단위로** 맞아야 한다.
        그래서 부트스트랩의 클론 줄은 `allowed_tools.json` 의 규칙과 정확히 같아야 하고,
        규칙은 변수를 펼치지 않으므로 `$ENGINE_REPO_URL` 같은 변수를 쓸 수 없다.
        """
        clone_lines = [line.strip() for _, line in command_lines(BOOTSTRAP) if "git clone" in line]
        self.assertEqual(len(clone_lines), 1, "부트스트랩의 클론 명령은 정확히 한 줄이어야 한다")
        self.assertNotIn("$", clone_lines[0], "클론 명령에 변수를 쓰면 허용 규칙과 맞지 않는다")
        rm, clone = [s.strip() for s in clone_lines[0].split("&&")]
        self.assertIn(f"Bash({rm})", RULES, f"rm 규칙이 allowed_tools.json 에 없다: {rm}")
        self.assertIn(f"Bash({clone})", RULES, f"클론 규칙이 allowed_tools.json 에 없다: {clone}")

    def test_엔진_스크립트는_규칙이_맞는_형태로만_부른다(self):
        """`python3 bin/x.py` 도 `cd ~/slack-autopilot && bin/x.py` 도 안 된다.

        - auto mode 는 인터프리터로 시작하는 와일드카드 규칙(`Bash(python*)`)을 버린다.
        - `cd` 는 작업 디렉터리 밖이라 그 자체가 분류 대상이고, 셸 cwd 는 호출마다 리셋된다.
        그래서 `~/slack-autopilot/bin/<이름>.py …` 절대 경로 + 실행 비트로만 부르고, 그 이름마다
        `Bash(~/slack-autopilot/bin/<이름>.py *)` 규칙이 있어야 한다.
        """
        script = re.compile(r"(?:python3\s+)?(?:~/slack-autopilot/)?bin/([a-z_]+\.py)")
        for p in PROMPTS:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for m in script.finditer(line):
                    call = m.group(0)
                    name = m.group(1)
                    if call.startswith("python3"):
                        self.fail(f"{p.name}:{i} — 인터프리터 없이 `~/slack-autopilot/bin/{name}` 로 부를 것\n  {line.strip()}")
                    if not call.startswith("~/slack-autopilot/"):
                        # 산문에서 파일 이름으로 언급하는 것(`bin/mark.py` 가 막는다)은 허용 —
                        # 명령으로 보이는 것(인자·옵션이 뒤따르는 것)만 잡는다.
                        rest = line[m.end():]
                        if rest.startswith(" --") or rest.startswith(" pr-") or rest.startswith(" checks"):
                            self.fail(f"{p.name}:{i} — 절대 경로 `~/slack-autopilot/bin/{name}` 로 부를 것\n  {line.strip()}")
                        continue
                    exact, prefix = f"Bash(~/slack-autopilot/bin/{name})", f"Bash(~/slack-autopilot/bin/{name} *)"
                    self.assertTrue(exact in RULES or prefix in RULES,
                                    f"{p.name}:{i} — allowed_tools.json 에 {name} 규칙이 없다")
                    self.assertTrue(os.access(ROOT / "bin" / name, os.X_OK),
                                    f"bin/{name} 에 실행 비트가 없다 — 인터프리터 없이 못 부른다 (chmod +x)")
                    self.assertTrue((ROOT / "bin" / name).read_text(encoding="utf-8").startswith("#!/usr/bin/env python3"),
                                    f"bin/{name} 에 python3 셔뱅이 없다")

    def test_스크립트_호출_앞에_cd_를_두지_않는다(self):
        """`cd ~/slack-autopilot && …` 는 cd 세그먼트가 분류기로 간다 — 규칙이 무력해진다."""
        for p in PROMPTS:
            for i, line in command_lines(p):
                self.assertNotRegex(line, r"^\s*cd\s+~/slack-autopilot",
                                    f"{p.name}:{i} — cd 대신 절대 경로로 부를 것\n  {line.strip()}")

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
