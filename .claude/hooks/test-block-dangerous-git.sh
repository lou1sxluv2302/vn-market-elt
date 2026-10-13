#!/bin/bash
# Known-answer tests for block-dangerous-git.sh. Exit 0 = all cases pass.
# Planted faults: every blocked form the code review found missing; controls:
# ordinary git commands, including ones whose description mentions "push".

HOOK="$(dirname "$0")/block-dangerous-git.sh"
fail=0

check() {  # expected_exit command [description]
  local expected=$1 cmd=$2 desc=${3:-test}
  local json
  json=$(python - "$cmd" "$desc" <<'PY'
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1], "description": sys.argv[2]}}))
PY
)
  printf '%s' "$json" | bash "$HOOK" 2>/dev/null
  local got=$?
  if [ "$got" -ne "$expected" ]; then
    echo "🔴 expected $expected got $got: $cmd"
    fail=1
  else
    echo "✅ $expected $cmd"
  fi
}

# must block (exit 2)
check 2 "git push origin main"
check 2 "git push --force"
check 2 'git -C "E:/Work/repo" push'
check 2 "git --no-pager push"
check 2 "git  push"
check 2 "git reset --hard HEAD~1"
check 2 "git clean -fd"
check 2 "git clean -xfd"
check 2 "git clean -df"
check 2 "git clean --force"
check 2 "git branch -D old"
check 2 "git branch --delete --force old"
check 2 "git checkout ."
check 2 "git checkout -- ."
check 2 "git restore ."
check 2 "cd repo && git push -u origin feat/x"

# must allow (exit 0)
check 0 "git status" "check before push"
check 0 "git commit -F msg.txt"
check 0 "git log --oneline"
check 0 "git switch -c feat/x"
check 0 "git checkout -- .claude/settings.json"
check 0 "git branch -d merged"
check 0 "git reset --soft HEAD~1"
check 0 "gh pr create --fill"
check 0 "python tools/secret_scan.py"

exit $fail
