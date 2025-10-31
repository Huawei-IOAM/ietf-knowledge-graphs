# ietf-knowledge-graphs

In this repository, we provide a toy example related to reflections from the [IETF NMOP](https://datatracker.ietf.org/wg/nmop/about/) Knowledge Graph Design Team.

Overall, we build an IT Service Management (ITSM) with the following workflow: IETF Topology --> RDF ([RFC8345](https://datatracker.ietf.org/doc/rfc8345/))
RDFS schema, PWE3 static/dynamic instances, and IETF <--> [NORIA-O](https://w3id.org/noria/) alignment

**Goal:** a fully navigable SIMAP topology graph where every element is referenced via unique IRIs and explicit relations (e.g., network-ref, node-ref, tp-ref, link-ref, source-node, dest-node, source-tp, dest-tp).
Outcome: consistent schema + instance data for queries, validation, and visualisation.

✨ Built for demo - quick to run, easy to show.

# 🚦 Quick start (TL;DR)

1. Open [RDF4J Workbench](https://rdf4j.org/documentation/tools/server-workbench/) (locally or publicly)
2. Create repo ID
3. Import files in this order:
   - simap-rdfs-schema.ttl
   - pwe3-static-topology.ttl
   - pwe3-dynamic-topology.ttl
   - relations-IETF-Noria.ttl (optional alignment)
4. SPARQL endpoint (use in SPARQLWorks): http://localhost:8080/rdf4j-server/repositories/...

# 📦 Repository structure

```
- schema/
  - simap-rdfs-schema.ttl            # RDFS schema, single base path
- instances/
  - pwe3-static-topology.ttl         # Static PWE3 instance
  - pwe3-dynamic-topology.ttl        # Dynamic PWE3 instance
- alignment/
  - Relations-IETF-Noria.ttl         # Cross-model links: IETF <--> NORIA (optional)
- README.md
```

# 🧠 Data model highlights

- Single ontology base: `http://www.huawei.com/ontology/ietf-network/` ... for all classes & properties (network, node, link, termination-point, supporting lists, source/dest, etc.).

- Instance paths use a stable data root, e.g.: `http://www.huawei.com/data/network/<network-id>/node/<node-id>/`...

- Explicit relations (examples):
  - Networks: hasNetwork, hasNetworkTypes
  - Links: hasSource --> source-node, source-tp; hasDest --> dest-node, dest-tp

- Supporting lists:
  - `supporting-network/network-ref`
  - `supporting-node/{network-ref,node-ref}`
  - `supporting-termination-point/{network-ref,node-ref,tp-ref}`
  - `supporting-link/{network-ref,link-ref}`

- IETF <--> [NORIA-O](https://w3id.org/noria/) alignment (optional):
  - Mappings in [relations-IETF-Simap-Noria.ttl](relations-IETF-Simap-Noria.ttl) let you traverse from IETF instance data to NORIA classes/instances for multi-model demos.

# 🧪 How to run (RDF4J Workbench)

- Open the rdf4j-workbench UI => http://localhost:8080/rdf4j-workbench

- Create repository => http://localhost:8080/rdf4j-workbench/repositories/NONE/create
  - Type : Native store
  - Repository ID: name

- Import data into the *name* repository, in the following order => http://localhost:8080/rdf4j-workbench/repositories/name/add
  - schema/simap-rdfs-schema.ttl --> (Context: http://www.huawei.com/graph/schema)
  - instances/pwe3-static-topology.ttl --> (Context: http://www.huawei.com/graph/instance/pwe3-static-topology)
  - instances/pwe3-dynamic-topology.ttl --> (Context: http://www.huawei.com/graph/instance/pwe3-dynamic-topology)
  - alignment/relations-IETF-Simap-Noria.ttl (optional) --> (Context: http://www.huawei.com/graph/alignment)
  - schema/ops-mgmt.ttl (optional) --> (Context: http://www.huawei.com/graph/schema)
  - alignment/relations-ops-mgmt-Noria.ttl (optional) --> (Context: http://www.huawei.com/graph/alignment)
  - instances/ops-mgmt-instances.ttl (optional) --> (Context: http://www.huawei.com/graph/instance/ops-mgmt-instances)

- Query data through the SPARQL endpoint (for tools):
  - SPARQL endpoint : http://localhost:8080/rdf4j-server/repositories/name or a public server domain if you want to take the endpoint
  - RDF4J SPARQL endpoint UI : http://localhost:8080/rdf4j-workbench/repositories/name/query 

- Sanity check (Workbench --> SPARQL):
	```
	SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }
	```
# 🔎 Visualise with SPARQLWorks

## Local use (recommended)

- Download SPARQLWorks from https://github.com/danielhmills/sparqlworks
- Open the `sparqlworks.html` file locally using your favorite Web browser (or serve via python -m http.server).
- Set *Query Mode* : Advanced
- Set *SPARQL Endpoint* : http://localhost:8080/rdf4j-server/repositories/name
- Run CONSTRUCT queries (see below) for live graph visuals.

If your browser blocks cross-origin calls, enable CORS on Tomcat (global conf/web.xml):

```
<filter>
  <filter-name>CorsFilter</filter-name>
  <filter-class>org.apache.catalina.filters.CorsFilter</filter-class>
  <init-param><param-name>cors.allowed.origins</param-name><param-value>*</param-value></init-param>
  <init-param><param-name>cors.allowed.methods</param-name><param-value>GET,POST,HEAD,OPTIONS</param-value></init-param>
  <init-param><param-name>cors.allowed.headers</param-name><param-value>Content-Type,Accept,Origin,Authorization,Access-Control-Request-Method,Access-Control-Request-Headers</param-value></init-param>
</filter>
<filter-mapping><filter-name>CorsFilter</filter-name><url-pattern>/*</url-pattern></filter-mapping>
```

Restart Tomcat afterwards.

## Public demo (optional)

- RDF4J Server behind a reverse proxy (Nginx/Apache) and expose https://<your-host>/rdf4j-server/repositories/name
- Make sure the proxy/app adds the CORS headers above.
- Alternative: use a tunnelling tool (e.g., LocalTunnel, Cloudflared). Ensure your corporate proxy policy allows it.

# 🧭 Example queries (ready for SPARQLWorks)

1. Root --> networks --> network-types : [rq/rq_simap_root_networks_network-types.sparql](rq/rq_simap_root_networks_network-types.sparql)
2. Links with Source/Dest --> Termination Points : [rq/rq_simap_links_tp.sparql](rq/rq_simap_links_tp.sparql)
3. Supporting-node : [rq/rq_simap_supporting-node.sparql](rq/rq_simap_supporting-node.sparql)
4. Node managed by and potential relationship to an incident : [rq/rq_noria_managedBy.sparql](rq/rq_noria_managedBy.sparql)
5. Implemented alignment relationships across models : [rq/rq_model-relationships.sparql](rq/rq_model-relationships.sparql)

# ✅ Demo checklist

- Schema loaded
- Static & dynamic instances loaded (contexts separated)
- Optional: IETF <--> NORIA alignment loaded for cross-model views
- SPARQLWorks renders CONSTRUCT graphs cleanly
