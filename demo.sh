#!/usr/bin/env bash
# Upload the sample docs, wait for indexing, then search. Needs: curl (jq optional).
set -euo pipefail
API="${API:-http://localhost:8000}"

pretty() { if command -v jq >/dev/null; then jq .; else cat; fi; }

echo "== uploading sample docs"
for f in sample_docs/*.md; do
  curl -s -X POST "$API/documents" -F "file=@$f" | pretty
done

echo "== waiting for indexing"
for _ in $(seq 1 30); do
  stats=$(curl -s "$API/stats")
  echo "$stats"
  if ! echo "$stats" | grep -qE '"(uploaded|chunked)"'; then break; fi
  sleep 1
done

echo "== search: how do consumer groups share partitions?"
curl -s -G "$API/search" --data-urlencode "q=how do consumer groups share partitions" | pretty

echo "== search: why use deterministic point ids?"
curl -s -G "$API/search" --data-urlencode "q=why use deterministic point ids" | pretty
