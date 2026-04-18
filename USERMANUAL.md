# Harness 사용자 매뉴얼

Harness는 Claude Code를 이용한 **구조화된 AI 개발 워크플로우**다.  
큰 프로젝트를 원자적인 step으로 분해하고, 각 step을 독립된 Claude 세션에서 실행한다.

---

## 목차

1. [Harness란 무엇인가](#1-harness란-무엇인가)
2. [새 프로젝트 시작하기](#2-새-프로젝트-시작하기)
3. [Phase & Step 설계 방법](#3-phase--step-설계-방법)
4. [파일 생성: scaffold.py](#4-파일-생성-scaffoldpy)
5. [Step 파일 작성 가이드](#5-step-파일-작성-가이드)
6. [실행: execute.py](#6-실행-executepy)
7. [코드 리뷰: /review](#7-코드-리뷰-review)
8. [에러 복구](#8-에러-복구)
9. [전체 워크플로우 요약](#9-전체-워크플로우-요약)
10. [팁 & 베스트 프랙티스](#10-팁--베스트-프랙티스)

---

## 1. Harness란 무엇인가

### 핵심 개념

| 개념 | 설명 |
|------|------|
| **Phase** | 기능 단위 작업 묶음 (예: 인증 구현, 결제 연동) |
| **Step** | Phase를 구성하는 원자적 작업 (예: DB 스키마, API Route) |
| **Guardrail** | 매 step에 주입되는 프로젝트 규칙 (CLAUDE.md + docs/*.md) |
| **Summary** | 완료된 step의 산출물 요약 → 다음 step에 컨텍스트로 전달 |

### 왜 Harness를 쓰는가

- **컨텍스트 오염 방지**: 긴 대화에서 AI가 초반 결정을 덮어쓰는 문제를 step 분리로 해결
- **일관성 보장**: CLAUDE.md + docs가 모든 step에 주입되어 규칙 위반 방지
- **재현 가능성**: JSON 상태 파일로 어디서든 중단/재개 가능
- **자가 교정**: 실패 시 최대 3회 재시도하며 에러 메시지를 피드백

---

## 2. 새 프로젝트 시작하기

### Step 1: 프레임워크 파일 복사

```bash
cp -r /path/to/harness_framework/ /path/to/my-project/
cd /path/to/my-project
```

복사되는 파일:
```
my-project/
├── .claude/
│   ├── settings.json       # 보안 훅 + 종료 시 lint/build/test
│   └── commands/
│       ├── harness.md      # /harness 명령어
│       └── review.md       # /review 명령어
├── docs/
│   ├── PRD.md              # 제품 요구사항 템플릿
│   ├── ARCHITECTURE.md     # 아키텍처 템플릿
│   ├── ADR.md              # 기술 결정 기록 템플릿
│   └── UI_GUIDE.md         # UI 디자인 가이드 템플릿
├── scripts/
│   ├── execute.py          # Step 실행 오케스트레이터
│   └── scaffold.py         # Phase 스캐폴딩 도구
└── CLAUDE.md               # 프로젝트 규칙 (반드시 채울 것)
```

### Step 2: 핵심 문서 작성

**이 순서로 작성한다:**

1. `CLAUDE.md` — 기술 스택, 아키텍처 규칙, 명령어 채우기
2. `docs/PRD.md` — 목표, 핵심 기능, 성공 지표
3. `docs/ARCHITECTURE.md` — 디렉토리 구조, 패턴, 에러 처리
4. `docs/ADR.md` — 주요 기술 결정과 이유
5. `docs/UI_GUIDE.md` — 색상, 컴포넌트, 레이아웃 규칙

> **중요**: `CLAUDE.md`의 CRITICAL 항목은 execute.py가 매 step에 주입한다.  
> 비어있으면 Claude 세션이 일관성 없는 코드를 생성한다.

### Step 3: Claude Code에서 /harness 실행

```
/harness
```

Claude가 docs/ 를 읽고 구현 계획을 제안한다.

---

## 3. Phase & Step 설계 방법

### Phase 분리 기준

| Phase 유형 | 예시 |
|-----------|------|
| 기반 구축 | 프로젝트 설정, 타입 정의 |
| 서비스 레이어 | 외부 API 연동, 비즈니스 로직 |
| API 레이어 | Next.js API Routes |
| UI 레이어 | 페이지, 컴포넌트 |

### Step 크기 기준

**하나의 Step에 담을 수 있는 규모:**
- 생성/수정 파일: **5개 이하**
- 코드 라인: **200줄 이하**
- 새 외부 패키지: **2개 이하**

**쪼개야 하는 신호:**
- "A도 하고 B도 한다"는 작업 설명
- DB 스키마 변경 + API 구현을 동시에 다룰 때
- OAuth/결제 등 외부 서비스 연동 + UI를 한 번에 묶을 때

### Phase 명명 규칙

```
{순번}-{목적}
예: 0-foundation, 1-youtube-service, 2-notion-integration, 3-ui-pages
```

### Step 명명 규칙

```
kebab-case로 핵심 모듈/작업을 한두 단어로
예: project-setup, core-types, api-layer, home-page
```

---

## 4. 파일 생성: scaffold.py

### 기본 사용법

```bash
python3 scripts/scaffold.py <phase-name> <step-name> [<step-name> ...]
```

### 예시

```bash
python3 scripts/scaffold.py 0-foundation project-setup core-types
python3 scripts/scaffold.py 1-youtube youtube-service summary-service
python3 scripts/scaffold.py 2-notion notion-service sync-api
python3 scripts/scaffold.py 3-ui home-page table-page detail-page
```

### 생성 결과

```
phases/
├── index.json                    ← 전체 phase 현황
├── 0-foundation/
│   ├── index.json                ← 이 phase의 step 목록
│   ├── step0.md                  ← project-setup 지시서
│   └── step1.md                  ← core-types 지시서
└── ...
```

### 사전 검증 (dry-run)

step 파일을 다 채운 후, **실제 실행 전에 반드시 dry-run을 실행**한다:

```bash
python3 scripts/execute.py 0-foundation --dry-run
```

dry-run이 확인하는 것:
- 모든 `step{N}.md` 파일 존재 여부
- guardrails(CLAUDE.md + docs/*.md) 로딩 성공
- 각 step 프롬프트 예상 길이 출력

---

## 5. Step 파일 작성 가이드

scaffold.py가 생성한 파일에서 `{TODO}` 부분을 채운다.

### 필수 섹션 구조

```markdown
# Step N: {step-name}

## 읽어야 할 파일
- 이 step에서 읽어야 할 파일 목록
- 이전 step 산출물 경로

## 작업
- 생성/수정할 파일 경로
- 함수/클래스 시그니처 (구현은 에이전트 재량)
- 설계 의도에서 벗어나면 안 되는 핵심 규칙

## Acceptance Criteria
```bash
npm run build && npm test
```

## 검증 절차
1. AC 커맨드 실행
2. 아키텍처 체크리스트 확인
3. index.json step 상태 업데이트

## 금지사항
- X를 하지 마라. 이유: Y
```

### 작업 섹션 작성 팁

**좋은 예:**
```markdown
## 작업

`src/services/youtube.ts`를 생성한다.

```typescript
// 시그니처만 제시 — 구현은 에이전트 재량
export async function getTranscript(videoId: string): Promise<Transcript[]>
export function extractVideoId(url: string): string | null
```

- `Transcript` 타입은 `src/types/index.ts`에 정의된 것을 사용한다.
- 네트워크 오류 시 ApiError를 throw한다 (ARCHITECTURE.md 에러 패턴 참고).
- youtube-transcript 패키지를 사용한다 (ADR-002 참고).
```

**나쁜 예:**
```markdown
## 작업

YouTube에서 트랜스크립트를 가져오는 기능을 구현한다.
```
→ 파일 경로, 시그니처, 사용 패키지가 없다.

### Summary 작성 기준

step 완료 시 `index.json`에 기록하는 `summary` 한 줄:

```json
"summary": "src/services/youtube.ts 생성 — getTranscript(videoId), extractVideoId(url) 익스포트"
```

포함해야 할 것:
1. 생성/수정된 핵심 파일 경로
2. 외부에서 쓰는 함수/타입 이름
3. 다음 step이 알아야 할 결정 (예: `videoId는 11자 string`)

---

## 6. 실행: execute.py

### 기본 실행

```bash
python3 scripts/execute.py <phase-dir>
```

### 주요 옵션

| 옵션 | 설명 |
|------|------|
| `--dry-run` | Claude 호출 없이 파일 존재·가드레일 로딩만 검증 |
| `--push` | 완료 후 원격 브랜치에 자동 push |
| `--max-retries N` | step당 최대 재시도 횟수 (기본: 3) |

### 실행 흐름

```
1. phases/{phase-dir}/index.json 읽기
2. feat-{phase-name} 브랜치 생성/checkout
3. CLAUDE.md + docs/*.md를 guardrails로 로딩
4. 첫 번째 pending step 찾기
5. [preamble + step 파일]을 Claude에 전달
6. 완료 → 2단계 커밋 (코드 feat: + 메타데이터 chore:)
7. 다음 pending step으로 반복
8. 모든 step 완료 → phase 완료 커밋
```

### 재시도 동작

```
attempt 1 → 실패 → error_message 기록 → status "pending" 초기화
attempt 2 → 이전 에러 메시지를 프롬프트에 피드백 → ...
attempt 3 → 최대 재시도 초과 → status "error" → 종료
```

### 출력 예시

```
============================================================
  Harness Step Executor
  Phase: 0-foundation | Steps: 2
============================================================
  Branch: feat-0-foundation
  ◐ Step 0/1 (0 done): project-setup [12s]
  ✓ Step 0: project-setup [47s]
  ◓ Step 1/1 (1 done): core-types [8s]
  ✓ Step 1: core-types [31s]

  All steps completed!
============================================================
  Phase '0-foundation' completed!
============================================================
```

---

## 7. 코드 리뷰: /review

Phase 완료 후 코드 품질을 검증한다.

```
/review
```

13개 항목을 체크한다:
- 아키텍처 준수 (디렉토리 구조, 에러 처리 패턴, 데이터 흐름)
- 코드 품질 (기술 스택, 타입 안전성, CRITICAL 규칙)
- 테스트 (새 테스트, 기존 테스트 통과)
- 보안 (인증 체크, 입력 검증, 환경변수 하드코딩)
- 빌드 & 린트

출력 형식:
```
### 최종 판정
- PASS: 모든 항목 통과 — 머지 가능
- FAIL: 위반 N개 — 수정 후 재리뷰
- WARN: 필수 위반 없음, 권장사항 N개
```

---

## 8. 에러 복구

### Error 상태 복구

```json
// phases/0-foundation/index.json 에서
{
  "step": 1,
  "name": "core-types",
  "status": "error",
  "error_message": "Cannot find module 'zod'"
}
```

**복구 절차:**
1. `error_message`를 읽고 원인 파악
2. `status`를 `"pending"`으로 변경
3. `error_message` 필드 삭제
4. 재실행: `python3 scripts/execute.py 0-foundation`

### Blocked 상태 복구

```json
{
  "status": "blocked",
  "blocked_reason": "NOTION_API_KEY 환경변수 미설정"
}
```

**복구 절차:**
1. `blocked_reason`에 적힌 사유 해결 (예: .env.local에 키 추가)
2. `status`를 `"pending"`으로 변경
3. `blocked_reason` 필드 삭제
4. 재실행

### 특정 Step 재실행

step N부터 다시 실행하고 싶을 때:
```json
// 해당 step과 이후 step을 모두 "pending"으로 변경
{ "step": 2, "status": "pending" }
```
단, 이전 step 코드를 수정했다면 `summary`도 업데이트한다.

---

## 9. 전체 워크플로우 요약

```
[프로젝트 시작]
   │
   ▼
① 핵심 문서 작성
   CLAUDE.md → PRD.md → ARCHITECTURE.md → ADR.md → UI_GUIDE.md
   │
   ▼
② Claude Code에서 /harness 실행
   Phase & Step 목록 제안 → 피드백 → 확정
   │
   ▼
③ scaffold.py로 파일 생성
   python3 scripts/scaffold.py 0-foundation project-setup core-types
   │
   ▼
④ step*.md 파일의 TODO 채우기
   "읽어야 할 파일" / "작업" / "AC" / "금지사항"
   │
   ▼
⑤ Dry-run으로 사전 검증
   python3 scripts/execute.py 0-foundation --dry-run
   │
   ▼
⑥ 실행
   python3 scripts/execute.py 0-foundation
   │
   ├─ 성공 → /review → 다음 phase로 이동
   │
   └─ 실패 → 에러 복구 → 재실행
```

---

## 10. 팁 & 베스트 프랙티스

### CLAUDE.md를 가장 먼저 채워라

execute.py가 CLAUDE.md를 모든 step에 주입한다.  
이 파일이 비어있으면 Claude 세션이 잘못된 가정을 하고 재작업이 발생한다.

### Step 설계는 Phase보다 먼저 결정하지 마라

/harness를 통해 전체 Phase 구조를 먼저 논의하고,  
승인 후 각 Phase를 scaffold하면서 Step을 구체화한다.

### Summary에 파일 경로와 인터페이스를 반드시 포함하라

```json
// 나쁜 summary
"summary": "인증 완료"

// 좋은 summary
"summary": "src/services/auth.ts 생성 — signIn(email, password), getSession() 익스포트. JWT 저장소: httpOnly cookie"
```

5 step 이상의 phase에서 summary 품질이 코드 일관성을 결정한다.

### 외부 API 연동 step에 --max-retries 5를 쓰라

Notion, YouTube 등 외부 API 연동은 rate limit이나 네트워크 문제로 실패할 수 있다.  
기본 3회로 부족하면:
```bash
python3 scripts/execute.py 2-notion --max-retries 5
```

### /review는 PR 전에 반드시 실행하라

execute.py가 생성한 코드가 항상 완벽하지 않다.  
보안(인증 누락, 시크릿 하드코딩)은 /review가 잡아낸다.

### blocked를 두려워하지 마라

API 키가 없거나 외부 서비스 설정이 필요한 경우,  
Claude 세션이 `blocked` 상태로 중단하는 것이 올바른 동작이다.  
blocked는 에러가 아니라 **인간 개입 요청**이다.
