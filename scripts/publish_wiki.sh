#!/usr/bin/env bash
# Publish the wiki pages in docs/wiki to the repository wiki.
#
# GitHub creates a repository's wiki git repository the first time a page is
# added through the web interface. Until that happens, `git clone` of the
# `.wiki.git` URL fails and this script says so instead of pretending.
#
# Usage: scripts/publish_wiki.sh [owner/repo]
set -euo pipefail

REPO="${1:-hamanakam1/el-hidratador}"
WIKI_URL="git@github.com:${REPO}.wiki.git"
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)/docs/wiki"

if [ ! -d "${SOURCE_DIR}" ]; then
  echo "no wiki source at ${SOURCE_DIR}" >&2
  exit 1
fi

if ! git ls-remote "${WIKI_URL}" >/dev/null 2>&1; then
  cat >&2 <<'MSG'
The wiki git repository does not exist yet.

GitHub creates it the first time a page is added from the web interface:
  https://github.com/OWNER/REPO/wiki/_new

Create the "Home" page there, then run this script again to publish every
page in docs/wiki.
MSG
  exit 2
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

git clone --quiet "${WIKI_URL}" "${WORKDIR}/wiki"
cp "${SOURCE_DIR}"/*.md "${WORKDIR}/wiki/"

cd "${WORKDIR}/wiki"
git add --all
if git diff --cached --quiet; then
  echo "wiki already up to date"
  exit 0
fi
git -c user.name="Michael Hamanaka" \
    -c user.email="41898235+hamanakam1@users.noreply.github.com" \
    commit --quiet -m "docs: publish the wiki pages from docs/wiki"
git push --quiet origin HEAD:main
count="$(find "${SOURCE_DIR}" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
echo "published ${count} wiki pages to ${WIKI_URL}"
