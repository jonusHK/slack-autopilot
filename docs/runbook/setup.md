# 셋업 — 봇 앱 · 토큰 · 루틴 등록

- 상태: 초안 (2026-08-14 갱신) — 3단계까지 작동 확인. 절차와 환경만 둔다(결정·설계는
  `../decisions.md`·`../design/`).

## 0. 준비물

| 항목 | 내용 |
|---|---|
| Slack 봇 앱 | 워크스페이스 관리 권한으로 생성(§1) |
| 봇 토큰(`xoxb-…`) | 시크릿으로만 보관 — 코드·문서·로그에 값 금지 |
| GitHub | 대상 레포 push·PR 권한(클라우드 에이전트의 GitHub 연동 + `gh`) |
| 클라우드 루틴 | 트리거 3개(:00·:20·:40) — 최소 간격 1시간을 오프셋으로 20분화. KST 07~02시 |

## 1. Slack 봇 앱 생성 (1회)

1. https://api.slack.com/apps → **Create New App** → **From a manifest** 가 가장 빠르다
   (스코프까지 한 번에). 매니페스트(JSON):
   ```json
   {"display_information":{"name":"slack-autopilot"},
    "features":{"bot_user":{"display_name":"slack-autopilot","always_online":false}},
    "oauth_config":{"scopes":{"bot":["channels:history","reactions:read","reactions:write","chat:write"]}},
    "settings":{"org_deploy_enabled":false,"socket_mode_enabled":false,"is_hosted":false,"token_rotation_enabled":false}}
   ```
   비공개 채널을 쓰려면 `groups:history` 를 더한다.
2. **Create and Install** → OAuth 승인(허용). 생성 직후 "스코프가 바뀌었으니 재설치하라"는
   배너가 뜨면 그 링크로 한 번 더 설치해야 스코프가 실제로 붙는다.
3. **Install App** 화면의 Bot User OAuth Token(`xoxb-…`)을 **복사 버튼**으로 클립보드에.
4. 대상 채널에 앱 추가(§1.5) — 안 하면 history 가 `not_in_channel`.
5. 토큰 저장은 §1.6 — **터미널에 값을 출력하지 않는다.**

### 1.5 채널에 앱 추가 — `/invite` 로는 안 된다 (함정)

채널 입력창에 `/invite @<봇>` 을 치면 자동완성에 봇이 뜨지만 **사람 초대 경로라 반영되지
않는다**(조용히 아무 일도 안 일어난다). `/invite ` 까지만 치면 나오는 메뉴에서
**"이 채널에 에이전트 및 앱 추가"** 를 고르고, 목록에서 봇의 **[추가]** 를 눌러야 한다.
확인은 §2 의 `conversations.history` 가 `ok:true` 가 되는 것.

### 1.6 토큰을 값 노출 없이 저장

복사 버튼을 누른 직후(클립보드에 토큰이 있는 상태):

```bash
cd <레포> && TOK=$(pbpaste) && case "$TOK" in
  xoxb-*) printf 'SLACK_BOT_TOKEN=%s\n' "$TOK" > .env && chmod 600 .env
          && echo "저장됨: 길이 ${#TOK}자";;
  *) echo "클립보드가 봇 토큰 형식이 아님(저장 안 함)";;
esac
```

토큰이 클립보드 → 파일로만 이동해 **터미널·기록 어디에도 값이 남지 않는다.**

## 2. 동작 확인 (스모크)

```bash
# 토큰은 환경변수 SLACK_BOT_TOKEN 으로만. 채널 ID 는 엔진 설정의 값.
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/conversations.history?channel=<채널ID>&limit=3" | jq '.ok'
# reactions.add / chat.postMessage 도 각 1회 — 테스트 메시지에.
```

`ok:false` 면 `error` 필드 확인 — `not_in_channel`(§1.5 누락)·`missing_scope`(§1-1 누락)이
단골이다.

부여된 스코프는 **부수효과 없이** 헤더로 확인한다(메시지·리액션을 남기지 않는다):

```bash
curl -s -D - -o /dev/null -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  https://slack.com/api/auth.test | grep -i '^x-oauth-scopes'
```

**채널 ID 를 얻으려고 `conversations.list` 를 쓰지 않는다** — `channels:read` 가 추가로
필요해진다. 채널 ID 는 슬랙 UI(채널 상세 하단) 또는 메시지 링크에서 읽어 환경변수로 넣는다.
엔진은 ID 를 설정으로 받으므로 이 스코프가 영구히 불필요하다(최소 권한).

## 3. 착수 순서 (단계 도입 — 한 번에 켜지 않는다)

1. ~~**봇 앱 + 토큰**(§1)~~ ✅ **완료(2026-08-14)** — 앱 생성·설치, 스코프 4종 부여 확인,
   #sai 채널 추가, `.env` 에 토큰·채널 ID·대상 레포 등록. `conversations.history` 응답 확인됨.
   **아직 안 한 것**: `chat:write`·`reactions:write` 의 실제 쓰기 스모크(채널에 흔적이 남으므로
   3단계 첫 루틴 실행에서 겸한다).
