#!/usr/bin/env python3
"""
Harness Step Executor — phase 내 step을 순차 실행하고 자가 교정한다.

Usage:
    python3 scripts/execute.py <phase-dir> [--push] [--dry-run] [--no-report]
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# HTML 리포트 CSS (외부 CDN 없음, 인라인 전용)
# ---------------------------------------------------------------------------

_HTML_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f8f9fa; color: #212529; line-height: 1.5; }
.container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }
h2 { font-size: 1.1rem; font-weight: 600; margin: 28px 0 12px; color: #343a40; }
.subtitle { color: #6c757d; font-size: 0.9rem; margin-bottom: 24px; }

/* 카드 */
.card { background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
        padding: 20px; margin-bottom: 20px; }
.stats { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-box { background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
            padding: 14px 20px; min-width: 120px; text-align: center; }
.stat-box .val { font-size: 1.8rem; font-weight: 700; }
.stat-box .lbl { font-size: 0.75rem; color: #6c757d; text-transform: uppercase; letter-spacing: .05em; }
.val.green { color: #198754; }
.val.red   { color: #dc3545; }
.val.orange{ color: #fd7e14; }
.val.blue  { color: #0d6efd; }

/* 표 */
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th { background: #f1f3f5; text-align: left; padding: 8px 10px;
     border-bottom: 2px solid #dee2e6; font-weight: 600; white-space: nowrap; }
td { padding: 8px 10px; border-bottom: 1px solid #f1f3f5; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8f9fa; }

/* 배지 */
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
.badge-completed { background: #d1e7dd; color: #0f5132; }
.badge-error     { background: #f8d7da; color: #842029; }
.badge-blocked   { background: #fff3cd; color: #664d03; }
.badge-pending   { background: #e2e3e5; color: #41464b; }

/* 토큰 바차트 */
.bar-wrap { display: flex; height: 18px; border-radius: 4px; overflow: hidden;
            background: #e9ecef; min-width: 80px; }
.bar-preamble { background: #6ea8fe; }
.bar-step     { background: #20c997; }
.bar-label    { font-size: 0.75rem; color: #6c757d; margin-top: 2px; }

/* 절감률 요약 박스 */
.savings-box { background: #d1e7dd; border: 1px solid #a3cfbb;
               border-radius: 8px; padding: 16px 20px; margin-top: 16px; }
.savings-box .big { font-size: 2rem; font-weight: 800; color: #0f5132; }
.savings-box p { color: #0f5132; font-size: 0.9rem; margin-top: 4px; }

/* 에러 로그 */
details { margin-bottom: 10px; }
details summary { cursor: pointer; font-weight: 600; padding: 8px;
                  background: #f8d7da; border-radius: 6px; color: #842029; }
details[open] summary { border-radius: 6px 6px 0 0; }
pre { background: #212529; color: #f8f9fa; padding: 14px; border-radius: 0 0 6px 6px;
      font-size: 0.8rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
.raw-json summary { background: #e2e3e5; color: #41464b; }
.raw-json pre { background: #f8f9fa; color: #212529; border: 1px solid #dee2e6; }

/* 집계 표 링크 */
a { color: #0d6efd; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def _fmt_duration(started: Optional[str], ended: Optional[str]) -> str:
    """ISO 타임스탬프 두 개를 받아 'Xm Ys' 형식으로 반환한다."""
    if not started or not ended:
        return "—"
    try:
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        s = datetime.strptime(started, fmt)
        e = datetime.strptime(ended, fmt)
        secs = int((e - s).total_seconds())
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"
    except Exception:
        return "—"


def _build_phase_html(index: dict, phase_dir: str) -> str:
    """phases/{phase}/index.json 데이터를 받아 self-contained HTML 문자열을 반환한다."""
    project = index.get("project", "Project")
    phase = index.get("phase", phase_dir)
    steps = index.get("steps", [])
    created = index.get("created_at", "")
    completed = index.get("completed_at", "")
    duration = _fmt_duration(created, completed)

    n_completed = sum(1 for s in steps if s.get("status") == "completed")
    n_error = sum(1 for s in steps if s.get("status") == "error")
    n_blocked = sum(1 for s in steps if s.get("status") == "blocked")
    n_total = len(steps)

    BASELINE_TOKENS = 40_000  # 160K chars / 4 — 단일 세션 기준
    total_tokens = sum(s.get("token_metrics", {}).get("total_tokens", 0) for s in steps)
    savings_pct = round((1 - total_tokens / BASELINE_TOKENS) * 100, 1) if total_tokens > 0 else 0

    # --- Step 타임라인 표 ---
    timeline_rows = []
    for s in steps:
        status = s.get("status", "pending")
        badge = f'<span class="badge badge-{status}">{status}</span>'
        summary = s.get("summary", "—")
        if len(summary) > 100:
            summary = f'<span title="{summary}">{summary[:100]}…</span>'
        tm = s.get("token_metrics")
        tok_cell = f"{tm['total_tokens']:,}" if tm else "—"
        dur = _fmt_duration(s.get("started_at"), s.get("completed_at") or s.get("failed_at") or s.get("blocked_at"))
        started_short = (s.get("started_at") or "—")[:16].replace("T", " ")
        timeline_rows.append(
            f"<tr><td>{s.get('step','')}</td><td>{s.get('name','')}</td>"
            f"<td>{started_short}</td><td>{dur}</td><td>{badge}</td>"
            f"<td style='max-width:280px'>{summary}</td><td style='text-align:right'>{tok_cell}</td></tr>"
        )

    # --- 토큰 바차트 ---
    bar_rows = []
    max_tok = max((s.get("token_metrics", {}).get("total_tokens", 0) for s in steps), default=1) or 1
    for s in steps:
        tm = s.get("token_metrics")
        if not tm:
            bar_rows.append(
                f"<tr><td>{s.get('step','')}</td><td>{s.get('name','')}</td>"
                f"<td colspan='3' style='color:#6c757d'>—</td><td>—</td></tr>"
            )
            continue
        pt, st, tt, att = tm["preamble_tokens"], tm["step_tokens"], tm["total_tokens"], tm.get("attempt", 1)
        pct_p = round(pt / max_tok * 100)
        pct_s = round(st / max_tok * 100)
        bar = (f'<div class="bar-wrap" style="width:180px">'
               f'<div class="bar-preamble" style="width:{pct_p}%"></div>'
               f'<div class="bar-step" style="width:{pct_s}%"></div>'
               f'</div><div class="bar-label">preamble {pt:,} + step {st:,}</div>')
        bar_rows.append(
            f"<tr><td>{s.get('step','')}</td><td>{s.get('name','')}</td>"
            f"<td>{bar}</td><td style='text-align:right'>{tt:,}</td><td style='text-align:right'>{att}</td></tr>"
        )

    # 절감률 박스
    if total_tokens > 0:
        savings_html = (
            f'<div class="savings-box">'
            f'<div class="big">{savings_pct}% 절감</div>'
            f'<p>이번 phase 추정 합계 <strong>{total_tokens:,} tokens</strong> vs '
            f'단일 세션 기준 <strong>{BASELINE_TOKENS:,} tokens</strong></p>'
            f'<p style="font-size:0.8rem;margin-top:6px;opacity:.8">'
            f'※ 토큰 수는 문자수 ÷ 4 휴리스틱 추정값입니다.</p>'
            f'</div>'
        )
    else:
        savings_html = '<p style="color:#6c757d">토큰 데이터 없음 (dry-run 또는 구버전 실행)</p>'

    # --- 에러 로그 ---
    error_steps = [s for s in steps if s.get("status") == "error" or s.get("error_message")]
    error_section = ""
    if error_steps:
        error_items = []
        for s in error_steps:
            msg = s.get("error_message", "(no message)")
            att = s.get("token_metrics", {}).get("attempt", "?")
            error_items.append(
                f'<details><summary>Step {s.get("step")} — {s.get("name")} '
                f'(시도 {att}회)</summary>'
                f'<pre>{msg}</pre></details>'
            )
        error_section = (
            f'<h2>⚠ 에러 로그</h2>'
            f'<div class="card">{"".join(error_items)}</div>'
        )

    # --- Raw JSON ---
    raw_json = json.dumps(index, indent=2, ensure_ascii=False)

    now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness Report — {phase}</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<div class="container">
  <h1>Harness 실행 리포트</h1>
  <p class="subtitle">{project} / {phase} &nbsp;·&nbsp; 생성: {now_str}</p>

  <div class="stats">
    <div class="stat-box"><div class="val blue">{n_total}</div><div class="lbl">Total Steps</div></div>
    <div class="stat-box"><div class="val green">{n_completed}</div><div class="lbl">Completed</div></div>
    <div class="stat-box"><div class="val red">{n_error}</div><div class="lbl">Error</div></div>
    <div class="stat-box"><div class="val orange">{n_blocked}</div><div class="lbl">Blocked</div></div>
    <div class="stat-box"><div class="val blue">{duration}</div><div class="lbl">Duration</div></div>
  </div>

  <h2>Step 타임라인</h2>
  <div class="card" style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>#</th><th>Name</th><th>Started</th><th>Duration</th>
        <th>Status</th><th>Summary</th><th>Est. Tokens</th>
      </tr></thead>
      <tbody>{"".join(timeline_rows)}</tbody>
    </table>
  </div>

  <h2>토큰 효율 분석</h2>
  <div class="card" style="overflow-x:auto">
    <p style="font-size:0.82rem;color:#6c757d;margin-bottom:12px">
      <span style="display:inline-block;width:12px;height:12px;background:#6ea8fe;border-radius:2px"></span> Preamble (guardrails + 이전 step 요약) &nbsp;
      <span style="display:inline-block;width:12px;height:12px;background:#20c997;border-radius:2px"></span> Step 파일
    </p>
    <table>
      <thead><tr>
        <th>#</th><th>Name</th><th>Token 분포</th>
        <th style="text-align:right">Total</th><th style="text-align:right">Attempt</th>
      </tr></thead>
      <tbody>{"".join(bar_rows)}</tbody>
    </table>
    {savings_html}
  </div>

  {error_section}

  <h2>Raw JSON</h2>
  <details class="raw-json">
    <summary>index.json 전체 보기</summary>
    <pre>{raw_json}</pre>
  </details>
</div>
</body>
</html>"""


