#!/bin/bash
# Robust GitHub release uploader with retry/backoff.
# Handles: leftover draft release, partial asset upload, transient connection resets.
GH="/c/Program Files/GitHub CLI/gh.exe"
REPO="PolyXRD/PolyXRD-DoCryst"
TAG="v1.0.0"
ASSETS=("dist/PolyXRD-DoCryst-v1.0.0.exe" "dist/PolyXRD-DoCryst-v1.0.0-Setup.exe")
NOTES="docs/RELEASE_NOTES_v1.0.0.md"
TITLE="PolyXRD DoCryst v1.0.0 稳定版"
MAX=30
SLEEP=90

api() { "$GH" api "$@" 2>&1; }

for attempt in $(seq 1 $MAX); do
  echo "=== attempt $attempt / $MAX  $(date '+%H:%M:%S') ==="

  state=$(api "repos/$REPO/releases" --jq '.[] | select(.tag_name=="'"$TAG"'") | {id, draft, assets: [.assets[].name]} | tostring')
  if [ -n "$state" ]; then
    echo "release exists: $state"
    rid=$(echo "$state" | sed 's/{"id":\([0-9]*\).*/\1/')
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
