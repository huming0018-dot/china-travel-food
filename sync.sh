#!/usr/bin/env bash
# Safe multi-agent repository entry point. Default operation is read-only.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'USAGE'
Usage:
  bash sync.sh [status <role>]               Read-only checks and task query (default)
  bash sync.sh sync                           Explicit git pull --rebase
  bash sync.sh task-list [role]               Explicit read-only task list
  bash sync.sh task-claim <id>                 Explicit task claim (remote write)
  bash sync.sh task-unblock                   Explicit task unlock (remote write)
  bash sync.sh commit --branch <branch> --files <path...> --message <text> --owner <name>
  bash sync.sh publish --branch <branch> --owner <name>

Commit stages only listed paths and requires a non-protected task branch and a
release-owner identity. Publish pushes only that branch and is owner-only.
Set SYNC_RELEASE_OWNER to the designated release owner's identity.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }

repo_branch() { git symbolic-ref --quiet --short HEAD || fail "detached HEAD is not allowed"; }

query_tasks() {
  local role="${1:-}"
  local output rc
  if output="$(python3 - "$ROOT" "$role" <<'PY'
import os, pathlib, sys
root, role = sys.argv[1:]
sys.path.insert(0, str(pathlib.Path(root, "cloud").resolve()))
os.environ.setdefault("FOOD_APP_DIR", str(pathlib.Path(root, "app").resolve()))
import task_helper
try:
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        tasks = task_helper.list_tasks(role or None)
except Exception as exc:
    print(f"TASK_QUERY_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(2)
if tasks is None:
    print("TASK_QUERY_ERROR: task service returned no result", file=sys.stderr)
    raise SystemExit(2)
todo = [t for t in tasks if t.get("status") == "todo"]
if not tasks:
    print("TASK_QUERY_OK_EMPTY")
elif todo:
    print("TASK_QUERY_OK_HAS_TODO")
    for t in todo[:5]:
        print(f"  #{t.get('id','?')} [{t.get('priority','?')}] {t.get('title','')[:40]}")
else:
    print("TASK_QUERY_OK_NO_TODO")
PY
)"; then
    :
  else
    rc=$?
    echo "$output" >&2
    return "$rc"
  fi
  case "$output" in
    *TASK_QUERY_OK_EMPTY*) echo "✅ 任务查询成功：列表为空" ;;
    *TASK_QUERY_OK_HAS_TODO*) echo "🔴 任务查询成功：存在待认领任务"; printf '%s\n' "$output" | sed -n '/^  #/p' ;;
    *TASK_QUERY_OK_NO_TODO*) echo "✅ 任务查询成功：当前没有待认领任务（任务列表非空）" ;;
    *) echo "$output" >&2; echo "ERROR: task query returned an unrecognized result" >&2; return 2 ;;
  esac
}

require_owner() {
  local owner="$1"
  [[ -n "$owner" ]] || fail "--owner is required"
  [[ -n "${SYNC_RELEASE_OWNER:-}" ]] || fail "SYNC_RELEASE_OWNER must identify the designated release owner"
  [[ "$owner" == "$SYNC_RELEASE_OWNER" ]] || fail "owner '$owner' does not match designated release owner"
}

