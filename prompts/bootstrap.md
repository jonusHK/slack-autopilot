# 트리거 부트스트랩 (정본)

**세 트리거(:00·:20·:40)의 프롬프트는 아래와 글자까지 같아야 한다.** 트리거가 여럿이면
프롬프트도 여러 벌이 되고, 여러 벌은 반드시 갈라진다 — 실제로 하루 만에 갈라졌다(한쪽은
`--days 7` 에 Q 티어 없음, 다른 쪽은 14 에 Q 있음).

그래서 **부트스트랩에는 갈라질 것을 두지 않는다.** 환경 확인·분류 규칙·절대 규칙은 전부
`triage.md` 에 있다. 여기 남은 것은 "레포를 가져와 명세를 읽어라"와 **그것이 실패했을 때의
알림** 하나뿐이다.

**클론 실패 알림을 굳이 여기 둔 이유**: 실패 보고를 레포 파일(`report_failure.py`)로 옮겼더니,
**레포를 못 가져온 실패는 보고할 수단도 함께 사라졌다.** 그때가 정확히 아무 흔적도 안 남는
경우다. 그래서 이 한 줄만은 레포에 의존하지 않는 형태(curl)로 여기 둔다.

---

```
slack-autopilot 엔진의 분류 루틴이다. 명세는 레포 안에 있고, 이 프롬프트는 그것을 가져오기만 한다.

git clone --depth 1 https://github.com/jonusHK/slack-autopilot.git ~/slack-autopilot 2>/dev/null || git -C ~/slack-autopilot pull -q --ff-only
cd ~/slack-autopilot

성공했으면 prompts/triage.md 를 읽고 그 파일의 절차를 그대로 수행한다. 그 파일이 명세이고 이 프롬프트보다 우선한다.

레포를 못 가져왔으면 명세도 못 읽는다. 그때는 **침묵하지 말고** 아래로 알린 뒤 종료한다(레포에 의존하지 않는 유일한 경로다):
curl -s -X POST -H "Authorization: Bearer $SLACK_BOT_TOKEN" -H "Content-type: application/json; charset=utf-8" -d "{\"channel\":\"$SLACK_CHANNEL_ID_SAI\",\"text\":\":warning: 루틴이 엔진 레포를 가져오지 못했어요 (클론·풀 실패)\"}" https://slack.com/api/chat.postMessage
```
