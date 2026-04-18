#!/usr/bin/env python3
"""
Harness Phase Scaffolder — phases/ 디렉토리와 step 파일을 자동으로 생성한다.

Usage:
    python3 scripts/scaffold.py <phase-name> <step-name> [<step-name> ...]

Example:
    python3 scripts/scaffold.py 0-mvp project-setup core-types api-layer

생성 결과:
    phases/index.json                    (없으면 신규, 있으면 항목 추가)
    phases/0-mvp/index.json
    phases/0-mvp/step0.md               (step-name: project-setup)
    phases/0-mvp/step1.md               (step-name: core-types)
    phases/0-mvp/step2.md               (step-name: api-layer)
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data: dict):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _step_template(phase_name: str, step_num: int, step_name: str, total: int) -> str:
    prev_files = ""
    if step_num > 0:
        prev_files = f"- 이전 step에서 생성/수정된 파일 (index.json의 summary 참고)\n"

    return f"""\
# Step {step_num}: {step_name}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
{prev_files}
## 작업

{{TODO: 구체적인 구현 지시를 여기에 작성}}
{{파일 경로, 함수/클래스 시그니처, 핵심 로직 설명 포함}}
{{구현체 상세는 에이전트 재량이지만, 설계 의도에서 벗어나면 안 되는 규칙은 명시}}

## Acceptance Criteria

```bash
npm run build   # 컴파일 에러 없음
npm test        # 테스트 통과
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조를 따르는가?
   - ADR 기술 스택을 벗어나지 않았는가?
   - CLAUDE.md CRITICAL 규칙을 위반하지 않았는가?
3. `phases/{phase_name}/index.json`의 step {step_num}을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- {{TODO: "X를 하지 마라. 이유: Y" 형식으로 작성}}
- 기존 테스트를 깨뜨리지 마라.
"""


def scaffold(phase_name: str, step_names: list[str]):
    phases_dir = ROOT / "phases"
    phase_dir = phases_dir / phase_name
    top_index_file = phases_dir / "index.json"

    # phases/ 디렉토리 생성
    phases_dir.mkdir(exist_ok=True)

    # phases/index.json 생성 또는 업데이트
    if top_index_file.exists():
        top = _read_json(top_index_file)
        existing_dirs = {p.get("dir") for p in top.get("phases", [])}
        if phase_name in existing_dirs:
            print(f"  ERROR: phases/index.json에 이미 '{phase_name}'이 존재합니다.")
            sys.exit(1)
        top.setdefault("phases", []).append({"dir": phase_name, "status": "pending"})
        _write_json(top_index_file, top)
        print(f"  Updated: phases/index.json (항목 추가: {phase_name})")
    else:
        _write_json(top_index_file, {"phases": [{"dir": phase_name, "status": "pending"}]})
        print(f"  Created: phases/index.json")

    # phases/{phase-name}/ 디렉토리 생성
    if phase_dir.exists():
        print(f"  ERROR: {phase_dir} 이미 존재합니다. 덮어쓰지 않습니다.")
        sys.exit(1)
    phase_dir.mkdir()

    # phases/{phase-name}/index.json 생성
    steps = [
        {"step": i, "name": name, "status": "pending"}
        for i, name in enumerate(step_names)
    ]
    # project 필드는 CLAUDE.md에서 가져오거나 placeholder 사용
    project_name = "{프로젝트명}"
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text(encoding="utf-8").splitlines():
            if line.startswith("# 프로젝트:"):
                project_name = line.split(":", 1)[1].strip()
                break

    phase_index = {
        "project": project_name,
        "phase": phase_name,
        "steps": steps,
    }
    _write_json(phase_dir / "index.json", phase_index)
    print(f"  Created: phases/{phase_name}/index.json ({len(steps)} steps)")

    # step{N}.md 파일 생성
    for i, name in enumerate(step_names):
        step_file = phase_dir / f"step{i}.md"
        step_file.write_text(
            _step_template(phase_name, i, name, len(step_names)),
            encoding="utf-8",
        )
        print(f"  Created: phases/{phase_name}/step{i}.md  ({name})")

    print(f"\n  Done! Phase '{phase_name}' scaffolded with {len(step_names)} steps.")
    print(f"\n  다음 단계:")
    print(f"    1. phases/{phase_name}/step*.md 파일의 TODO 섹션을 채워라.")
    print(f"    2. python3 scripts/execute.py {phase_name} --dry-run  # 사전 검증")
    print(f"    3. python3 scripts/execute.py {phase_name}            # 실행")


def main():
    parser = argparse.ArgumentParser(
        description="Harness Phase Scaffolder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python3 scripts/scaffold.py 0-mvp project-setup core-types api-layer",
    )
    parser.add_argument("phase_name", help="Phase 디렉토리명 (예: 0-mvp)")
    parser.add_argument("step_names", nargs="+", help="Step 이름 목록 (kebab-case)")
    args = parser.parse_args()

    # kebab-case 검증
    import re
    for name in [args.phase_name] + args.step_names:
        if not re.match(r"^[a-z0-9][a-z0-9\-]*$", name):
            print(f"  ERROR: '{name}'은 kebab-case가 아닙니다. (소문자, 숫자, 하이픈만 허용)")
            sys.exit(1)

    print(f"\n  Scaffolding phase '{args.phase_name}' with {len(args.step_names)} steps...")
    scaffold(args.phase_name, args.step_names)


if __name__ == "__main__":
    main()
