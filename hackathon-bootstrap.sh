#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# Config (override via env)
# ----------------------------
SERVER="${SERVER:-http://localhost:8080/rdf4j-server}"
REPO_ID="${REPO_ID:-ietf-core}"
REPO_LABEL="${REPO_LABEL:-$REPO_ID}"

SCHEMA_FILE="${SCHEMA_FILE:-simap-rdfs-schema.ttl}"
INSTANCE_FILE="${INSTANCE_FILE:-pwe3-dynamic-topology.ttl}"

SCHEMA_CTX="${SCHEMA_CTX:-<http://www.huawei.com/graph/schema>}"
INSTANCE_CTX="${INSTANCE_CTX:-<http://www.huawei.com/graph/instance/pwe3-dynamic-topology>}"

# If your corporate proxy is set, we force direct-to-localhost for curl
CURL="curl --silent --show-error --noproxy localhost"

say() { printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# ----------------------------
# Sanity checks
# ----------------------------
command -v curl >/dev/null || fail "curl not found"
[[ -f "$SCHEMA_FILE" ]]   || fail "Missing $SCHEMA_FILE (expected beside this script)"
[[ -f "$INSTANCE_FILE" ]] || fail "Missing $INSTANCE_FILE (expected beside this script)"

say "RDF4J Server: $SERVER"
say "Repository   : $REPO_ID  (label: $REPO_LABEL)"
say "Files        : $SCHEMA_FILE  |  $INSTANCE_FILE"

# ----------------------------
# (1) One-time CORS instructions (manual)
# ----------------------------
cat <<'TIP'

================================ CORS / Tomcat instructions ================================

If you have NOT enabled CORS globally yet, do this once:

  1) Stop Tomcat (close window or run:  D:\Apps\apache-tomcat-9.0.106\bin\shutdown.bat)
  2) Edit  D:\Apps\apache-tomcat-9.0.106\conf\web.xml  and add near the end, before </web-app>:

     <filter>
       <filter-name>CorsFilter</filter-name>
       <filter-class>org.apache.catalina.filters.CorsFilter</filter-class>
       <init-param>
         <param-name>cors.allowed.origins</param-name>
         <param-value>*</param-value>
       </init-param>
       <init-param>
         <param-name>cors.allowed.methods</param-name>
         <param-value>GET,POST,HEAD,OPTIONS</param-value>
       </init-param>
       <init-param>
         <param-name>cors.allowed.headers</param-name>
         <param-value>Content-Type,Accept,Origin,Authorization,Access-Control-Request-Method,Access-Control-Request-Headers</param-value>
       </init-param>
       <init-param>
         <param-name>cors.exposed.headers</param-name>
         <param-value>Access-Control-Allow-Origin,Access-Control-Allow-Credentials</param-value>
       </init-param>
       <init-param>
         <param-name>cors.support.credentials</param-name>
         <param-value>false</param-value>
       </init-param>
     </filter>
     <filter-mapping>
       <filter-name>CorsFilter</filter-name>
       <url-pattern>/*</url-pattern>
     </filter-mapping>

  3) Start Tomcat again (put your own path):
       D:\Apps\apache-tomcat-9.0.106\bin\startup.bat

When Tomcat is fully up, come back to this window and PRESS ENTER to continue.
===========================================================================================

TIP

# ----------------------------
# (2) Wait for user to confirm Tomcat is up
# ----------------------------
read -r -p "Press ENTER once Tomcat is running and http://localhost:8080 is reachable..."

# Quick health check (RDF4J CSV list)
say "Checking RDF4J availability…"
$CURL -f "$SERVER/repositories" >/dev/null || fail "RDF4J not reachable at $SERVER"

# ----------------------------
# Helper: check if repository exists
# ----------------------------
repo_exists() {
  $CURL -f "$SERVER/repositories" \
    | tr -d '\r' \
    | awk -F, 'NR>1 {print $2}' \
    | grep -Fxq "$REPO_ID"
}

# ----------------------------
# (3) Create or recreate repository
# ----------------------------
if repo_exists; then
  say "Repository '$REPO_ID' already exists — deleting it to start clean…"
  $CURL -f -X DELETE "$SERVER/repositories/$REPO_ID" || fail "Delete failed"
else
  say "Repository '$REPO_ID' not present — creating fresh."
fi

# Build a local config file (avoid /tmp on Windows Git-Bash)
CFG_FILE="./.${REPO_ID}.config.ttl"
cat > "$CFG_FILE" <<TTL
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rep:   <http://www.openrdf.org/config/repository#> .
@prefix sr:    <http://www.openrdf.org/config/repository/sail#> .
@prefix sail:  <http://www.openrdf.org/config/sail#> .
@prefix ns:    <http://www.openrdf.org/config/sail/native#> .

[] a rep:Repository ;
   rep:repositoryID "$REPO_ID" ;
   rdfs:label "$REPO_LABEL" ;
   rep:repositoryImpl [
     rep:repositoryType "openrdf:SailRepository" ;
     sr:sailImpl [
       sail:sailType "openrdf:NativeStore" ;
       ns:tripleIndexes "spoc,posc,opsc"
     ]
   ] .
TTL

say "Creating repository '$REPO_ID'…"
# Preferred multipart form
$CURL -f -X POST "$SERVER/repositories" \
  -H "Accept: text/plain" \
  -F "config=@${CFG_FILE};type=application/x-turtle" \
  >/dev/null || fail "Repository creation failed"

rm -f "$CFG_FILE"

repo_exists || fail "Repository was not created"

say "Repository created."

# ----------------------------
# (4) Upload schema and instance
# ----------------------------
encode_ctx() {
  # Keep angle brackets in the query string but URL-encode them as required
  python - <<'PY' "$1"
import sys, urllib.parse
ctx=sys.argv[1]
print(urllib.parse.quote(ctx, safe='<>:/#'))
PY
}

SCHEMA_CTX_Q=$(encode_ctx "$SCHEMA_CTX")
INSTANCE_CTX_Q=$(encode_ctx "$INSTANCE_CTX")

say "Uploading schema to context $SCHEMA_CTX …"
$CURL -f -X POST \
  "$SERVER/repositories/$REPO_ID/statements?context=${SCHEMA_CTX_Q}" \
  -H "Content-Type: text/turtle" \
  --data-binary @"$SCHEMA_FILE" \
  >/dev/null || fail "Schema upload failed"

say "Uploading instance to context $INSTANCE_CTX …"
$CURL -f -X POST \
  "$SERVER/repositories/$REPO_ID/statements?context=${INSTANCE_CTX_Q}" \
  -H "Content-Type: text/turtle" \
  --data-binary @"$INSTANCE_FILE" \
  >/dev/null || fail "Instance upload failed"

# ----------------------------
# (5) Report counts and useful URLs
# ----------------------------
say "Done. Repository contents (CSV):"
$CURL -f "$SERVER/repositories" | tr -d '\r' | grep ",$REPO_ID," || true

say "Query endpoint for SPARQLWorks:"
echo "  $SERVER/repositories/$REPO_ID"

say "WorkBench (browser):"
echo "  http://localhost:8080/rdf4j-workbench/repositories/$REPO_ID/summary"

say "Contexts you used:"
echo "  Schema  : $SCHEMA_CTX"
echo "  Instance: $INSTANCE_CTX"

say "Tip: in SPARQLWorks use FROM to pin contexts, e.g.:"
cat <<EOF

  SELECT (COUNT(*) as ?n) WHERE {
    GRAPH $SCHEMA_CTX { ?s ?p ?o }
  }

  SELECT (COUNT(*) as ?n) WHERE {
    GRAPH $INSTANCE_CTX { ?s ?p ?o }
  }
EOF
