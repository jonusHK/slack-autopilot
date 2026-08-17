#!/usr/bin/env python3
"""GitHub REST API 최소 래퍼 (표준 라이브러리만 — VM 에 아무것도 설치하지 않는다).

**`gh` 를 쓰지 않는 이유**: 세션 VM 에 `gh` 가 설치돼 있지 않았고, 한 실행이 이를
직접 설치하느라 시간을 태웠다. 매 실행 반복될 낭비이고, 설치가 막히면 그대로 실패다.
슬랙을 다루는 `slack_api.py` 와 같은 모양으로 API 를 직접 부르면 그 전제가 사라진다.

규칙:
- 토큰은 환경변수(GH_TOKEN → GITHUB_TOKEN)에서만 읽는다. 인자·로그·예외에 값을 싣지 않는다.
- **git 명령에는 토큰을 URL 로 넘기지 않는다.** 자격 저장 파일에 두고 원격 주소는 깨끗하게
  유지한다 — git 이 낸 에러 문구가 그대로 슬랙에 실리는 경로가 있어서, URL 에 토큰을 박으면
  실패 알림이 토큰 유출 경로가 된다.
- 실패는 삼키지 않는다. 판단은 엔진이 한다.

CLI:
  python3 bin/github_api.py setup-git          자격 저장 설정(클론·푸시 전에 한 번)
  python3 bin/github_api.py pr-list  --repo R --head BRANCH [--state all]
  python3 bin/github_api.py pr-create --repo R --head BRANCH --base main
                                      --title T --body-file F
  python3 bin/github_api.py checks   --repo R --ref SHA
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def _token():
    """토큰이 있으면 쓰고, **없으면 없는 채로 간다.**

    클라우드 세션에서는 레포가 세션에 붙어 있으면 프록시가 밖에서 자격을 붙여 준다 —
    그래서 토큰이 없어도 REST 가 200 으로 돌아온다(2026-08-17 실측). 예전에는 여기서
    SystemExit 으로 죽였는데, 그건 **실제로 필요 없는 것을 필수로 만든 것**이었다.
    자리표시자(`proxy-injected`)도 진짜 토큰이 아니라 붙이지 않는다.

    토큰 없이 정말로 권한이 모자란 경우는 호출이 403/404 로 돌아오고, 그 본문에
    무엇이 막혔는지 적혀 있다. **그 판단은 호출부가 한다** — 여기서 미리 죽이면
    "왜 막혔는지"를 알려 주는 본문을 볼 기회가 사라진다.
    """
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    return "" if tok == "proxy-injected" else tok


def scrub(text):
    """토큰이 섞였을 수 있는 문자열을 밖으로 내보내기 전에 지운다.

    URL 에 토큰을 박지 않는 것이 1차 방어이고, 이건 2차다. 실패 알림은 사람이 보라고
    있는 것이라 원문을 최대한 살리되, 토큰만은 예외 없이 가린다.
    """
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    return text.replace(tok, "***") if tok else text


def call(path, method="GET", body=None, retries=3):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "slack-autopilot",
    }
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    if data:
        headers["Content-Type"] = "application/json"

    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp) if resp.status != 204 else {}
        except urllib.error.HTTPError as e:
            detail = scrub(e.read().decode("utf-8", "replace")[:400])
            # 2차 한도(초당 제한)와 5xx 만 재시도한다. 403/404 는 권한·오타라 재시도가 무의미하다.
            retryable = e.code in (429,) or 500 <= e.code < 600
            if retryable and attempt < retries - 1:
                time.sleep(int(e.headers.get("Retry-After", 2 ** attempt)))
                continue
            raise GitHubError(f"{method} {path} → HTTP {e.code}: {detail}")
    raise GitHubError(f"{method} {path} → 재시도 소진")


# --- git 자격 -----------------------------------------------------------------

CRED_FILE = os.path.expanduser("~/.git-credentials-autopilot")


def setup_git():
    """git 이 무인으로 돌 수 있게 준비한다. **토큰이 있을 때만** 자격 파일을 깐다.

    토큰이 있으면 자격 저장 파일에 두고 원격 주소는 `https://github.com/owner/name.git`
    그대로 쓴다 — 토큰이 주소에도, 프로세스 인자에도, git 에러 문구에도 남지 않는다.

    토큰이 없으면 아무 자격도 깔지 않는다. 클라우드 세션에서는 레포가 세션에 붙어 있으면
    프록시가 밖에서 자격을 붙여 주므로 그대로 클론·push 가 된다(2026-08-17 실측).
    프롬프트만은 어느 쪽이든 막는다 — 자격이 모자랄 때 사용자 이름을 물으며 멈추면
    무인 실행이 조용히 매달린다.
    """
    tok = _token()
    if tok:
        with open(CRED_FILE, "w") as f:
            f.write(f"https://x-access-token:{tok}@github.com\n")
        os.chmod(CRED_FILE, 0o600)
        subprocess.run(
            ["git", "config", "--global", "credential.helper", f"store --file={CRED_FILE}"],
            check=True,
        )
    # 자격이 없을 때 git 이 프롬프트를 띄우고 멈추는 것을 막는다(무인 실행).
    subprocess.run(["git", "config", "--global", "core.askPass", ""], check=True)
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    return CRED_FILE if tok else None


def clone_url(repo):
    return f"https://github.com/{repo}.git"


# --- PR -----------------------------------------------------------------------

def pr_list(repo, head=None, state="all"):
    q = f"?state={state}&per_page=100"
    if head:
        # head 필터는 owner:branch 형태를 요구한다.
        q += f"&head={repo.split('/')[0]}:{head}"
    return call(f"/repos/{repo}/pulls{q}")


def pr_create(repo, head, base, title, body):
    return call(
        f"/repos/{repo}/pulls",
        method="POST",
        body={"head": head, "base": base, "title": title, "body": body},
    )


def pr_number(ref):
    """PR 을 URL 로도 번호로도 받는다 — 스레드에 남는 것은 URL 이라서."""
    s = str(ref).rstrip("/")
    tail = s.rsplit("/", 1)[-1]
    if not tail.isdigit():
        raise GitHubError(f"PR 번호를 읽을 수 없습니다: {ref}")
    return int(tail)


def pr_get(repo, ref):
    return call(f"/repos/{repo}/pulls/{pr_number(ref)}")


def pr_files(repo, ref):
    return [f["filename"]
            for f in call(f"/repos/{repo}/pulls/{pr_number(ref)}/files?per_page=100")]


def pr_merge(repo, ref, method="merge"):
    return call(
        f"/repos/{repo}/pulls/{pr_number(ref)}/merge",
        method="PUT",
        body={"merge_method": method},
    )


def checks(repo, ref):
    """커밋 하나의 CI 상태를 한 덩어리로. check runs 와 commit status 를 모두 본다.

    둘 중 하나만 보면 놓친다 — GitHub Actions 는 check run 으로, 외부 CI 는 status 로
    올라오는 것이 흔하다.

    반환: {"state": "success"|"pending"|"failure", "failed": [이름...], "pending": [이름...]}
    """
    failed, pending = [], []

    runs = call(f"/repos/{repo}/commits/{ref}/check-runs?per_page=100").get("check_runs", [])
    for r in runs:
        if r.get("status") != "completed":
            pending.append(r.get("name", "?"))
        elif r.get("conclusion") not in ("success", "neutral", "skipped"):
            failed.append(r.get("name", "?"))

    st = call(f"/repos/{repo}/commits/{ref}/status")
    for s in st.get("statuses", []):
        if s.get("state") == "pending":
            pending.append(s.get("context", "?"))
        elif s.get("state") not in ("success",):
            failed.append(s.get("context", "?"))

    if failed:
        state = "failure"
    elif pending:
        state = "pending"
    elif runs or st.get("statuses"):
        state = "success"
    else:
        # 붙은 검사가 하나도 없다. "그린"이 아니라 "모름"이다 — 병합 판단은 사람 몫으로 넘긴다.
        state = "none"
    return {"state": state, "failed": failed, "pending": pending}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup-git")

    p = sub.add_parser("pr-list")
    p.add_argument("--repo", required=True)
    p.add_argument("--head")
    p.add_argument("--state", default="all")

    p = sub.add_parser("pr-create")
    p.add_argument("--repo", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--base", default="main")
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True)

    p = sub.add_parser("pr-get")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, help="PR URL 또는 번호")

    p = sub.add_parser("pr-files")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True)

    p = sub.add_parser("pr-merge")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True)
    p.add_argument("--method", default="merge", choices=["merge", "squash", "rebase"])

    p = sub.add_parser("checks")
    p.add_argument("--repo", required=True)
    p.add_argument("--ref", required=True, help="커밋 SHA. PR 이면 head.sha")

    a = ap.parse_args()
    try:
        if a.cmd == "setup-git":
            print(setup_git())
        elif a.cmd == "pr-list":
            json.dump(pr_list(a.repo, a.head, a.state), sys.stdout)
            print()
        elif a.cmd == "pr-create":
            with open(a.body_file) as f:
                body = f.read()
            pr = pr_create(a.repo, a.head, a.base, a.title, body)
            print(pr["html_url"])
        elif a.cmd == "pr-get":
            pr = pr_get(a.repo, a.pr)
            out = {k: pr.get(k) for k in
                   ("number", "state", "merged", "mergeable", "mergeable_state",
                    "title", "html_url")}
            out["head_sha"] = pr["head"]["sha"]
            json.dump(out, sys.stdout)
            print()
        elif a.cmd == "pr-files":
            json.dump(pr_files(a.repo, a.pr), sys.stdout)
            print()
        elif a.cmd == "pr-merge":
            json.dump(pr_merge(a.repo, a.pr, a.method), sys.stdout)
            print()
        elif a.cmd == "checks":
            json.dump(checks(a.repo, a.ref), sys.stdout)
            print()
    except GitHubError as e:
        print(scrub(str(e)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
