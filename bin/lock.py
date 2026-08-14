#!/usr/bin/env python3
"""브랜치 락 — 구현 단계의 **진짜** 클레임 (engine.md §3).

이모지 클레임(💬)은 사람이 보는 표시이고 경쟁에 약하다(reactions.add 는 원자적 test-and-set
이 아니다 — 이미 붙어 있을 때만 거절한다). 구현 단계에서는 두 실행이 같은 노드를 잡으면
**같은 파일을 두 번 고치고 PR 이 둘 난다**. 그래서 락은 원격 브랜치의 **원자적 생성**으로 건다:
`git push` 로 새 ref 를 만드는 것은 서버에서 직렬화되므로 승자가 하나다.

정책(engine.md §3):
- 브랜치 이름은 노드 ts 에서 유도한다 — 같은 노드는 늘 같은 이름이라 재실행이 안전하다.
- **스레드에 미병합 PR 이 있으면 그 브랜치에 얹는다**(작업 파편화 방지). 그때는 새 락을 걸지
  않고 기존 브랜치를 체크아웃한다.

사용:
  python3 bin/lock.py --repo owner/name --ts 1786675913.239919 [--base main] [--work-dir DIR]

출력(stdout, JSON): {"branch": "...", "mode": "created"|"reused", "path": "..."}
종료코드 1 = 다른 실행이 이미 잡았다(건너뛰라는 뜻).
"""

import argparse
import json
import os
import subprocess
import sys

BRANCH_PREFIX = "auto/slack-"


def run(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} → {p.returncode}\n{p.stderr.strip()}")
    return p


def branch_name(ts):
    # ts 의 점은 브랜치 이름에 두어도 되지만, 도구마다 취급이 달라 밑줄로 눕힌다.
    return BRANCH_PREFIX + ts.replace(".", "_")


def ensure_clone(repo, work_dir):
    path = os.path.join(work_dir, repo.split("/")[-1])
    if os.path.isdir(os.path.join(path, ".git")):
        run(["git", "fetch", "--prune", "origin"], cwd=path)
    else:
        os.makedirs(work_dir, exist_ok=True)
        run(["gh", "repo", "clone", repo, path])
    return path


def remote_has(path, branch):
    out = run(["git", "ls-remote", "--heads", "origin", branch], cwd=path).stdout
    return bool(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--ts", required=True, help="노드 ts — 브랜치 이름의 근거")
    ap.add_argument("--base", default="main")
    ap.add_argument("--work-dir", default=os.path.expanduser("~/work"))
    ap.add_argument(
        "--reuse",
        help="스레드에 미병합 PR 이 있을 때 그 브랜치 이름. 새 락을 걸지 않고 여기에 얹는다.",
    )
    args = ap.parse_args()

    try:
        path = ensure_clone(args.repo, args.work_dir)

        if args.reuse:
            run(["git", "checkout", args.reuse], cwd=path)
            run(["git", "pull", "--ff-only", "origin", args.reuse], cwd=path)
            json.dump({"branch": args.reuse, "mode": "reused", "path": path}, sys.stdout)
            print()
            return 0

        branch = branch_name(args.ts)
        if remote_has(path, branch):
            # 이미 누가 잡았다. 재실행이 아니라 경쟁이면 여기서 물러나는 것이 맞다 —
            # 이어서 하려면 --reuse 로 명시해야 한다(의도가 드러나야 한다).
            print(f"이미 잡힌 노드다: {branch}", file=sys.stderr)
            return 1

        run(["git", "checkout", args.base], cwd=path)
        run(["git", "pull", "--ff-only", "origin", args.base], cwd=path)
        run(["git", "checkout", "-b", branch], cwd=path)
        # **빈 브랜치를 먼저 민다** — 작업을 시작하기 전에 락을 잡아야 경쟁이 막힌다.
        push = run(["git", "push", "-u", "origin", branch], cwd=path, check=False)
        if push.returncode != 0:
            # 밀리는 사이 남이 만들었다(정상적인 경쟁 패배).
            print(f"락 획득 실패(경쟁): {push.stderr.strip()}", file=sys.stderr)
            return 1
    except RuntimeError as e:
        print(f"락 실패: {e}", file=sys.stderr)
        return 2

    json.dump({"branch": branch, "mode": "created", "path": path}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
