#!/usr/bin/env bash
# Commit the desk's state from a workflow. Every post, veto and reply is a commit, so the history is the log.
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add queue state 2>/dev/null || true
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "$1"
for i in 1 2 3; do git pull -q --rebase && git push -q && exit 0; sleep 5; done
exit 1
