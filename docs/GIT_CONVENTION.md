# Git Convention

팀에서 합의한 브랜치 전략·커밋 메시지·MR/이슈 작성 규칙입니다.
**사람과 AI 에이전트 모두 이 규칙을 따릅니다.** (MR/이슈 템플릿은 GitLab의 `.gitlab/` 템플릿으로도 등록되어 있습니다.)

## 1. Branch 전략 (Git Flow)

| 구분 | 브랜치 | 역할 |
|------|--------|------|
| main | `master` | 제품으로 출시되는 브랜치 |
| main | `develop` | 다음 출시 버전을 개발하는 브랜치 |
| sub | `feature/*` | 기능을 개발하는 브랜치 |
| sub | `release/*` | 이번 출시 버전을 준비하는 브랜치 |
| sub | `hotfix/*` | 출시 버전 버그를 수정하는 브랜치 |

흐름: `feature/*` → `develop` → `release/*` → `master` (긴급 수정은 `master` → `hotfix/*` → `master`+`develop`)

> ⚠️ 현재 이 저장소의 기본 브랜치는 `main`입니다. 전략 적용 시 `master`/`develop` 브랜치 정리가 필요합니다.

## 2. Commit Message — `[type] subject`

### type

| type | 용도 |
|------|------|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변화 없이 구조 개선 |
| `style` | 들여쓰기, 포맷팅 등 코드 스타일 수정 |
| `docs` | README, API 명세 등 문서 수정 |
| `test` | 테스트 코드 추가/수정 |
| `chore` | 설정 변경, 패키지 관리, 파일 정리 등 기타 작업 |

### subject

- **50자 이하**로 간결하게
- 변경 내용을 **명사형**으로
- **마침표 없이**

### 예시

```
[feat] 로그인 기능 추가
[fix] 알림 중복 전송 오류 수정
[refactor] 인증 로직 분리
[docs] 실행 방법 추가
```

## 3. Merge Request 템플릿

```markdown
## 📌 요약 (Summary)
어떤 변경 사항을 적용하는 MR인가요?

## 🛠 작업 내용 (Changes)
- [ ] 기능 개발 (Feature)
    - [ ]  FE
    - [ ]  BE
    - [ ]  AI
    - [ ]  EM
- [ ] 버그 수정 (Bug fix)
- [ ] 리팩토링 (Refactoring)
- [ ] 문서 수정 (Documentation)

## 🎯 관련 이슈 (Related Issues)
Close #

## 📸 스크린샷 (선택)
```

## 4. Issue 템플릿

```markdown
## 목적

## 작업 내용

- [ ]

## 참고사항
```
