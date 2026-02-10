#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON → TTL converter aligned to Noria (core) + Noria-EXT (IETF-aligned)

Namespaces
----------
- noria:     https://w3id.org/noria/ontology/           (core)
- noria_ext: http://www.huawei.com/ontology/noria-ext#  (extension)

HTTP instance URIs (no URN, no % encodes; hyphenated “slugs”):
  http://www.huawei.com/data/network/{net}
  http://www.huawei.com/data/network/{net}/node/{node}
  http://www.huawei.com/data/network/{net}/node/{node}/iface/{tp}
  http://www.huawei.com/data/network/{net}/link/{link}
  http://www.huawei.com/data/resource/dev/{device}
  http://www.huawei.com/data/resource/iface/{device}/{iface}
  http://www.huawei.com/data/configRef/{sha1}

Two-pass strategy
-----------------
Pass 1: create Networks, Nodes, Interfaces, Links; fill indices for URI resolution.
Pass 2: resolve & attach supports as IRIs (supportsNetwork/Node/Interface/Link).

Files handled (if present in current dir):
  - pwe3-static-topology.json                  -> pwe3-static-topology.ttl
  - pwe3-dynamic-topology.json                 -> pwe3-dynamic-topology.ttl
  - mock-dm-ISIS-instance.json                 -> mock-dm-ISIS-instance.ttl
  - mock-dm-ISIS-instance_config_refs.json     -> mock-dm-ISIS-instance_config_refs.ttl
