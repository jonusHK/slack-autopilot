"""상태 기계의 이모지 어휘 한 자리 (engine.md §1 · decisions D-002).

문구·이모지가 코드 곳곳에 흩어지면 상태 정의가 조용히 갈라진다. 여기만 고친다.
"""

TRIGGER = "arrow_forward"      # ▶️ 진행 필요 — **사람만**
CLAIM = "speech_balloon"       # 💬 처리 중
PR_OPEN = "eyes"               # 👀 PR 열림 — 사람 검토 대기
NEEDS_DECISION = "question"    # ❓ 결정 필요
MERGE = "rocket"               # 🚀 병합 진행 — **사람만**
DONE = "white_check_mark"      # ✅ 병합 완료
FAILED = "x"                   # ❌ 실패

# 봇이 절대 붙이지 않는 것(D-002 — 자기 트리거 금지가 무한 루프를 막는다).
HUMAN_ONLY = frozenset({TRIGGER, MERGE})

BOT_MAY_ADD = frozenset({CLAIM, PR_OPEN, NEEDS_DECISION, DONE, FAILED})


def assert_bot_may_add(name):
    if name in HUMAN_ONLY:
        raise RuntimeError(
            f"봇은 :{name}: 를 붙일 수 없다(D-002 — 사람 전용 트리거). "
            "이 규칙을 우회하면 봇이 자기 작업을 스스로 트리거한다."
        )
    if name not in BOT_MAY_ADD:
        raise RuntimeError(f"정의되지 않은 이모지: {name} (emoji.py 에 먼저 추가)")
