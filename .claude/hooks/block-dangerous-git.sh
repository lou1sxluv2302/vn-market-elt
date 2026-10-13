#!/bin/bash
# PreToolUse hook: blocks destructive git commands for agents (Bash and PowerShell
# tools). The owner runs them. The blocked list is documented in CONTRIBUTING.md
# (Agent tooling); tests: .claude/hooks/test-block-dangerous-git.sh.
#
# Adapted from mattpocock/skills git-guardrails-claude-code. Differences:
# - no jq (absent here; the upstream script then passed every command silently):
#   the command is read with Python, and if no Python is found the whole raw input
#   is matched instead, so a failure blocks rather than allows;
# - patterns match within one command segment and survive options between `git`
#   and the subcommand (`git -C <dir> push`, `git --no-pager push`, extra spaces).

INPUT=$(cat)

COMMAND=""
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    COMMAND=$(printf '%s' "$INPUT" | "$py" -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) && break
  fi
done
[ -z "$COMMAND" ] && COMMAND="$INPUT"

# One segment = text between ; & | or newline. Each pattern needs `git` earlier in the segment.
SEG='[^;&|]*'
DANGEROUS_PATTERNS=(
  "\\bgit\\b${SEG}\\bpush\\b"
  "\\bgit\\b${SEG}\\breset\\b${SEG}--hard"
  "\\bgit\\b${SEG}\\bclean\\b${SEG}(-[a-zA-Z]*f|--force)"
  "\\bgit\\b${SEG}\\bbranch\\b${SEG}(-[a-zA-Z]*D\\b|--delete${SEG}--force|--force${SEG}--delete)"
  "\\bgit\\b${SEG}\\b(checkout|restore)\\b(${SEG}[[:space:]]--)?[[:space:]]+\\.([[:space:]]|$)"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if printf '%s\n' "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: this git command is reserved for the owner (pattern: $pattern). Give the owner the exact command to run." >&2
    exit 2
  fi
done

exit 0
