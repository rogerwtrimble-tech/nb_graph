#!/usr/bin/env bash
# Create github.com/rogerwtrimble-tech/nb_graph (if needed) and push this repo to it.
# Needs the GitHub CLI logged in as an account that can create repos there:  gh auth login
set -euo pipefail
OWNER=${OWNER:-rogerwtrimble-tech}
REPO=${REPO:-nb_graph}
VISIBILITY=${VISIBILITY:-private}   # or public
cd "$(dirname "$0")/.."
if ! gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  gh repo create "$OWNER/$REPO" --"$VISIBILITY" --description "Graph-first UI for NetBox on PostgreSQL 19" --disable-wiki
fi
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$OWNER/$REPO.git"
git push -u origin main
echo "https://github.com/$OWNER/$REPO"
