# 프로젝트: {프로젝트명}

## 기술 스택
- {프레임워크 (예: Next.js 15)}
- {언어 (예: TypeScript strict mode)}
- {스타일링 (예: Tailwind CSS)}

## 아키텍처 규칙
- CRITICAL: {절대 지켜야 할 규칙 1 (예: 모든 API 로직은 app/api/ 라우트 핸들러에서만 처리)}
- CRITICAL: {절대 지켜야 할 규칙 2 (예: 클라이언트 컴포넌트에서 직접 외부 API를 호출하지 말 것)}
- {일반 규칙 (예: 컴포넌트는 components/ 폴더에, 타입은 types/ 폴더에 분리)}

## 개발 프로세스
- CRITICAL: 새 기능 구현 시 반드시 테스트를 먼저 작성하고, 테스트가 통과하는 구현을 작성할 것 (TDD)
- 커밋 메시지는 conventional commits 형식을 따를 것 (feat:, fix:, docs:, refactor:)

## 명령어
npm run dev      # 개발 서버
npm run build    # 프로덕션 빌드
npm run lint     # ESLint
npm run test     # 테스트

## 환경 변수
- 필수: {예: DATABASE_URL, NEXTAUTH_SECRET}
- 절대 코드에 하드코딩 금지 — process.env.* 만 사용
- .env.local은 gitignore됨. .env.example에 키 목록 유지

## 테스트 전략
- 단위 테스트: {예: src/**/*.test.ts — 순수 함수, 유틸리티}
- 통합 테스트: {예: API Route는 supertest로}
- E2E: {예: 이번 MVP에서는 작성 안 함}
- 커버리지 목표: {예: 핵심 비즈니스 로직 80% 이상}

## 성능 제약
- CRITICAL: {예: 첫 페이지 로드 LCP 2.5초 이하}
- {예: API 응답은 500ms 이하 목표}

## 보안 규칙
- CRITICAL: {예: 모든 API Route에서 세션 검증 필수}
- {예: SQL 쿼리는 parameterized query만 사용}
- {예: 사용자 입력은 zod로 반드시 검증}

## 의존성 관리
- 새 패키지 추가 전 ADR에 근거 확인 필수
- {예: ORM은 Prisma 고정. 다른 DB 클라이언트 사용 금지}
