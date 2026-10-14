#!/usr/bin/env bash
# Upload the sample docs, wait for indexing, then search. Needs: curl (jq optional).
set -euo pipefail
API="${API:-http://localhost:8000}"

pretty() { if command -v jq >/dev/null; then jq .; else cat; fi; }

echo "== uploading sample docs"
find sample_docs -type f -name '*.md' | while read -r f; do
  curl -s -X POST "$API/documents" -F "file=@$f" | pretty
done

echo "== waiting for indexing"
for _ in $(seq 1 60); do
  stats=$(curl -s "$API/stats")
  echo "$stats"
  if ! echo "$stats" | grep -qE '"(uploaded|chunked)"'; then break; fi
  sleep 1
done

echo "== search: vector search database"
curl -s -G "$API/search" --data-urlencode "q=vector search database" | pretty

echo "== search: container orchestration"
curl -s -G "$API/search" --data-urlencode "q=container orchestration" | pretty
