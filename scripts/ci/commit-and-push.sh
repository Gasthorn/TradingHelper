#!/usr/bin/env bash
# Commit et push des données par les workflows qui écrivent (spec F10 — R3, R4).
#
# Usage : commit-and-push.sh "<message>" <chemin> [<chemin>...]
#
# - Ne commite que les chemins donnés (fichiers modifiés ET non suivis : `git status --porcelain`,
#   que `git diff --quiet` ne voit pas). Rien à commiter : aucun commit, sortie 0.
# - Auteur et committer : github-actions[bot], sans toucher à la configuration git.
# - Push : `git pull --rebase` puis `git push`, 3 tentatives au plus, attentes de
#   TH_PUSH_SLEEP × 1 puis × 2 secondes (défaut 5 : 5 s puis 10 s). Les fichiers modifiés hors
#   des chemins sont préservés par --autostash. Un rebase en conflit est abandonné ; après
#   3 échecs, sortie 1 (le run suivant ré-ingère, F01 est idempotent).
# - Écrit `pushed_sha` (vide sans commit) et `head_sha` (HEAD final) dans $GITHUB_OUTPUT,
#   ou sur stdout hors GitHub Actions.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage : commit-and-push.sh \"<message>\" <chemin> [<chemin>...]" >&2
  exit 2
fi

message=$1
shift

export GIT_AUTHOR_NAME="github-actions[bot]"
export GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"
export GIT_COMMITTER_NAME=$GIT_AUTHOR_NAME
export GIT_COMMITTER_EMAIL=$GIT_AUTHOR_EMAIL

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "$1" >> "$GITHUB_OUTPUT"
  else
    echo "$1"
  fi
}

pushed_sha=""
if [ -n "$(git status --porcelain -- "$@")" ]; then
  branch=$(git symbolic-ref --short HEAD)
  git add -A -- "$@"
  git commit -q -m "$message" -- "$@"
  delay=${TH_PUSH_SLEEP:-5}
  attempt=1
  until
    echo "Tentative de push $attempt/3" >&2
    git pull -q --rebase --autostash origin "$branch" && git push -q origin "HEAD:refs/heads/$branch"
  do
    git rebase --abort >/dev/null 2>&1 || true
    if [ "$attempt" -ge 3 ]; then
      echo "Push en échec après 3 tentatives : rien n'est poussé." >&2
      exit 1
    fi
    sleep $((delay * attempt))
    attempt=$((attempt + 1))
  done
  pushed_sha=$(git rev-parse HEAD)
  echo "Commit poussé sur $branch : $pushed_sha ($message)"
else
  echo "Aucun changement dans : $* — pas de commit."
fi

output "pushed_sha=$pushed_sha"
output "head_sha=$(git rev-parse HEAD)"
