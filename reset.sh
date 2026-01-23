# --- Run this from your existing local clone of concordance-v1 ---

set -euo pipefail

# 1) Create the archive repo on GitHub FIRST (empty):
#    https://github.com/concordance-co/concordance-v1-archive
ARCHIVE_URL="https://github.com/concordance-co/concordance-v1-archive.git"

# 2) Mirror ALL history (branches/tags) into the archive repo
git remote add archive "$ARCHIVE_URL" 2>/dev/null || git remote set-url archive "$ARCHIVE_URL"
git push --mirror archive

# 3) Wipe history in the EXISTING repo (fresh root commit with current code)
DEFAULT_BRANCH="$(git remote show origin | sed -n 's/.*HEAD branch: //p')"
: "${DEFAULT_BRANCH:=main}"

git checkout --orphan fresh-start
git add -A
git commit -m "Initial commit"

git branch -M "$DEFAULT_BRANCH"
git push --force-with-lease origin "$DEFAULT_BRANCH"

# 4) Delete all other remote branches (keep only default branch)
git fetch --prune
git for-each-ref --format='%(refname:short)' "refs/remotes/origin" \
  | sed 's#^origin/##' \
  | grep -v "^${DEFAULT_BRANCH}$" \
  | xargs -r -n 1 git push origin --delete

# 5) Delete all remote tags
git tag -l | xargs -r -n 1 git push origin --delete

# 6) Local cleanup (optional)
git gc --prune=now --aggressive
