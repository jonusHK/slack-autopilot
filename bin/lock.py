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
- **죽은 락은 회수한다**(§ stale). 락 해제가 없는 설계라, 브랜치를 민 직후 실행이 죽으면
  그 노드는 영원히 잠긴다 — 다음 실행은 브랜치가 있어 건너뛰고, 메시지에는 💬 가 붙어 있어
  분류 검출에도 안 잡힌다. 조용한 교착이다.

사용:
  python3 bin/lock.py --repo owner/name --ts 1786675913.239919 [--base main] [--work-dir DIR]

출력(stdout, JSON): {"branch": "...", "mode": "created"|"reused"|"reclaimed", "path": "..."}
종료코드 1 = 살아 있는 다른 실행이 잡고 있다(건너뛰라는 뜻).
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import github_api  # noqa: E402

BRANCH_PREFIX = "auto/slack-"


def run(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        # 이 문구는 실패 알림으로 슬랙까지 간다 — 토큰이 섞일 여지를 남기지 않는다.
        raise RuntimeError(github_api.scrub(
            f"{' '.join(cmd)} → {p.returncode}\n{p.stderr.strip()}"))
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
        # 토큰은 자격 저장 파일에 있고 주소는 깨끗하다(github_api.setup_git 참조).
        github_api.setup_git()
        run(["git", "clone", github_api.clone_url(repo), path])
    return path


def remote_has(path, branch):
    out = run(["git", "ls-remote", "--heads", "origin", branch], cwd=path).stdout
    return bool(out.strip())


def has_open_pr(repo, branch):
    """이 브랜치로 열린 PR 이 있는가. 있으면 살아 있는 작업이다(회수 금지)."""
    try:
        return bool(github_api.pr_list(repo, head=branch, state="all"))
    except github_api.GitHubError as e:
        # 판단할 수 없으면 **살아 있다고 본다** — 남의 작업을 뺏는 쪽이 더 비싸다.
        raise RuntimeError(f"PR 조회 실패(회수 판단 불가): {e}")


def branch_age_minutes(path, branch):
    """원격 브랜치 tip 의 커밋 시각으로부터 흐른 분. 락을 건 시점의 근사치다."""
    run(["git", "fetch", "origin", f"{branch}:refs/remotes/origin/{branch}"],
        cwd=path, check=False)
    out = run(["git", "log", "-1", "--format=%ct", f"origin/{branch}"], cwd=path).stdout.strip()
    return (time.time() - int(out)) / 60


def is_stale(repo, path, branch, stale_minutes):
    """PR 이 하나도 없고 브랜치가 충분히 오래됐으면 죽은 락이다.

    상한(자기 수정 60분)보다 넉넉히 잡아야 **살아 있는 작업을 뺏지 않는다**. PR 이 하나라도
    있으면(열렸든 닫혔든) 그 실행은 최소한 PR 을 여는 데까지 갔다는 뜻이라 회수하지 않는다.
    """
    if has_open_pr(repo, branch):
        return False
    return branch_age_minutes(path, branch) >= stale_minutes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--ts", required=True, help="노드 ts — 브랜치 이름의 근거")
    ap.add_argument("--base", default="main")
    ap.add_argument(
        "--stale-minutes",
        type=int,
        default=120,
        help="PR 없는 브랜치를 죽은 락으로 보는 경과 시간(기본 120분). "
             "자기 수정 상한 60분보다 넉넉해야 살아 있는 작업을 뺏지 않는다.",
    )
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
        mode = "created"
        if remote_has(path, branch):
            # 이미 누가 잡았다. 살아 있는 작업이면 물러나고(이어서 하려면 --reuse 로 의도를
            # 드러낸다), 죽은 락이면 회수한다.
            if not is_stale(args.repo, path, branch, args.stale_minutes):
                print(f"이미 잡힌 노드다(살아 있음): {branch}", file=sys.stderr)
                return 1
            age = int(branch_age_minutes(path, branch))
            print(f"죽은 락 회수: {branch} (PR 없음 · {age}분 경과)", file=sys.stderr)
            run(["git", "push", "origin", "--delete", branch], cwd=path)
            mode = "reclaimed"

        run(["git", "checkout", args.base], cwd=path)
        run(["git", "pull", "--ff-only", "origin", args.base], cwd=path)
        # -B 로 만든다: 회수했거나 이전 실행이 남긴 **로컬** 브랜치가 있어도 base 로 리셋된다.
        # -b 면 그 경우 "already exists" 로 죽는데, 원격은 비었으므로 잡을 수 있는 락이다.
        run(["git", "checkout", "-B", branch], cwd=path)
        # **빈 브랜치를 먼저 민다** — 작업을 시작하기 전에 락을 잡아야 경쟁이 막힌다.
        push = run(["git", "push", "-u", "origin", branch], cwd=path, check=False)
        if push.returncode != 0:
            # 밀리는 사이 남이 만들었다(정상적인 경쟁 패배).
            print(f"락 획득 실패(경쟁): {push.stderr.strip()}", file=sys.stderr)
            return 1
    except RuntimeError as e:
        print(f"락 실패: {e}", file=sys.stderr)
        return 2

    json.dump({"branch": branch, "mode": mode, "path": path}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
