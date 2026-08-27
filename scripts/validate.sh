#!/usr/bin/env bash
# Local gate for trading-futures-scalp-bot.
#
#   ./scripts/validate.sh            # human-readable run
#   ./scripts/validate.sh --json     # per-check machine-readable results
#   ./scripts/validate.sh --strict   # treat a skipped check as a failure
#
# SCOPE, HONESTLY STATED
# ----------------------
# This gate covers the safety layer, syntax and import resolution. It does NOT
# prove the bots run.
#
# The March 2026 reorganisation moved modules into core/ and bots/*/ but left
# every import flat. Those imports DO resolve when all four source directories
# are on sys.path -- which is what conftest.py arranges for tests, and what
# `imports` below checks. They do NOT resolve when a bot is launched directly
# (python bots/momentum_scalp/momentum_scalp_main.py), because Python then puts
# only that one directory on the path. Repairing the runtime layout is separate
# work this gate does not attempt and does not pretend to cover.
#
# Nothing here contacts a broker, reads credentials, or places an order.
set -uo pipefail

cd "$(dirname "$0")/.."

JSON=0
STRICT=0
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    --strict) STRICT=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

FAIL=0
LOGDIR=".loop/logs"
rm -rf "$LOGDIR"; mkdir -p "$LOGDIR"
RESULTS=()

if [ "$JSON" -eq 1 ]; then step() { :; }; else step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }; fi

record() {
  RESULTS+=("$1|$2|$3")
  case "$2" in
    fail) FAIL=1 ;;
    skip) [ "$STRICT" -eq 1 ] && FAIL=1 ;;
  esac
  return 0
}

first_error() {
  local line
  line=$(grep -m1 -aE 'AssertionError|ModuleNotFoundError|Error|error|FAILED|failed' "$1" 2>/dev/null)
  [ -n "$line" ] || line=$(grep -m1 -a '[^[:space:]]' "$1" 2>/dev/null)
  printf '%s' "$line" | tr -d '"\\' | tr -s '[:space:]' ' ' | cut -c1-160
}

check() {
  local id="$1" bin="$2" label="$3"; shift 4
  local log="$LOGDIR/$id.log" rc=0
  if [ "$bin" != "-" ] && ! command -v "$bin" >/dev/null; then
    printf 'skipped: %s not installed\n' "$bin" >"$log"
    [ "$JSON" -eq 1 ] || printf '    \033[2mskipped: %s not installed\033[0m\n' "$bin"
    record "$id" skip "$bin not installed"; return 0
  fi
  "$@" >"$log" 2>&1 || rc=$?
  [ "$JSON" -eq 1 ] || cat "$log"
  if [ "$rc" -ne 0 ]; then
    [ "$JSON" -eq 1 ] || printf '\033[31m    FAILED: %s\033[0m\n' "$label"
    record "$id" fail "$(first_error "$log")"
  else
    record "$id" pass ""
  fi
  return 0
}

# --- safety tests ---------------------------------------------------------
# The only real behavioural coverage in this repo. Mutation-verified: each
# guard, when disabled, turns at least one of these red.
step "safety tests"
check safety-tests python3 "safety tests" -- python3 -m pytest tests/ -q

# --- syntax ---------------------------------------------------------------
step "syntax"
syntax_all() {
  local bad=0
  while IFS= read -r f; do
    python3 -m py_compile "$f" 2>&1 || { echo "SYNTAX FAILED: $f"; bad=1; }
  done < <(find core bots analysis tests -name '*.py' -not -path '*/__pycache__/*' 2>/dev/null)
  return $bad
}
check syntax - "syntax" -- syntax_all

