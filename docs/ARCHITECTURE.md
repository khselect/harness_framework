# 아키텍처

## 디렉토리 구조
```
src/
├── app/               # 페이지 + API 라우트
├── components/        # UI 컴포넌트
├── types/             # TypeScript 타입 정의
├── lib/               # 유틸리티 + 헬퍼
└── services/          # 외부 API 래퍼
```

## 패턴
{사용하는 디자인 패턴 (예: Server Components 기본, 인터랙션이 필요한 곳만 Client Component)}

## 데이터 흐름
```
{데이터가 어떻게 흐르는지 (예:
사용자 입력 → Client Component → API Route → 외부 API → 응답 → UI 업데이트
)}
```

## 상태 관리
{상태 관리 방식 (예: 서버 상태는 Server Components, 클라이언트 상태는 useState/useReducer)}

## 에러 처리 패턴
```typescript
// API Route 에러 응답 형식 — 모든 Route가 이 구조를 따를 것
// {예:
type ApiError = {
  error: string       // 사용자에게 보여줄 메시지
  code: string        // 클라이언트 분기용 에러 코드 (예: "UNAUTHORIZED")
  details?: unknown   // 개발 환경에서만 노출
}
// }
```

HTTP 상태 코드 규칙:
- 400: 입력 유효성 오류 (zod parse 실패 등)
- 401: 미인증
- 403: 권한 없음
- 404: 리소스 없음
- 500: 서버 내부 오류 (상세는 서버 로그에만, 응답에 포함 금지)

## 보안 패턴
- 인증 체크: {예: 모든 /api/user/* Route는 getServerSession()으로 세션 검증 후 userId 추출}
- 입력 검증: {예: Request body는 항상 z.parse()로 검증. 실패 시 400 반환}
- 데이터 노출 범위: {예: DB User 모델에서 password, salt 필드는 절대 API 응답에 포함 안 함}