cmd="${1:-status}"
if [[ "$cmd" == "-h" || "$cmd" == "--help" || "$cmd" == "help" ]]; then usage; exit 0; fi
shift || true
case "$cmd" in
  status)
    role="${1:-}"
    echo "Read-only status${role:+ for role $role}"
    git status --short --branch
    [[ -f ROLES.md ]] && echo "✅ ROLES.md present" || echo "⚠️ ROLES.md missing"
    [[ -f STATUS.md ]] && echo "✅ STATUS.md present" || echo "⚠️ STATUS.md missing"
    if [[ -n "$role" && -f ROLES.md ]]; then
      echo "Role boundary: $role"
      awk -v role="$role" '$0 == "### " role {p=1; next} /^### |^## / {if (p) exit} p {print}' ROLES.md | head -8
    fi
    query_tasks "$role"
    git log --oneline -5
    ;;
  task-list) query_tasks "${1:-}" ;;
  sync)
    [[ $# -eq 0 ]] || fail "sync takes no extra arguments"
    branch="$(repo_branch)"
    [[ "$branch" != "main" && "$branch" != "master" ]] || fail "refusing to pull on protected branch '$branch'"
    git pull --rebase
    ;;
  task-claim)
    [[ $# -eq 1 ]] || fail "usage: sync.sh task-claim <id>"
    [[ "$1" =~ ^[0-9]+$ ]] || fail "task id must be numeric"
    python3 cloud/task_helper.py claim "$1"
    ;;
  task-unblock)
    [[ $# -eq 0 ]] || fail "usage: sync.sh task-unblock"
    python3 cloud/task_helper.py unblock
    ;;
  commit)
    branch=""; message=""; owner=""; files=(); seen_files=0
    while (($#)); do
      case "$1" in
        --branch) (($# >= 2)) || fail "--branch needs a value"; branch="$2"; shift 2 ;;
        --message) (($# >= 2)) || fail "--message needs a value"; message="$2"; shift 2 ;;
        --owner) (($# >= 2)) || fail "--owner needs a value"; owner="$2"; shift 2 ;;
        --files) seen_files=1; shift; while (($#)) && [[ "$1" != --* ]]; do files+=("$1"); shift; done ;;
        *) fail "unknown commit argument: $1" ;;
      esac
    done
    [[ -n "$branch" && -n "$message" && ${#files[@]} -gt 0 && $seen_files -eq 1 ]] || fail "commit requires --branch, --files (one or more paths), and --message"
    require_owner "$owner"
    [[ "$(repo_branch)" == "$branch" ]] || fail "current branch does not match --branch '$branch'"
    [[ "$branch" != "main" && "$branch" != "master" && "$branch" != release/* ]] || fail "commits to protected/release branches are forbidden"
    for path in "${files[@]}"; do
      [[ "$path" != /* && "$path" != .. && "$path" != ../* && "$path" != */../* && "$path" != */.. ]] || fail "unsafe path: $path"
      [[ -e "$path" || -L "$path" ]] || fail "path does not exist: $path"
    done
    existing_staged="$(git diff --cached --name-only)"
    for path in $existing_staged; do
      allowed=0
      for requested_path in "${files[@]}"; do [[ "$path" == "$requested_path" ]] && allowed=1; done
      [[ $allowed -eq 1 ]] || fail "pre-staged out-of-scope path '$path'; refusing commit"
    done
    git add -- "${files[@]}"
    staged="$(git diff --cached --name-only | sort)"
    requested="$(printf '%s\n' "${files[@]}" | sort -u)"
    [[ "$staged" == "$requested" ]] || fail "staged paths differ from requested scope; refusing commit"
    git diff --cached --check
    git commit -m "$message"
    ;;
  publish)
    branch=""; owner=""
    while (($#)); do
      case "$1" in
        --branch) (($# >= 2)) || fail "--branch needs a value"; branch="$2"; shift 2 ;;
        --owner) (($# >= 2)) || fail "--owner needs a value"; owner="$2"; shift 2 ;;
        *) fail "unknown publish argument: $1" ;;
      esac
    done
    [[ -n "$branch" ]] || fail "publish requires --branch"
    require_owner "$owner"
    [[ "$(repo_branch)" == "$branch" ]] || fail "current branch does not match --branch '$branch'"
    [[ "$branch" != "main" && "$branch" != "master" ]] || fail "direct publish to protected branch is forbidden"
    [[ -z "$(git status --porcelain)" ]] || fail "working tree must be clean before publish"
    git push -u origin "$branch"
    ;;
  *) usage >&2; fail "unknown operation '$cmd'" ;;
esac
