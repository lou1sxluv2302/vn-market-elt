#!/bin/bash
# Blocks destructive git commands before Claude Code runs them (PreToolUse hook).
# Adapted from mattpocock/skills git-guardrails-claude-code: the original reads the
# command with jq, which is not installed here, so every check passed silently.
# This version matches the raw JSON input instead: no dependency, and a false
# match blocks (safe side) rather than allows.

INPUT=$(cat)

DANGEROUS_PATTERNS=(
  "git push"
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "push --force"
  "reset --hard"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$INPUT" | grep -qE "$pattern"; then
    echo "BLOCKED: command matches dangerous pattern '$pattern'. The owner runs this command; ask them." >&2
    exit 2
  fi
done

exit 0