def _build_aggregate_html(phases_data: list) -> str:
    """모든 phase 데이터를 받아 집계 HTML을 반환한다.
    phases_data: [{"dir": str, "status": str, "index": dict|None}, ...]
    """
    now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    BASELINE_TOKENS = 40_000

    rows = []
    grand_total_tokens = 0
    for p in phases_data:
        d = p["dir"]
        status = p["status"]
        idx = p.get("index") or {}
        steps = idx.get("steps", [])
        n_done = sum(1 for s in steps if s.get("status") == "completed")
        n_total = len(steps)
        phase_tokens = sum(s.get("token_metrics", {}).get("total_tokens", 0) for s in steps)
        grand_total_tokens += phase_tokens
        dur = _fmt_duration(idx.get("created_at"), idx.get("completed_at"))
        tok_str = f"{phase_tokens:,}" if phase_tokens else "—"
        badge = f'<span class="badge badge-{status}">{status}</span>'
        report_link = f'<a href="{d}/report.html">report.html</a>'
        rows.append(
            f"<tr><td>{d}</td><td>{badge}</td><td>{n_done}/{n_total}</td>"
            f"<td>{dur}</td><td style='text-align:right'>{tok_str}</td><td>{report_link}</td></tr>"
        )

    grand_savings = round((1 - grand_total_tokens / (BASELINE_TOKENS * max(len(phases_data), 1))) * 100, 1) if grand_total_tokens > 0 else 0

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness 집계 리포트</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<div class="container">
  <h1>Harness 프로젝트 집계 리포트</h1>
  <p class="subtitle">생성: {now_str}</p>

  <div class="card" style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Phase</th><th>Status</th><th>Steps (완료/전체)</th>
        <th>소요시간</th><th style="text-align:right">총 Tokens</th><th>리포트</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>

  {"" if grand_total_tokens == 0 else f'''<div class="savings-box">
    <div class="big">{grand_savings}% 절감 (전체 평균)</div>
    <p>전체 phase 추정 합계 <strong>{grand_total_tokens:,} tokens</strong>
       vs 단일 세션 기준 <strong>{BASELINE_TOKENS * len(phases_data):,} tokens</strong></p>
  </div>'''}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 진행 표시기
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def progress_indicator(label: str):
    """터미널 진행 표시기. with 문으로 사용하며 .elapsed 로 경과 시간을 읽는다."""
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