2. **엔진 스크립트 + 첫 소비자 정책 파일** — 이 레포에 검출·클레임 스크립트와 루틴
   프롬프트, 대상 레포에 `AUTOMATION.md`(계약: `../design/policy-contract.md`).
3. ~~**검출·분류 루틴**~~ ✅ **작동 확인(2026-08-14)** — 실채널에서 검출 → 클레임 → 분류 →
   답글까지 관통(약 2분 40초). 트리거 3개(:00·:20·:40), KST 07~02시. **지금은 분류 정확도
   관찰 구간**이고, 오판은 대상 레포의 정책 파일을 고쳐 잡는다(엔진이 아니라 — D-001).
4. **구현·PR 단계**(engine.md §4·§5) — 도구·명세는 준비됨(`lock.py`·`prompts/implement.md`),
   트리거만 미등록. 켜기 전 확인: ①분류 정확도 표본 ②VM 에서 대상 레포 push 권한
   ③이미지 첨부가 흔하면 `files:read` 스코프.
5. **병합 루틴**(engine.md §6) — 명세 준비됨(`prompts/merge.md`), 트리거 미등록.
6. 동시 3개로 확장. 두 번째 프로젝트는 `AUTOMATION.md` + 엔진 설정 한 줄로 붙는다 —
   그 이상이 필요하면 분리가 샌 것(D-001 ④).

## 3.5 루틴 등록 — 실제로 걸린 제약 셋 (2026-08-14)

**① 클라우드 루틴의 최소 간격은 1시간이다.** `*/10` 같은 cron 은 API 가 거절한다
(`cron interval too short`). 더 짧은 주기가 필요하면 **오프셋을 준 루틴 여러 개**를 만든다 —
`0 …` / `20 …` / `40 …` 세 개면 실질 20분 간격이다. 겹쳐 돌아도 안전하다(상태가 이모지에
있고 클레임이 중복을 막는다). 대신 프롬프트가 셋으로 복제되므로, 트리거 프롬프트는
**부트스트랩만** 담는다 — **실제로 하루 만에 갈라졌다**(한쪽 `--days 7`·Q 없음, 다른 쪽
14·Q 있음). 지금은 트리거에 "레포를 가져와 명세를 읽어라" 3줄만 있고 정본은
`prompts/bootstrap.md` 다. 바꿀 일이 생기면 **세 트리거를 함께** 바꾼다.

**② 시간대는 UTC 로 쓴다.** 현행 스케줄 KST 07~02시(새벽 2~7시만 쉼) = UTC `0-16,22,23`.

**③ 환경변수는 로컬 `.env` 가 아니라 클라우드 환경에 있어야 한다.** 루틴은 VM 에서 돌고
그 VM 에는 이 맥의 `.env` 가 없다(gitignore 라 레포에도 없다). claude.ai 의 **Code →
Environments → 해당 환경**에 `SLACK_BOT_TOKEN`·`SLACK_CHANNEL_ID_SAI`·`TARGET_REPO_SAI` 를
등록해야 한다. 없으면 루틴은 아무것도 하지 않고 "환경변수 누락"만 남기고 끝난다(설계대로).

**④ 기본 네트워크(Trusted)는 `slack.com` 을 막는다.** 이게 가장 오해하기 쉬운 함정이다 —
증상이 **"아무 일도 일어나지 않음"** 이라 토큰이나 스코프 문제로 착각하기 딱 좋다(2026-08-14
실제로 그렇게 한 번 헤맸다). Trusted 허용 목록은 Anthropic 서비스·GitHub 계열·컨테이너
레지스트리·클라우드 플랫폼·패키지 매니저뿐이고 **슬랙은 없다**.

조치 — 환경 설정에서 **Network access 를 Custom** 으로 바꾸고 **Allowed domains** 에:

```
slack.com
```

그리고 **"Also include default list of common package managers" 를 반드시 체크한다.**
빠뜨리면 적은 것만 열려서 GitHub·패키지 레지스트리가 막히고 엔진 클론부터 실패한다.
(GitHub 트래픽은 별도 프록시라 이 목록과 무관하게 동작하지만, 다른 준비 단계가 걸린다.)

**⑤ MCP 커넥터는 환경 기본값이 강제로 붙는다.** `mcp_connections: []` 로 지워도 되돌아온다.
대신 `allowed_tools` 에 `mcp__*` 를 넣지 않으면 도구가 노출되지 않아 입력 토큰이 절약된다 —
이 엔진은 슬랙을 python 으로 직접 부르므로 커넥터가 필요 없다.

## 4. 운영 노트

- 루틴은 유휴 시 즉시 종료(▶️ 없으면 토큰 소비 ~0). 사용량은 로컬 집계 도구(ccusage 류)에
  잡히지 않는다 — 클라우드 루틴은 로컬 CLI 세션이 아니다.
- 루틴이 중간에 죽어도 복구 절차가 없다 — 상태가 전부 슬랙·브랜치에 있어서(D-003 ④) 다음
  실행이 그냥 이어간다. "복구"가 필요해 보이면 상태 설계가 샌 것이니 engine.md §3 을 다시 본다.
