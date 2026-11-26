#!/usr/bin/env bash
# Commit the desk's state from a workflow. Every post, veto and reply is a commit, so the history is the log.
#
# A status change that never reaches main is how a post goes out twice: the next run sees it still queued.
# So on a rebase conflict this run's files win. In `git pull --rebase`, "theirs" is the commit being replayed
# (this run's commit) and "ours" is the upstream it is replayed onto, so `-X theirs` keeps this run's version
# of any conflicting hunk in queue/ and state/. If that is not enough, the files this run changed are taken
# over a fresh copy of upstream. If the push still fails the job fails loudly; the publish step's check of the
# account's recent posts is then what stops a duplicate.
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
# add each folder that exists: one missing path made `git add queue state` fail as a whole and commit nothing
for d in queue state; do [ -e "$d" ] && git add "$d"; done
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "$1"

abort_rebase() { git rebase --abort >/dev/null 2>&1 || true; }

# last resort: upstream plus the files this run's commit touched, taken as this run left them
rebuild_on_upstream() {
  local mine upstream f
  mine=$(git rev-parse HEAD)
  git diff --no-renames --name-status HEAD~1 HEAD > "${TMPDIR:-/tmp}/commit-sh-changes.$$"
  git fetch -q origin
  upstream=$(git rev-parse '@{u}')
  git reset -q --hard "$upstream"
  while IFS=$'\t' read -r st f; do
    case "$st" in
      D) git rm -q -f --ignore-unmatch -- "$f" ;;
      *) git checkout -q "$mine" -- "$f" ;;
    esac
  done < "${TMPDIR:-/tmp}/commit-sh-changes.$$"
  rm -f "${TMPDIR:-/tmp}/commit-sh-changes.$$"
  git diff --cached --quiet || git commit -q -m "$1"
}

for i in 1 2 3 4 5; do
  if git pull -q --rebase -X theirs && git push -q; then exit 0; fi
  abort_rebase
  sleep $((i * ${COMMIT_RETRY_PAUSE:-3}))
done
echo "pull --rebase -X theirs did not settle; rebuilding this run's changes on upstream"
if rebuild_on_upstream "$1" && git push -q; then exit 0; fi
echo "::error::could not push the desk state to main; this run's status changes are NOT saved" >&2
exit 1