# ---------------------------------------------------------------------------
# StepExecutor
# ---------------------------------------------------------------------------

class StepExecutor:
    """Phase 디렉토리 안의 step들을 순차 실행하는 하네스."""

    MAX_RETRIES = 3
    FEAT_MSG = "feat({phase}): step {num} — {name}"
    CHORE_MSG = "chore({phase}): step {num} output"
    TZ = timezone(timedelta(hours=9))

    def __init__(self, phase_dir_name: str, *, auto_push: bool = False,
                 dry_run: bool = False, max_retries: int = 3,
                 generate_report: bool = True):
        self._root = str(ROOT)
        self._phases_dir = ROOT / "phases"
        self._phase_dir = self._phases_dir / phase_dir_name
        self._phase_dir_name = phase_dir_name
        self._top_index_file = self._phases_dir / "index.json"
        self._auto_push = auto_push
        self._dry_run = dry_run
        self._generate_report = generate_report
        self._dry_run_metrics: list = []
        self.MAX_RETRIES = max_retries

        if not self._phase_dir.is_dir():
            print(f"ERROR: {self._phase_dir} not found")
            sys.exit(1)

        self._index_file = self._phase_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", phase_dir_name)
        self._total = len(idx["steps"])

    def run(self):
        self._print_header()
        self._check_blockers()
        self._checkout_branch()
        guardrails = self._load_guardrails()
        self._ensure_created_at()
        self._execute_all_steps(guardrails)
        self._finalize()

    # --- 토큰 추정 ---

    @staticmethod
    def _measure_tokens(text: str) -> int:
        """문자수 / 4 로 토큰 수를 추정한다 (Claude/GPT 공통 휴리스틱)."""
        return len(text) // 4

    # --- timestamps ---

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- JSON I/O ---

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- git ---

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True)

    def _checkout_branch(self):
        branch = f"feat-{self._phase_name}"

        if self._dry_run:
            print(f"  [dry-run] Would checkout branch: {branch}")
            return

        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        if r.stdout.strip() == branch:
            return

        r = self._run_git("rev-parse", "--verify", branch)
        r = self._run_git("checkout", branch) if r.returncode == 0 else self._run_git("checkout", "-b", branch)

        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패.")
            print(f"  {r.stderr.strip()}")
            print(f"  Hint: 변경사항을 stash하거나 commit한 후 다시 시도하세요.")
            sys.exit(1)

        print(f"  Branch: {branch}")

    def _commit_step(self, step_num: int, step_name: str):
        output_rel = f"phases/{self._phase_dir_name}/step{step_num}-output.json"
        index_rel = f"phases/{self._phase_dir_name}/index.json"

        self._run_git("add", "-A")
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.FEAT_MSG.format(phase=self._phase_name, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.CHORE_MSG.format(phase=self._phase_name, num=step_num)
            r = self._run_git("commit", "-m", msg)
            if r.returncode != 0:
                print(f"  WARN: housekeeping 커밋 실패: {r.stderr.strip()}")

    # --- top-level index ---

    def _update_top_index(self, status: str):
        if not self._top_index_file.exists():
            return
        top = self._read_json(self._top_index_file)
        ts = self._stamp()
        for phase in top.get("phases", []):
            if phase.get("dir") == self._phase_dir_name:
                phase["status"] = status
                ts_key = {"completed": "completed_at", "error": "failed_at", "blocked": "blocked_at"}.get(status)
                if ts_key:
                    phase[ts_key] = ts
                break
        self._write_json(self._top_index_file, top)

    # --- guardrails & context ---

    def _load_guardrails(self) -> str:
        sections = []
        claude_md = ROOT / "CLAUDE.md"
        if claude_md.exists():
            sections.append(f"## 프로젝트 규칙 (CLAUDE.md)\n\n{claude_md.read_text()}")
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            for doc in sorted(docs_dir.glob("*.md")):
                sections.append(f"## {doc.stem}\n\n{doc.read_text()}")
        return "\n\n---\n\n".join(sections) if sections else ""

    @staticmethod
    def _build_step_context(index: dict) -> str:
        lines = [
            f"- Step {s['step']} ({s['name']}): {s['summary']}"
            for s in index["steps"]
            if s["status"] == "completed" and s.get("summary")
        ]
        if not lines:
            return ""
        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(self, guardrails: str, step_context: str,
                        prev_error: Optional[str] = None) -> str:
        commit_example = self.FEAT_MSG.format(
            phase=self._phase_name, num="N", name="<step-name>"
        )
        retry_section = ""
        if prev_error:
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{prev_error}\n\n---\n\n"
            )
        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrails}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria) 검증을 직접 실행하라.\n"
            f"5. /phases/{self._phase_dir_name}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약\n"
            f"   - {self.MAX_RETRIES}회 수정 시도 후에도 실패 → \"error\" + \"error_message\" 기록\n"
            f"   - 사용자 개입이 필요한 경우 (API 키, 인증, 수동 설정 등) → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 모든 변경사항을 커밋하라:\n"
            f"   {commit_example}\n\n---\n\n"
        )

    # --- Claude 호출 ---

    def _invoke_claude(self, step: dict, preamble: str) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._phase_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        step_file_text = step_file.read_text(encoding="utf-8")

        if self._dry_run:
            p_tok = self._measure_tokens(preamble)
            s_tok = self._measure_tokens(step_file_text)
            total_tok = p_tok + s_tok
            print(f"  [dry-run] Step {step_num} ({step_name})")
            print(f"    Preamble : {len(preamble):>8,} chars  (~{p_tok:,} tokens)")
            print(f"    Step file: {len(step_file_text):>8,} chars  (~{s_tok:,} tokens)")
            print(f"    Total    : {len(preamble)+len(step_file_text):>8,} chars  (~{total_tok:,} tokens)")
            self._dry_run_metrics.append({
                "step": step_num, "name": step_name,
                "preamble_tokens": p_tok, "step_tokens": s_tok, "total_tokens": total_tok,
            })
            return {"step": step_num, "name": step_name, "exitCode": 0,
                    "stdout": "", "stderr": "", "dry_run": True}

        prompt = preamble + step_file_text
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "json", prompt],
            cwd=self._root, capture_output=True, text=True, timeout=1800,
        )

        if result.returncode != 0:
            print(f"\n  WARN: Claude가 비정상 종료됨 (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")

        output = {
            "step": step_num, "name": step_name,
            "exitCode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
        out_path = self._phase_dir / f"step{step_num}-output.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output

    # --- 헤더 & 검증 ---

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Phase: {self._phase_name} | Steps: {self._total}")
        if self._dry_run:
            print(f"  Mode: DRY-RUN (Claude 호출 생략)")
        if self._auto_push:
            print(f"  Auto-push: enabled")
        if self.MAX_RETRIES != 3:
            print(f"  Max retries: {self.MAX_RETRIES}")
        if self._generate_report and not self._dry_run:
            print(f"  Report: enabled")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # --- 실행 루프 ---

    def _execute_single_step(self, step: dict, guardrails: str) -> bool:
        """단일 step 실행 (재시도 포함). 완료되면 True, 실패/차단이면 False."""
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")
        prev_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            index = self._read_json(self._index_file)
            step_context = self._build_step_context(index)
            preamble = self._build_preamble(guardrails, step_context, prev_error)

            # 토큰 측정 (Claude 호출 전)
            step_file = self._phase_dir / f"step{step_num}.md"
            step_file_text = step_file.read_text(encoding="utf-8") if step_file.exists() else ""
            preamble_tokens = self._measure_tokens(preamble)
            step_tokens = self._measure_tokens(step_file_text)
            total_tokens = preamble_tokens + step_tokens

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            with progress_indicator(tag) as pi:
                self._invoke_claude(step, preamble)
                elapsed = int(pi.elapsed)

            if self._dry_run:
                print(f"  [dry-run] Step {step_num}: {step_name} — skipping Claude call")
                return True

            index = self._read_json(self._index_file)
            status = next((s.get("status", "pending") for s in index["steps"] if s["step"] == step_num), "pending")
            ts = self._stamp()

            if status == "completed":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["completed_at"] = ts
                        s["token_metrics"] = {
                            "preamble_tokens": preamble_tokens,
                            "step_tokens": step_tokens,
                            "total_tokens": total_tokens,
                            "attempt": attempt,
                        }
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]  (~{total_tokens:,} tokens)")
                return True

            if status == "blocked":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["blocked_at"] = ts
                self._write_json(self._index_file, index)
                reason = next((s.get("blocked_reason", "") for s in index["steps"] if s["step"] == step_num), "")
                print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                print(f"    Reason: {reason}")
                self._update_top_index("blocked")
                sys.exit(2)

            err_msg = next(
                (s.get("error_message", "Step did not update status") for s in index["steps"] if s["step"] == step_num),
                "Step did not update status",
            )

            if attempt < self.MAX_RETRIES:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "pending"
                        s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"\n  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES}")
                print(f"  {'─'*52}")
                for line in err_msg.splitlines()[:10]:
                    print(f"  {line}")
                print(f"  {'─'*52}\n")
            else:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "error"
                        s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                        s["failed_at"] = ts
                        s["token_metrics"] = {
                            "preamble_tokens": preamble_tokens,
                            "step_tokens": step_tokens,
                            "total_tokens": total_tokens,
                            "attempt": attempt,
                        }
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                self._update_top_index("error")
                sys.exit(1)

        return False  # unreachable

    def _execute_all_steps(self, guardrails: str):
        while True:
            index = self._read_json(self._index_file)
            pending = next((s for s in index["steps"] if s["status"] == "pending"), None)
            if pending is None:
                print("\n  All steps completed!")
                if self._dry_run and self._dry_run_metrics:
                    self._print_dry_run_summary()
                return

            step_num = pending["step"]
            for s in index["steps"]:
                if s["step"] == step_num and "started_at" not in s:
                    s["started_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    break

            self._execute_single_step(pending, guardrails)

    def _print_dry_run_summary(self):
        """dry-run 완료 후 step별 토큰 추정 요약 표를 출력한다."""
        BASELINE_TOKENS = 40_000
        print(f"\n  {'─'*60}")
        print(f"  [dry-run] 토큰 추정 요약")
        print(f"  {'─'*60}")
        header = f"  {'Step':<5} {'Name':<25} {'Preamble':>10} {'Step':>8} {'Total':>8}"
        print(header)
        print(f"  {'─'*60}")
        grand_total = 0
        for m in self._dry_run_metrics:
            grand_total += m["total_tokens"]
            print(f"  {m['step']:<5} {m['name']:<25} "
                  f"~{m['preamble_tokens']:>8,} ~{m['step_tokens']:>6,} ~{m['total_tokens']:>6,}")
        savings = round((1 - grand_total / BASELINE_TOKENS) * 100, 1) if grand_total > 0 else 0
        print(f"  {'─'*60}")
        print(f"  단일 세션 기준(160K chars):  ~{BASELINE_TOKENS:>8,} tokens")
        print(f"  이번 phase 예상 합계:         ~{grand_total:>8,} tokens")
        print(f"  예상 절감률:                   {savings:>8.1f}%")
        print(f"  {'─'*60}\n")

    # --- HTML 리포트 생성 ---

    def _generate_html_report(self) -> Optional[Path]:
        """phases/{phase}/report.html을 생성한다. 실패 시 경고만 출력."""
        try:
            index = self._read_json(self._index_file)
            html = _build_phase_html(index, self._phase_dir_name)
            out = self._phase_dir / "report.html"
            out.write_text(html, encoding="utf-8")
            return out
        except Exception as e:
            print(f"  WARN: HTML 리포트 생성 실패: {e}")
            return None

    def _generate_aggregate_report(self) -> Optional[Path]:
        """phases/report.html — 모든 phase를 집계한 상위 리포트를 생성한다."""
        try:
            if not self._top_index_file.exists():
                return None
            top = self._read_json(self._top_index_file)
            phases_data = []
            for p in top.get("phases", []):
                phase_idx_file = self._phases_dir / p["dir"] / "index.json"
                idx = self._read_json(phase_idx_file) if phase_idx_file.exists() else None
                phases_data.append({"dir": p["dir"], "status": p.get("status", "pending"), "index": idx})
            if not phases_data:
                return None
            html = _build_aggregate_html(phases_data)
            out = self._phases_dir / "report.html"
            out.write_text(html, encoding="utf-8")
            return out
        except Exception as e:
            print(f"  WARN: 집계 리포트 생성 실패: {e}")
            return None

    def _finalize(self):
        index = self._read_json(self._index_file)
        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = f"chore({self._phase_name}): mark phase completed"
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  ✓ {msg}")

        if self._auto_push:
            branch = f"feat-{self._phase_name}"
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        if self._generate_report and not self._dry_run:
            report_path = self._generate_html_report()
            if report_path:
                print(f"  ✓ Report: {report_path.relative_to(ROOT)}")
            agg_path = self._generate_aggregate_report()
            if agg_path:
                print(f"  ✓ Aggregate: {agg_path.relative_to(ROOT)}")

        print(f"\n{'='*60}")
        print(f"  Phase '{self._phase_name}' completed!")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", help="Phase directory name (e.g. 0-mvp)")
    parser.add_argument("--push", action="store_true", help="Push branch after completion")
    parser.add_argument("--dry-run", action="store_true",
                        help="Claude를 호출하지 않고 step 파일 존재·guardrails 로딩만 검증")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Step당 최대 재시도 횟수 (기본값: 3)")
    parser.add_argument("--no-report", dest="report", action="store_false", default=True,
                        help="HTML 리포트 생성 비활성화 (기본값: 활성화)")
    args = parser.parse_args()

    StepExecutor(args.phase_dir, auto_push=args.push,
                 dry_run=args.dry_run, max_retries=args.max_retries,
                 generate_report=args.report).run()


if __name__ == "__main__":
    main()
