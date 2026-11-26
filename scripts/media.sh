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
    else
      git worktree add -q --detach media HEAD
      (cd media && git rm -rqf . && git clean -fdqx)
    fi
    ;;
  push)
    python3 -c "from aidaily import desk; desk.prune_media()"
    cd media
    git checkout -q --orphan "media-$(date +%s)"
    git add -A
    git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      commit -q --allow-empty -m "media $(date -u +%F-%H%M)"
    git push -q -f origin HEAD:refs/heads/media
    ;;
  *) echo "usage: $0 pull|push" >&2; exit 2 ;;
esac
