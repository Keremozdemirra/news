#!/usr/bin/env bash
# The media branch holds the JPEGs Instagram fetches and the thumbnails the web pages show.
# It is always one commit, rewritten on every push and pruned by age, so images never pile up in
# history the way they would on main.
#   scripts/media.sh pull   check the branch out into ./media (empty on first use)
#   scripts/media.sh push   prune, then replace the branch with one commit of what is in ./media
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  pull)
    rm -rf media && git worktree prune
    if git fetch -q --depth=1 origin media 2>/dev/null; then
      git worktree add -q --detach media FETCH_HEAD
    elif [ -n "$(git ls-remote origin refs/heads/media)" ]; then
      # the branch exists, so a failed fetch is a network error, not first use: an empty checkout would
      # make the next push replace the branch with nothing
      echo "media branch exists on origin but could not be fetched" >&2
      exit 1
    else
      git worktree add -q --detach media HEAD
      (cd media && git rm -rqf . && git clean -fdqx)
    fi
    ;;
  push)
    python3 -c "from aidaily import desk; desk.prune_media()"
    # Two jobs can push at once. Each push keeps every folder already on the remote branch that this
    # checkout does not have, and is refused if the remote moved in between; then it starts over.
    for attempt in 1 2 3 4 5; do
      remote=$(git ls-remote origin refs/heads/media | cut -f1)
      if [ -n "$remote" ]; then
        git fetch -q --depth=1 origin media
        rm -rf .media-remote && mkdir .media-remote
        git archive FETCH_HEAD | tar -x -C .media-remote
        for d in .media-remote/*/; do
          name=$(basename "$d")
          [ -e "media/$name" ] || cp -R "$d" "media/$name"
        done
        rm -rf .media-remote
      fi
      (cd media
       git checkout -q --orphan "media-$(date +%s)-$attempt"
       git add -A
       git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
         commit -q --allow-empty -m "media $(date -u +%F-%H%M)")
      if (cd media && git push -q --force-with-lease=refs/heads/media:"${remote}" origin HEAD:refs/heads/media); then
        exit 0
      fi
      echo "media branch moved; retrying ($attempt)" >&2
      sleep $((attempt * 3))
    done
    exit 1
    ;;
  *) echo "usage: $0 pull|push" >&2; exit 2 ;;
esac
