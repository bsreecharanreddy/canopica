#!/usr/bin/env bash
# PreToolUse/Bash hook: warns before a `git commit` if files outside docs/
# are staged without docs/STATUS.md, since CLAUDE.md requires STATUS.md to
# update "in the same commit as the work it describes -- never as a
# separate follow-up commit, or it drifts and stops being trustworthy."
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

if ! printf '%s' "$cmd" | grep -qE '\bgit\s+commit\b'; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

staged="$(git diff --cached --name-only 2>/dev/null || true)"
[ -z "$staged" ] && exit 0

if printf '%s\n' "$staged" | grep -q '^docs/STATUS\.md$'; then
  exit 0
fi

if printf '%s\n' "$staged" | grep -qv '^docs/'; then
  msg="docs/STATUS.md is not staged, but other files are. CLAUDE.md requires STATUS.md to update in the same commit as the work it describes -- confirm this commit doesn't need a STATUS.md update (task done, a verification result, or a new decision) before proceeding."
  jq -n --arg msg "$msg" '{systemMessage: $msg, hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", permissionDecisionReason: $msg}}'
fi

exit 0
