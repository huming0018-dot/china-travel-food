#!/usr/bin/env bash
set -Eeuo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/sync.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
assert_contains() { grep -Fq "$2" <<<"$1" || fail "expected output to contain: $2"; }

new_fixture() {
  local name="$1"
  mkdir -p "$TMP/$name/cloud" "$TMP/$name/app"
  cp "$SRC" "$TMP/$name/sync.sh"
  cat > "$TMP/$name/cloud/task_helper.py" <<'PY'
import json, os, pathlib, sys
log = pathlib.Path(os.environ["STUB_LOG"])
mode = os.environ.get("TASK_MODE", "empty")
def list_tasks(role=None):
    with log.open("a") as f: f.write("GET list\n")
    if mode == "error": raise RuntimeError("stub service unavailable")
    if mode == "empty": return []
    if mode == "todo": return [{"id": 7, "priority": "P1", "title": "stub task", "status": "todo"}]
    if mode == "none": return [{"id": 8, "priority": "P2", "title": "done task", "status": "done"}]
    return []

if len(sys.argv) > 1 and sys.argv[1] == "claim":
    with log.open("a") as f: f.write("WRITE claim " + sys.argv[2] + "\n")
    sys.exit(0)

PY
  touch "$TMP/$name/ROLES.md" "$TMP/$name/STATUS.md"
  git -C "$TMP/$name" init -q -b task/test
  git -C "$TMP/$name" config user.email test@example.com
  git -C "$TMP/$name" config user.name Test
  echo base > "$TMP/$name/base.txt"
  git -C "$TMP/$name" add base.txt
  git -C "$TMP/$name" commit -qm base
  : > "$TMP/$name/stub.log"
}

# Default is read-only: stub task service must see GET only; git state stays unchanged.
new_fixture readonly
before="$(git -C "$TMP/readonly" status --porcelain)"
out="$(STUB_LOG="$TMP/readonly/stub.log" TASK_MODE=empty bash "$TMP/readonly/sync.sh" 2>&1)" || fail "read-only empty query failed: $out"
assert_contains "$out" "任务查询成功：列表为空"
[[ "$(cat "$TMP/readonly/stub.log")" == "GET list" ]] || fail "read-only mode made a task write"
[[ "$(git -C "$TMP/readonly" status --porcelain)" == "$before" ]] || fail "read-only mode changed git worktree"
! grep -Eqi 'git pull|git add|git commit|git push|unblock|claim' "$TMP/readonly/stub.log" || fail "read-only mode invoked a write operation"

# Query failures are non-zero and never claim there are no tasks.
new_fixture query_error
if STUB_LOG="$TMP/query_error/stub.log" TASK_MODE=error bash "$TMP/query_error/sync.sh" >"$TMP/query_error/out" 2>&1; then fail "query error returned success"; fi
grep -q 'TASK_QUERY_ERROR: RuntimeError: stub service unavailable' "$TMP/query_error/out" || fail "query failure not reported clearly"
! grep -q '无待认领任务' "$TMP/query_error/out" || fail "query failure disguised as empty"

# Successful non-empty task results are distinguished.
new_fixture todo
out="$(STUB_LOG="$TMP/todo/stub.log" TASK_MODE=todo bash "$TMP/todo/sync.sh" task-list dev 2>&1)" || fail "todo query failed"
assert_contains "$out" "任务查询成功：存在待认领任务"
assert_contains "$out" "#7 [P1] stub task"
new_fixture no_todo
out="$(STUB_LOG="$TMP/no_todo/stub.log" TASK_MODE=none bash "$TMP/no_todo/sync.sh" task-list dev 2>&1)" || fail "no todo query failed"
assert_contains "$out" "任务查询成功：当前没有待认领任务（任务列表非空）"

# Explicit pull is opt-in and uses a local stub remote; protected main is rejected.
new_fixture sync
mkdir -p "$TMP/bare.git"; git init -q --bare "$TMP/bare.git"
git -C "$TMP/sync" remote add origin "$TMP/bare.git"
git -C "$TMP/sync" push -qu origin task/test
bash "$TMP/sync/sync.sh" sync >/dev/null
git -C "$TMP/sync" checkout -q -b main
git -C "$TMP/sync" config branch.main.remote origin
git -C "$TMP/sync" config branch.main.merge refs/heads/main
if bash "$TMP/sync/sync.sh" sync >"$TMP/sync/out" 2>&1; then fail "pull on protected main succeeded"; fi

# Explicit task writes are delegated only after the explicit operation.
new_fixture task_write
STUB_LOG="$TMP/task_write/stub.log" bash "$TMP/task_write/sync.sh" task-claim 7 >/dev/null
[[ "$(cat "$TMP/task_write/stub.log")" == "WRITE claim 7" ]] || fail "task claim did not use isolated write stub"

# Commit scope, branch, and owner are enforced; only named file is committed.
new_fixture commit
cd "$TMP/commit"
echo change > allowed.txt
echo other > other-agent.txt
git add allowed.txt other-agent.txt
git commit -qm 'fixture changes'
echo next > allowed.txt
echo unsafe > other-agent.txt
git add other-agent.txt
if SYNC_RELEASE_OWNER=agent-a bash ./sync.sh commit --branch task/test --files allowed.txt --message scoped --owner agent-a >out 2>&1; then fail "commit accepted pre-staged out-of-scope file"; fi
# Reset staged state for the positive path; leave other agent change unstaged.
git reset -q
echo next > allowed.txt
echo other-uncommitted > other-agent.txt
SYNC_RELEASE_OWNER=agent-a bash ./sync.sh commit --branch task/test --files allowed.txt --message scoped --owner agent-a >/dev/null
[[ "$(git show --pretty='' --name-only HEAD | sed '/^$/d')" == "allowed.txt" ]] || fail "commit included file outside declared scope"
[[ "$(git status --porcelain | grep -c 'other-agent.txt')" -eq 1 ]] || fail "other agent file was not left uncommitted"
if SYNC_RELEASE_OWNER=agent-a bash ./sync.sh commit --branch task/test --files other-agent.txt --message wrong-owner --owner agent-b >/dev/null 2>&1; then fail "wrong owner was accepted"; fi

# Publish requires owner, current task branch, clean worktree, and pushes only named branch.
new_fixture publish
mkdir "$TMP/publish-remote"; git init -q --bare "$TMP/publish-remote"
git -C "$TMP/publish" remote add origin "$TMP/publish-remote"
rm -f "$TMP/publish/ROLES.md" "$TMP/publish/STATUS.md"
rm -rf "$TMP/publish/cloud" "$TMP/publish/app"
git -C "$TMP/publish" add -A
git -C "$TMP/publish" commit -qm "fixture clean-up"
SYNC_RELEASE_OWNER=agent-a bash "$TMP/publish/sync.sh" publish --branch task/test --owner agent-a
[[ "$(git --git-dir="$TMP/publish-remote" for-each-ref --format='%(refname:short)')" == "task/test" ]] || fail "publish did not push only named branch"

echo "PASS: read-only, query states, explicit operations, scoped commit, owner-only publish"
