"""Slack Web API 최소 래퍼 (표준 라이브러리만 — 클라우드 루틴 VM 에서 의존성 설치 없이 돈다).

규칙:
- 토큰은 환경변수 SLACK_BOT_TOKEN 에서만 읽는다. 인자·로그·예외 메시지에 값을 싣지 않는다.
- 실패는 삼키지 않는다. ok:false 는 SlackError 로 올린다(엔진이 판단하게).
  예외 — 멱등 호출의 무해한 실패(already_reacted 등)는 호출부가 명시적으로 허용한다.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://slack.com/api/"


class SlackError(RuntimeError):
    def __init__(self, method, error):
        super().__init__(f"{method}: {error}")
        self.method = method
        self.error = error


def _token():
    tok = os.environ.get("SLACK_BOT_TOKEN", "")
    if not tok:
        raise SystemExit("SLACK_BOT_TOKEN 이 비어 있습니다(.env 또는 루틴 시크릿 확인).")
    return tok


def call(method, params=None, post=False, retries=3):
    """Slack API 호출. 429/5xx 는 재시도, 그 외 실패는 SlackError."""
    params = params or {}
    data = None
    url = API + method
    headers = {"Authorization": f"Bearer {_token()}"}

    if post:
        data = urllib.parse.urlencode(params).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif params:
        url += "?" + urllib.parse.urlencode(params)

    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(int(e.headers.get("Retry-After", "3")))
                continue
            if 500 <= e.code < 600 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        if body.get("ok"):
            return body
        err = body.get("error", "unknown")
        if err == "ratelimited" and attempt < retries - 1:
            time.sleep(3)
            continue
        raise SlackError(method, err)
    raise SlackError(method, "retries_exhausted")


def history(channel, oldest=None, limit=200):
    p = {"channel": channel, "limit": limit}
    if oldest:
        p["oldest"] = oldest
    return call("conversations.history", p)["messages"]


def replies(channel, thread_ts, limit=200):
    p = {"channel": channel, "ts": thread_ts, "limit": limit}
    return call("conversations.replies", p)["messages"]


def add_reaction(channel, ts, name):
    """이모지 부착. 이미 붙어 있으면 False(무해) — 그 외 실패는 예외."""
    try:
        call("reactions.add", {"channel": channel, "timestamp": ts, "name": name}, post=True)
        return True
    except SlackError as e:
        if e.error == "already_reacted":
            return False
        raise


def post(channel, text, thread_ts=None):
    p = {"channel": channel, "text": text}
    if thread_ts:
        p["thread_ts"] = thread_ts
    return call("chat.postMessage", p, post=True)


def reactions_of(msg):
    return {r["name"] for r in msg.get("reactions", [])}