# --- import health --------------------------------------------------------
# Reports the known post-reorg breakage instead of hiding it.
#
# STATIC ONLY. An earlier version of this check imported each module to see if
# it resolved -- which executed module-level code, and importing
# bots/schwab_0dte/schwab_8081_fixed.py launched an interactive Schwab auth
# prompt (it has no __main__ guard). A checker must never run code that can
# reach a broker. This parses the AST and resolves module names with
# find_spec; it executes nothing.
step "imports"
import_health() {
  python3 - <<'PYEOF'
import ast, os, pathlib, sys
from importlib.util import find_spec

root = os.getcwd()
DIRS = ("core", "bots/momentum_scalp", "bots/schwab_0dte", "bots/tradovate")
for rel in DIRS:
    p = os.path.join(root, rel)
    if os.path.isdir(p):
        sys.path.insert(0, p)

# Local module names this repo provides, by stem.
local = set()
for rel in DIRS:
    for f in pathlib.Path(rel).glob("*.py") if pathlib.Path(rel).is_dir() else []:
        local.add(f.stem)

broken = []
for rel in DIRS:
    d = pathlib.Path(rel)
    if not d.is_dir():
        continue
    for f in sorted(d.glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except SyntaxError as e:
            broken.append(f"{f}: SyntaxError: {e}")
            continue
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
        for n in sorted(names):
            if n in local:
                continue
            try:
                if find_spec(n) is None:
                    broken.append(f"{f}: cannot resolve import {n!r}")
            except (ImportError, ModuleNotFoundError, ValueError):
                broken.append(f"{f}: cannot resolve import {n!r}")

if broken:
    print(f"{len(broken)} unresolvable import(s):")
    for b in broken:
        print("  " + b)
    sys.exit(1)
print(f"all imports resolve ({len(local)} local modules on the test path)")
PYEOF
}
check imports - "import health" -- import_health

# --- secrets --------------------------------------------------------------
step "gitleaks"
if [ -f .gitleaks.toml ]; then
  check gitleaks gitleaks "gitleaks" -- gitleaks detect --no-banner --redact --config .gitleaks.toml
else
  check gitleaks gitleaks "gitleaks" -- gitleaks detect --no-banner --redact
fi

# --- credential file permissions -----------------------------------------
# .env holds a live token. It was world-readable (0644) until 27 Aug 2026.
step "env permissions"
env_perms() {
  [ -f .env ] || { echo "no .env present"; return 0; }
  mode=$(stat -f '%OLp' .env 2>/dev/null || stat -c '%a' .env 2>/dev/null)
  if [ "$mode" != "600" ]; then
    echo "FAILED: .env is mode $mode; expected 600 (it holds a live token)"
    return 1
  fi
  echo ".env is mode 600"
}
check env-perms - "env permissions" -- env_perms

# --- report ---------------------------------------------------------------
n_pass=0; n_fail=0; n_skip=0
for r in "${RESULTS[@]}"; do
  case "${r#*|}" in pass\|*) n_pass=$((n_pass+1)) ;; fail\|*) n_fail=$((n_fail+1)) ;; skip\|*) n_skip=$((n_skip+1)) ;; esac
done

if [ "$JSON" -eq 1 ]; then
  printf '{\n  "checks": [\n'
  first=1
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r id status detail <<<"$r"
    [ "$first" -eq 1 ] || printf ',\n'; first=0
    printf '    {"check": "%s", "status": "%s", "detail": "%s", "log": "%s/%s.log"}' \
      "$id" "$status" "$detail" "$LOGDIR" "$id"
  done
  printf '\n  ],\n  "summary": {"pass": %d, "fail": %d, "skip": %d},\n' "$n_pass" "$n_fail" "$n_skip"
  if [ "$n_fail" -eq 0 ] && [ "$n_skip" -eq 0 ]; then printf '  "all_green": true\n}\n'; else printf '  "all_green": false\n}\n'; fi
  exit "$FAIL"
fi

printf '\n'
for r in "${RESULTS[@]}"; do
  IFS='|' read -r id status detail <<<"$r"
  [ "$status" = "skip" ] && printf '\033[33m  SKIP  %-16s %s\033[0m\n' "$id" "$detail"
  [ "$status" = "fail" ] && printf '\033[31m  FAIL  %-16s %s\033[0m\n' "$id" "$detail"
done
if [ "$FAIL" -eq 0 ]; then
  printf '\033[32m%d checks passed\033[0m\n' "$n_pass"
  [ "$n_skip" -gt 0 ] && printf '\033[33m%d checks were SKIPPED -- unverified, not clean.\033[0m\n' "$n_skip"
else
  printf '\033[31m%d checks failed, %d passed, %d skipped\033[0m\n' "$n_fail" "$n_pass" "$n_skip"
fi
exit "$FAIL"
