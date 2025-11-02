#!/usr/bin/env bash

set -euo pipefail

# ----------------------------
# Config (override via env)
# ----------------------------

SERVER="${SERVER:-http://localhost:8080/rdf4j-server}"
WORKBENCH="${WORKBENCH:-http://localhost:8080/rdf4j-workbench}"
REPO_ID="${REPO_ID:-ietf-core}"
REPO_LABEL="${REPO_LABEL:-$REPO_ID}"

CURL="curl --silent --show-error --noproxy localhost"

say() { printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# ----------------------------
# Define files and contexts
# ----------------------------

declare -A FILES=(
  ["simap-rdfs-schema.ttl"]="http://www.huawei.com/graph/schema"
  ["pwe3-static-topology.ttl"]="http://www.huawei.com/graph/instance/pwe3-static-topology"
  ["pwe3-dynamic-topology.ttl"]="http://www.huawei.com/graph/instance/pwe3-dynamic-topology"
  ["relations-IETF-Simap-Noria.ttl"]="http://www.huawei.com/graph/alignment"
  ["ops-mgmt.ttl"]="http://www.huawei.com/graph/schema"
  ["relations-ops-mgmt-Noria.ttl"]="http://www.huawei.com/graph/alignment"
  ["ops-mgmt-instances.ttl"]="http://www.huawei.com/graph/instance/ops-mgmt-instances"
)

say "RDF4J Server: $SERVER"
say "Repository ID: $REPO_ID"

# ----------------------------
# Create repository
# ----------------------------

say "Creating repository '$REPO_ID'…"

$CURL -X POST "$WORKBENCH/repositories/NONE/create" \
  --data-urlencode "type=native" \
  --data-urlencode "Repository ID=$REPO_ID" \
  --data-urlencode "Repository title=$REPO_LABEL" \
  --data-urlencode "Triple indexes=spoc,posc" \
  --data-urlencode "Query Evaluation Mode=STRICT" \
  >/dev/null || fail "Repository creation failed"

say "✓ Repository created successfully"

# ----------------------------
# Upload data files
# ----------------------------

say "Uploading data files…"

for FILE in "${!FILES[@]}"; do
  CTX="${FILES[$FILE]}"
  
  # Check if file exists
  if [[ ! -f "$FILE" ]]; then
    say "⚠ Skipping missing file: $FILE"
    continue
  fi
  
  say "Uploading: $FILE"
  say "Context: $CTX"
  
  $CURL -X POST "$SERVER/repositories/$REPO_ID/statements?context=%3C${CTX}%3E" \
    -H "Content-Type: text/turtle" \
    --data-binary "@$FILE" \
    || fail "Upload failed for $FILE"
  
  say "✓ $FILE uploaded successfully"
done

# ----------------------------
# Verification
# ----------------------------

say "Verifying upload…"

TRIPLE_COUNT=$($CURL "$SERVER/repositories/$REPO_ID/size" || echo "unknown")

say "Repository now contains approximately $TRIPLE_COUNT triples."
say ""
say "✓ Bootstrap complete!"
say "Access repository at: $SERVER/repositories/$REPO_ID"
