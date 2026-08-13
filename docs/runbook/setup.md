# 셋업 — 봇 앱 · 토큰 · 루틴 등록

- 상태: 초안 (2026-08-13) — 아래 착수 순서의 1·2단계 진행 전. 절차와 환경만 둔다(결정·설계는
  `../decisions.md`·`../design/`).

## 0. 준비물

| 항목 | 내용 |
|---|---|
| Slack 봇 앱 | 워크스페이스 관리 권한으로 생성(§1) |
| 봇 토큰(`xoxb-…`) | 시크릿으로만 보관 — 코드·문서·로그에 값 금지 |
| GitHub | 대상 레포 push·PR 권한(클라우드 에이전트의 GitHub 연동 + `gh`) |
| 클라우드 루틴 | Claude Code `/schedule` — 매시(정각 회피 분) |

## 1. Slack 봇 앱 생성 (1회, 사람)

1. https://api.slack.com/apps → **Create New App** → From scratch → 워크스페이스 선택.
2. **OAuth & Permissions → Bot Token Scopes** 4개:
   `channels:history` · `reactions:read` · `reactions:write` · `chat:write`.
   (비공개 채널을 쓰려면 `groups:history` 추가.)
3. **Install to Workspace** → Bot User OAuth Token(`xoxb-…`) 발급.
4. 대상 채널에서 `/invite @<봇이름>` — 초대 안 된 채널은 history 를 못 읽는다.
5. 토큰을 루틴 시크릿에 등록. **터미널에 값을 출력하지 않는다.**

## 2. 동작 확인 (스모크)

```bash
# 토큰은 환경변수 SLACK_BOT_TOKEN 으로만. 채널 ID 는 엔진 설정의 값.
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/conversations.history?channel=<채널ID>&limit=3" | jq '.ok'
# reactions.add / chat.postMessage 도 각 1회 — 테스트 메시지에.
```

`ok:false` 면 `error` 필드 확인 — `not_in_channel`(§1-4 누락)·`missing_scope`(§1-2 누락)이
단골이다.

## 3. 착수 순서 (단계 도입 — 한 번에 켜지 않는다)

1. **봇 앱 + 토큰**(§1) — 이게 없으면 나머지가 전부 막힌다.
2. **엔진 스크립트 + 첫 소비자 정책 파일** — 이 레포에 검출·클레임 스크립트와 루틴
   프롬프트, 대상 레포에 `AUTOMATION.md`(계약: `../design/policy-contract.md`).
3. **검출·클레임만 하는 루틴**(구현 없음) — ▶️ 를 집어 💬 + "무엇을 하려는지 + 티어 분류
   결과"만 답글. **하루 돌려 분류 정확도를 눈으로 확인한다.** 오판은 대상 레포의 정책
   파일을 고쳐 잡는다(엔진이 아니라 — D-001).
4. **구현·PR 단계**(engine.md §4·§5) — 처음엔 동시 1개.
5. **병합 루틴**(engine.md §6).
6. 동시 3개로 확장. 두 번째 프로젝트는 `AUTOMATION.md` + 엔진 설정 한 줄로 붙는다 —
   그 이상이 필요하면 분리가 샌 것(D-001 ④).

## 4. 운영 노트

- 루틴은 유휴 시 즉시 종료(▶️ 없으면 토큰 소비 ~0). 사용량은 로컬 집계 도구(ccusage 류)에
  잡히지 않는다 — 클라우드 루틴은 로컬 CLI 세션이 아니다.
- 루틴이 중간에 죽어도 복구 절차가 없다 — 상태가 전부 슬랙·브랜치에 있어서(D-003 ④) 다음
  실행이 그냥 이어간다. "복구"가 필요해 보이면 상태 설계가 샌 것이니 engine.md §3 을 다시 본다.
