#!/usr/bin/env bash
# One call that answers "is this shippable", cheapest failure first.
#   ./check.sh          full run
#   ./check.sh tests    just the suite
set -uo pipefail
cd "$(dirname "$0")" || exit 1

ROTA="${ROTA:-$HOME/agents/rota/tools}"
fails=0
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
bad() { printf '  FAIL: %s\n' "$1"; fails=$((fails + 1)); }

step "tests"
if out=$(python3 -m unittest discover -s tests 2>&1); then
  printf '  %s\n' "$(printf '%s' "$out" | tail -3 | head -1)"
else
  printf '%s\n' "$out" | tail -30
  bad "suite red"
fi
[ "${1:-all}" = "tests" ] && exit $fails

step "prose (slopcheck)"
for f in README.md; do
  if o=$(python3 "$ROTA/slopcheck.py" "$f" 2>&1); then printf '  %s\n' "$o" | head -1
  else printf '%s\n' "$o"; bad "$f has hard failures"; fi
done

step "secrets"
# out/ is gitignored generated output; its "linkedin_post" fields trip the linkedin-client-id rule
if o=$(gitleaks git --no-banner . 2>&1 && gitleaks git --pre-commit --no-banner . 2>&1 && gitleaks git --staged --pre-commit --no-banner . 2>&1); then
  printf '  history, working changes and staged changes clean\n'
else
  printf '%s\n' "$o" | tail -5; bad "gitleaks"
fi
if [ -d .git ] && git ls-files | grep -qE '\.(key|pem)$|\.db$|\.env$'; then bad "a key, env or database is tracked"; fi

step "result"
if [ "$fails" -eq 0 ]; then printf '  ready to commit\n'; else printf '  %s check(s) failed\n' "$fails"; fi
exit $fails
