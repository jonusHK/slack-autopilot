# slack-autopilot

슬랙 채널에 적은 개발 지시를 자동으로 검출해 **백그라운드에서 구현 → PR → 병합**까지 끌고
가는 범용 엔진. 사람이 하는 일은 셋뿐이다 — **지시를 쓰고, ▶️ 를 달고, 병합할 PR 에 🚀 를 단다.**

```
사람: 슬랙에 지시 + ▶️
 └→ [20분마다] 클라우드 루틴: 검출 → 클레임(브랜치+💬) → 티어 분류(Q/A/B)
      ├─ Q(설명 요구): 근거를 붙여 답변 → ✅
      ├─ A(스펙 확정): 구현 → PR → CI 그린까지 자기 수정 → 🧵
      └─ B(재량 필요): ❓ + 판단 지점 답글 → 사람이 답글로 결정 + ▶️ → 재투입
사람: PR 검토 → 🚀
 └→ 병합 루틴: 순차 병합 → ✅
```

## 구조

| 무엇 | 어디 |
|---|---|
| 엔진(범용) — 상태 기계·검출·클레임·자기 수정·병합 | 이 레포 |
| 정책(프로젝트별) — 티어 경계·리뷰어·병합 금지선 | **각 대상 레포의 `AUTOMATION.md`** |
| 검증 — 테스트·e2e | 대상 레포의 GitHub Actions (엔진은 결과만 읽음) |
| 실행 — 20분 폴링(KST 07~02시) | Claude Code 클라우드 루틴 3개(:00·:20·:40) |

새 프로젝트를 붙이는 비용 = 그 레포에 `AUTOMATION.md` 작성 + 엔진 설정에 채널 매핑 한 줄.
**엔진 수정이 필요했다면 분리가 샌 것이다.**

## 문서

- 결정 로그: [docs/decisions.md](docs/decisions.md)
- 엔진 설계(상태 기계·파이프라인·락 — **무엇을·왜**): [docs/design/engine.md](docs/design/engine.md)
- 런타임(**어떻게 도는가** — 실행 순서·코드 맵·실패 모드·현재 단계): [docs/design/runtime.md](docs/design/runtime.md)
- 정책 파일 계약(`AUTOMATION.md` 작성법): [docs/design/policy-contract.md](docs/design/policy-contract.md)
- 셋업(봇 앱·토큰·루틴 등록): [docs/runbook/setup.md](docs/runbook/setup.md)

## 상태

설계 단계(2026-08-13) — 문서 먼저, 구현은 docs/runbook/setup.md 의 착수 순서대로.
첫 소비자: [sai](https://github.com/jonusHK/sai) (`AUTOMATION.md` 는 그 레포에).
