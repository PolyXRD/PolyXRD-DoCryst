#!/bin/bash
# Robust GitHub release uploader with retry/backoff.
# Usage: bash upload_release_retry.sh v1.0.1
# Handles: leftover draft release, partial asset upload, transient connection resets.
TAG="${1:?usage: upload_release_retry.sh vX.Y.Z}"
VER="${TAG#v}"
GH="/c/Program Files/GitHub CLI/gh.exe"
REPO="PolyXRD/PolyXRD-DoCryst"
ASSETS=("dist/PolyXRD-DoCryst-v$VER.exe" "dist/PolyXRD-DoCryst-v$VER-Setup.exe")
NOTES="docs/RELEASE_NOTES_$TAG.md"
TITLE="PolyXRD DoCryst $TAG 稳定版"
MAX=30
SLEEP=90

for f in "${ASSETS[@]}"; do
  [ -f "$f" ] || { echo "missing asset: $f"; exit 1; }
done
[ -f "$NOTES" ] || { echo "missing notes: $NOTES"; exit 1; }

api() { "$GH" api "$@" 2>&1; }

for attempt in $(seq 1 $MAX); do
  echo "=== attempt $attempt / $MAX  $(date '+%H:%M:%S') ==="

  state=$(api "repos/$REPO/releases" --jq '.[] | select(.tag_name=="'"$TAG"'") | {id, draft, assets: [.assets[].name]} | tostring')
  if [ -n "$state" ]; then
    echo "release exists: $state"
    published=$(echo "$state" | grep -o '"draft":false')
    have1=$(echo "$state" | grep -c "$(basename ${ASSETS[0]})" || true)
    have2=$(echo "$state" | grep -c "$(basename ${ASSETS[1]})" || true)

    if [ "$have1" = "0" ]; then
      echo "uploading ${ASSETS[0]} ..."
      "$GH" release upload "$TAG" "${ASSETS[0]}" --clobber --repo "$REPO" 2>&1 && echo "OK asset1" || { echo "asset1 failed"; sleep $SLEEP; continue; }
    fi
    if [ "$have2" = "0" ]; then
      echo "uploading ${ASSETS[1]} ..."
      "$GH" release upload "$TAG" "${ASSETS[1]}" --clobber --repo "$REPO" 2>&1 && echo "OK asset2" || { echo "asset2 failed"; sleep $SLEEP; continue; }
    fi

    if [ -z "$published" ]; then
      echo "publishing draft ..."
      "$GH" release edit "$TAG" --draft=false --title "$TITLE" --notes-file "$NOTES" --repo "$REPO" 2>&1 && echo "PUBLISHED" || { echo "publish failed"; sleep $SLEEP; continue; }
    fi
    echo "SUCCESS: release $TAG is published with all assets"
    exit 0
  fi

  echo "no release yet, creating draft ..."
  "$GH" release create "$TAG" --draft --title "$TITLE" --notes-file "$NOTES" --repo "$REPO" 2>&1 && echo "draft created" || echo "create failed, will retry"
  sleep $SLEEP
done
echo "GAVE UP after $MAX attempts"
exit 1