"""

import os, json, re, hashlib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, XSD, DCTERMS

# ---------- Namespaces & base ----------
NORIA     = Namespace("https://w3id.org/noria/ontology/")
NORIA_EXT = Namespace("http://www.huawei.com/ontology/noria-ext#")
BASE      = "http://www.huawei.com/data"

# ---------- Slug (no % encodes; use hyphens) ----------
_slug_keep = re.compile(r'[^A-Za-z0-9._-]+')
def slug(s: str) -> str:
    s = str(s)
    s = s.replace('%', '-').replace(':', '-').replace('/', '-').replace('\\', '-')
    s = _slug_keep.sub('-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s

# ---------- Literals & add helper ----------
def lit(v):
    if v is None: return None
    if isinstance(v, bool):  return Literal(v)
    if isinstance(v, int):   return Literal(v, datatype=XSD.integer)
    if isinstance(v, float): return Literal(v, datatype=XSD.decimal)
    return Literal(str(v))

def add(g: Graph, s, p, o):
    if o is not None:
        g.add((s, p, o))

# ---------- URI builder ----------
def U(kind: str, **ids) -> URIRef:
    if kind == "network":
        return URIRef(f"{BASE}/network/{slug(ids['net'])}")
    if kind == "node":
        return URIRef(f"{BASE}/network/{slug(ids['net'])}/node/{slug(ids['node'])}")
    if kind == "iface":  # network TerminationPoint
        return URIRef(f"{BASE}/network/{slug(ids['net'])}/node/{slug(ids['node'])}/iface/{slug(ids['tp'])}")
    if kind == "link":
        return URIRef(f"{BASE}/network/{slug(ids['net'])}/link/{slug(ids['link'])}")
    if kind == "devres":
        return URIRef(f"{BASE}/resource/dev/{slug(ids['dev'])}")
    if kind == "ifres":  # inventory interface
        return URIRef(f"{BASE}/resource/iface/{slug(ids['dev'])}/{slug(ids['iface'])}")
    if kind == "cfg":
        return URIRef(f"{BASE}/configRef/{slug(ids['key'])}")
    raise ValueError(f"Unknown kind {kind}")

# ---------- YANG-ish paths (provenance) ----------
def yang_net(n):              return f"/ietf-network:networks/network[network-id='{n}']"
def yang_node(n, node):       return f"{yang_net(n)}/node[node-id='{node}']"
def yang_tp(n, node, tp):     return f"{yang_node(n,node)}/ietf-network-topology:termination-point[tp-id='{tp}']"
def yang_link(n, link):       return f"{yang_net(n)}/ietf-network-topology:link[link-id='{link}']"

def pwe3_net(n):              return f"/pwe3:networks/network[id='{n}']"
def pwe3_node(n, node):       return f"{pwe3_net(n)}/node[id='{node}']"
def pwe3_tp(n, node, tp):     return f"{pwe3_node(n,node)}/termination-point[id='{tp}']"
def pwe3_link(n, link):       return f"{pwe3_net(n)}/link[id='{link}']"

# ---------- Inventory mapping from TP id (best-effort) ----------
TP_PAT_IF  = re.compile(r"^isis:([^:]+):(.+)$")      # isis:<node>:<if-name>
TP_PAT_NUM = re.compile(r"^isis:([^:]+):([0-9]+)$")  # isis:<node>:<digits> -> Loopback<digits>

def interface_resource_from_tpid(tp_id: str):
    if not isinstance(tp_id, str):
        return None, None
    m = TP_PAT_IF.match(tp_id)
    if m:
        dev, ifname = m.group(1), m.group(2)
        return U("devres", dev=dev), U("ifres", dev=dev, iface=ifname)
    m = TP_PAT_NUM.match(tp_id)
    if m:
        dev, num = m.group(1), m.group(2)
        ifname = f"Loopback{num}"
        return U("devres", dev=dev), U("ifres", dev=dev, iface=ifname)
    return None, None

# ---------- Graph boilerplate ----------
def begin_graph() -> Graph:
    g = Graph()
    g.bind("noria", NORIA)
    g.bind("noria_ext", NORIA_EXT)
    g.bind("dct", DCTERMS)
    g.bind("rdfs", RDFS)
    return g

# ---------- Emitters ----------
def emit_network(g, net_id, label, yang_path):
    N = U("network", net=net_id)
    add(g, N, RDF.type, NORIA_EXT.Network)
    add(g, N, DCTERMS.identifier, lit(net_id))
    add(g, N, RDFS.label, lit(label or net_id))
    add(g, N, NORIA_EXT.yangPath, lit(yang_path))
    return N

def emit_node(g, net_id, node_id, label, yang_path, holder_net):
    Nd = U("node", net=net_id, node=node_id)
    add(g, Nd, RDF.type, NORIA_EXT.NetworkNode)
    add(g, Nd, DCTERMS.identifier, lit(node_id))
    add(g, Nd, RDFS.label, lit(label or node_id))
    add(g, Nd, NORIA_EXT.yangPath, lit(yang_path))
    add(g, holder_net, NORIA_EXT.hasNode, Nd)
    return Nd

def emit_interface(g, net_id, node_id, tp_id, label, yang_path, holder_node, maybe_tp_identifier=None):
    If = U("iface", net=net_id, node=node_id, tp=tp_id)
    add(g, If, RDF.type, NORIA.NetworkInterface)
    add(g, If, DCTERMS.identifier, lit(maybe_tp_identifier or tp_id))
    add(g, If, RDFS.label, lit(label or tp_id))
    add(g, If, NORIA_EXT.yangPath, lit(yang_path))
    add(g, holder_node, NORIA.hasTerminationPoint, If)
    return If

def emit_link(g, net_id, link_id, label, yang_path, holder_net, src_if=None, dst_if=None):
    L = U("link", net=net_id, link=link_id)
    add(g, L, RDF.type, NORIA.NetworkLink)
    add(g, L, DCTERMS.identifier, lit(link_id))
    add(g, L, RDFS.label, lit(label or link_id))
    add(g, L, NORIA_EXT.yangPath, lit(yang_path))
    add(g, holder_net, NORIA_EXT.hasLink, L)
    if src_if:
        add(g, L, NORIA_EXT.networkLinkSourceInterface, src_if)
    if dst_if:
        add(g, L, NORIA_EXT.networkLinkDestinationInterface, dst_if)
    return L

# ---------- Indices (two-pass; re-initialised per mapper) ----------
idx_net = {}
idx_node = {}
idx_if = {}
idx_if_by_tp = {}
idx_link = {}

# ---------- Prefix→network heuristics for labels ----------
NET_BY_PREFIX = {
    "L3:": "layer3-network",
    "CR:": "static-cr-layer",
    # add more if your data uses other prefixes
}

def strip_prefix(val: str):
    for pfx, net in NET_BY_PREFIX.items():
        if isinstance(val, str) and val.startswith(pfx):
            return net, val[len(pfx):]
    return None, val

# ---------- Cross-file mint helpers ----------
def node_uri_or_none(net, node):
    return U("node", net=net, node=node) if (net and node) else None

def iface_uri_or_none(net, node, tp):
    if net and node and tp:
        n2, tp2 = strip_prefix(tp)
        if n2: net, tp = n2, tp2
        return U("iface", net=net, node=node, tp=tp)
    return None

def link_uri_or_none(net, link):
    return U("link", net=net, link=link) if (net and link) else None

# ---------- Resolvers for supports ----------
def resolve_if_target(net_hint, node_hint, tp_id):
    if net_hint and node_hint:
        return idx_if.get((net_hint, node_hint, tp_id))
    if net_hint:
        return idx_if_by_tp.get((net_hint, tp_id))
    return None

def add_supports_interface(g, subj, rec):
    net  = rec.get("network") or rec.get("network-ref")
    node = rec.get("node")    or rec.get("node-ref")
    tp   = rec.get("tp")      or rec.get("tp-ref")
    tgt = None
    if tp:
        tgt = resolve_if_target(net, node, tp)
        if not tgt and node and net:
            tgt = iface_uri_or_none(net, node, tp)  # cross-file mint
    if tgt:
        g.add((subj, NORIA_EXT.supportsInterface, tgt))
    elif tp:
        g.add((subj, NORIA_EXT.supportsInterface, lit(rec.get("tp") or rec.get("tp-ref"))))

def add_supports_node(g, subj, rec):
    net  = rec.get("network") or rec.get("network-ref")
    node = rec.get("node")    or rec.get("node-ref")
    tgt = idx_node.get((net, node)) if (net and node) else None
    if not tgt:
        tgt = node_uri_or_none(net, node)
    if tgt:
        g.add((subj, NORIA_EXT.supportsNode, tgt))
    elif node:
        g.add((subj, NORIA_EXT.supportsNode, lit(node)))

def add_supports_network(g, subj, rec):
    net = rec.get("network") or rec.get("network-ref")
    tgt = idx_net.get(net) if net else None
    if not tgt and net:
        tgt = U("network", net=net)
    if tgt:
        g.add((subj, NORIA_EXT.supportsNetwork, tgt))
    elif net:
        g.add((subj, NORIA_EXT.supportsNetwork, lit(net)))

def add_supports_link(g, subj_link_uri, support_rec):
    link_id = support_rec.get("link") or support_rec.get("link-ref")
    net_id  = support_rec.get("network") or support_rec.get("network-ref")
    if not net_id and link_id:
        net_id, link_id = strip_prefix(link_id)
    tgt = idx_link.get((net_id, link_id)) if (net_id and link_id) else None
    if not tgt:
        tgt = link_uri_or_none(net_id, link_id)  # cross-file mint
    if tgt:
        g.add((subj_link_uri, NORIA_EXT.supportsLink, tgt))
    elif link_id:
        g.add((subj_link_uri, NORIA_EXT.supportsLink, lit(link_id)))

# ---------- ConfigRef emitter (extension) ----------
def _emit_cfg_refs(g: Graph, holder: URIRef, key_seed: str, cfg: dict):
    """
    cfg is either a dict of domain -> block or the block itself.
    We create noria_ext:ConfigRef individuals and attach with noria_ext:configRef.
    """
    def make_ref(domain: str, item: dict):
        key = hashlib.sha1((json.dumps(item, sort_keys=True) + domain + key_seed).encode("utf-8")).hexdigest()
        C = U("cfg", key=key)
        add(g, C, RDF.type, NORIA_EXT.ConfigRef)
        add(g, C, NORIA_EXT.domain, lit(domain))
        field_map = {
            "attr_name":         NORIA_EXT.attrName,
            "value_type":        NORIA_EXT.valueType,
            "reference-type":    NORIA_EXT.referenceType,
            "reference-path":    NORIA_EXT.yangPath,
            "execution-context": NORIA_EXT.executionContext,
            "request_protocol":  NORIA_EXT.requestProtocol,
            "subtree-filter":    NORIA_EXT.subtreeFilter,
            "depth":             NORIA_EXT.depth,
        }
        for k, pred in field_map.items():
            if k in item:
                v = item[k]
                if k == "depth":
                    try: v = int(v)
                    except: pass
                add(g, C, pred, lit(v))
        add(g, holder, NORIA_EXT.configRef, C)

    if isinstance(cfg, dict):
        for domain, block in cfg.items():
            if isinstance(block, list):
                for it in block: make_ref(domain, it)
            elif isinstance(block, dict):
                make_ref(domain, block)

# ========================= PWE3 mapper =========================
def map_pwe3(json_path, out_ttl):
    global idx_net, idx_node, idx_if, idx_if_by_tp, idx_link
    idx_net, idx_node, idx_if, idx_if_by_tp, idx_link = {}, {}, {}, {}, {}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    g = begin_graph()

    # ----- PASS 1: entities + indices -----
    for net in data.get("networks", []):
        nid = net.get("id")
        N   = emit_network(g, nid, net.get("name", nid), pwe3_net(nid))
        idx_net[nid] = N

        for node in net.get("nodes", []):
            node_id = node.get("id")
            Nd = emit_node(g, nid, node_id, node.get("name", node_id), pwe3_node(nid, node_id), N)
            idx_node[(nid, node_id)] = Nd

            for tp in node.get("termination-points", []):
                tpid = tp.get("id")
                If = emit_interface(g, nid, node_id, tpid, tp.get("name"), pwe3_tp(nid, node_id, tpid), Nd, maybe_tp_identifier=tpid)
                idx_if[(nid, node_id, tpid)] = If
                idx_if_by_tp[(nid, tpid)] = If

                # inventory (best-effort)
                devRes, ifRes = interface_resource_from_tpid(tpid)
                if devRes: add(g, Nd, NORIA_EXT.realizedByResource, devRes)
                if ifRes:  add(g, If, NORIA_EXT.realizedByResource, ifRes)

        for link in net.get("links", []):
            lid = link.get("id")
            src = link.get("source", {}) or {}
            dst = link.get("destination", {}) or {}
            s_if = U("iface", net=nid, node=src.get("node"), tp=src.get("termination-point")) if (src.get("node") and src.get("termination-point")) else None
            d_if = U("iface", net=nid, node=dst.get("node"), tp=dst.get("termination-point")) if (dst.get("node") and dst.get("termination-point")) else None
            L = emit_link(g, nid, lid, link.get("name"), pwe3_link(nid, lid), N, s_if, d_if)
            idx_link[(nid, lid)] = L

    # ----- PASS 2: attach supports as IRIs -----
    for net in data.get("networks", []):
        nid = net.get("id")
        N   = idx_net.get(nid)

        # network-level supports
        for sup in net.get("supporting-networks", []):
            tgt = idx_net.get(sup) or U("network", net=sup)
            add(g, N, NORIA_EXT.supportsNetwork, tgt)

        # node-level + iface-level supports
        for node in net.get("nodes", []):
            node_id = node.get("id")
            Nd = idx_node.get((nid, node_id))

            for s in node.get("supporting", []):
                if isinstance(s, dict):
                    add_supports_node(g,    Nd, s)
                    add_supports_network(g, Nd, s)

            for tp in node.get("termination-points", []):
                tpid = tp.get("id")
                If   = idx_if.get((nid, node_id, tpid))
                sup  = tp.get("supporting")
                if isinstance(sup, dict):
                    add_supports_interface(g, If, sup)
                    add_supports_node(g,      If, sup)
                    add_supports_network(g,   If, sup)

        # link overlays
        for link in net.get("links", []):
            lid = link.get("id")
            L   = idx_link.get((nid, lid))
            for su in link.get("supporting", []):
                if isinstance(su, dict):
                    add_supports_link(g, L, su)

    g.serialize(out_ttl, format="turtle")

# ========================= ISIS mapper =========================
def map_isis(json_path, out_ttl, include_config_refs=False):
    global idx_net, idx_node, idx_if, idx_if_by_tp, idx_link
    idx_net, idx_node, idx_if, idx_if_by_tp, idx_link = {}, {}, {}, {}, {}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    g = begin_graph()
    networks = data.get("ietf-network:networks", {}).get("network", [])

    # ----- PASS 1: entities + indices -----
    for net in networks:
        nid = net.get("network-id")
        N   = emit_network(g, nid, net.get("name", nid), yang_net(nid))
        idx_net[nid] = N

        for node in net.get("node", []):
            node_id = node.get("node-id")
            Nd = emit_node(g, nid, node_id, node.get("name", node_id), yang_node(nid, node_id), N)
            idx_node[(nid, node_id)] = Nd

            for tp in node.get("ietf-network-topology:termination-point", []):
                tpid = tp.get("tp-id")
                If = emit_interface(g, nid, node_id, tpid, None, yang_tp(nid, node_id, tpid), Nd, maybe_tp_identifier=tpid)
                idx_if[(nid, node_id, tpid)] = If
                idx_if_by_tp[(nid, tpid)] = If

                devRes, ifRes = interface_resource_from_tpid(tpid)
                if devRes: add(g, Nd, NORIA_EXT.realizedByResource, devRes)
                if ifRes:  add(g, If, NORIA_EXT.realizedByResource, ifRes)

                if include_config_refs:
                    l3 = tp.get("ietf-l3-unicast-topology:l3-termination-point-attributes", {})
                    cfg = l3.get("configuration-ref")
                    if cfg:
                        _emit_cfg_refs(g, holder=If, key_seed=f"{nid}/{node_id}/{tpid}", cfg=cfg)

        for link in net.get("ietf-network-topology:link", []):
            lid = link.get("link-id")
            s, d = link.get("source", {}) or {}, link.get("destination", {}) or {}
            s_node, s_tp = s.get("source-node"), s.get("source-tp")
            d_node, d_tp = d.get("dest-node"),   d.get("dest-tp")

            s_if = U("iface", net=nid, node=s_node, tp=s_tp) if (s_node and s_tp) else None
            d_if = U("iface", net=nid, node=d_node, tp=d_tp) if (d_node and d_tp) else None

            L = emit_link(g, nid, lid, link.get("name", lid), yang_link(nid, lid), N, s_if, d_if)
            idx_link[(nid, lid)] = L

            # Optional: termination inventory from endpoint TP ids
            if s_tp:
                _, ifRes = interface_resource_from_tpid(s_tp)
                if ifRes: add(g, L, NORIA_EXT.networkLinkTerminationResourceOrigin, ifRes)
            if d_tp:
                _, ifRes = interface_resource_from_tpid(d_tp)
                if ifRes: add(g, L, NORIA_EXT.networkLinkTerminationResourceDestination, ifRes)

    # ----- PASS 2: supports -----
    for net in networks:
        nid = net.get("network-id")
        N   = idx_net.get(nid)

        for s in net.get("supporting-network", []):
            ref = s.get("network-ref")
            tgt = idx_net.get(ref) or (U("network", net=ref) if ref else None)
            if tgt: add(g, N, NORIA_EXT.supportsNetwork, tgt)

        for node in net.get("node", []):
            node_id = node.get("node-id")
            Nd = idx_node.get((nid, node_id))

            for s in node.get("supporting-node", []):
                rec = {"network-ref": s.get("network-ref"), "node-ref": s.get("node-ref")}
                add_supports_node(g,    Nd, rec)
                add_supports_network(g, Nd, rec)

            for tp in node.get("ietf-network-topology:termination-point", []):
                tpid = tp.get("tp-id")
                If   = idx_if.get((nid, node_id, tpid))
                stp  = tp.get("supporting-termination-point") or {}
                if isinstance(stp, dict):
                    rec = {
                        "tp-ref":      stp.get("tp-ref"),
                        "node-ref":    stp.get("node-ref"),
                        "network-ref": stp.get("network-ref"),
                    }
                    add_supports_interface(g, If, rec)
                    add_supports_node(g,      If, rec)
                    add_supports_network(g,   If, rec)

        for link in net.get("ietf-network-topology:link", []):
            lid = link.get("link-id")
            L   = idx_link.get((nid, lid))
            su  = link.get("supporting-link") or {}
            if isinstance(su, dict) and (su.get("link-ref") or su.get("network-ref")):
                add_supports_link(g, L, su)

    g.serialize(out_ttl, format="turtle")

# ========================= main =========================
def main():
    in_dir = "."
    jobs = [
        ("pwe3-static-topology.json",               "pwe3-static-topology.ttl",              map_pwe3),
        ("pwe3-dynamic-topology.json",              "pwe3-dynamic-topology.ttl",             map_pwe3),
        ("mock-dm-ISIS-instance.json",              "mock-dm-ISIS-instance.ttl",             lambda p,o: map_isis(p,o,include_config_refs=False)),
        ("mock-dm-ISIS-instance_config_refs.json",  "mock-dm-ISIS-instance_config_refs.ttl", lambda p,o: map_isis(p,o,include_config_refs=True)),
    ]
    for src_name, out_name, fn in jobs:
        src = os.path.join(in_dir, src_name)
        if not os.path.exists(src):
            print(f"[SKIP] {src_name} not found")
            continue
        print(f"[INFO] {src_name} -> {out_name}")
        fn(src, out_name)
    print("[DONE] Conversion complete.")

if __name__ == "__main__":
    main()
