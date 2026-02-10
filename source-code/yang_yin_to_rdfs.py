#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YIN (RDF) -> RDFS/OWL neutral schema converter
----------------------------------------------
- Flattens all public IRIs to: BASE/<module>/<local-name>
- Classes: YIN List/Container
- Datatype properties: YIN Leaf  (domain=nearest structural parent class; range from yin:type)
- Object properties (2 kinds):
    (A) Hierarchy containment: parent(List/Container) -> child(List/Container) as "has<Child>"
    (B) Leafref links (e.g., source-node, dest-tp, supporting-*) with proper ranges
- Keeps rdfs:label / yin:description as annotations
- prov:wasDerivedFrom points to the *flattened Huawei IRI of the source term* (no 'eurecom')

References (structure & semantics): RFC 8345 (ietf-network / topology) and YANG trees for
ietf-network / ietf-network-topology. (Used only for design alignment)
"""

import argparse
import re
from typing import Optional, Iterable

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL, XSD, NamespaceManager

# Namespaces (YIN is only used to READ the source triples)
PROV = Namespace("http://www.w3.org/ns/prov#")
YIN  = Namespace("http://yang.eurecom.fr/yin#")  # source model predicates only

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Convert YIN RDF to flattened RDFS/OWL schema")
    p.add_argument("--in", dest="infile", required=True, help="Input YIN-as-RDF Turtle")
    p.add_argument("--out", dest="outfile", required=True, help="Output RDFS/OWL Turtle")
    p.add_argument("--base_ns", default="http://www.huawei.com/ontology/ietf-topology/",
                   help="Base namespace for all generated IRIs (default: %(default)s)")
    return p.parse_args()

# ---------- utils ----------
_PCT = {"%28":"(", "%29":")", "%3D":"=", "%5D":"]", "%2F":"/", "%3A":":", "%3F":"?"}

def pct_decode(s: str) -> str:
    for k, v in _PCT.items():
        s = s.replace(k, v)
    return s

def norm_token(s: str) -> str:
    s = pct_decode(s)
    s = re.sub(r"[\s:/\?\[\]\(\)\.]+", "-", s)
    s = re.sub(r"[^A-Za-z0-9_\-]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "unnamed"

def last_seg(u: URIRef) -> str:
    return str(u).rstrip("/").split("/")[-1]

def module_from(u: URIRef) -> str:
    m = re.search(r"/module/([^/]+)/", str(u))
    return norm_token(m.group(1)) if m else "module"

def local_from(u: URIRef) -> str:
    return norm_token(last_seg(u))

def flat_iri(base: str, yin_term: URIRef) -> URIRef:
    return URIRef(f"{base.rstrip('/')}/{module_from(yin_term)}/{local_from(yin_term)}")

def to_camel(s: str) -> str:
    # "termination-point" -> "TerminationPoint"
    return "".join(p.capitalize() for p in s.split("-") if p)

def add_ann(out: Graph, term: URIRef, yin_g: Graph, yin_term: URIRef, base_ns: str):
    # rdfs:label
    label = None
    for _, _, lab in yin_g.triples((yin_term, RDFS.label, None)):
        if isinstance(lab, Literal):
            label = str(lab); break
    if not label:
        label = local_from(yin_term).replace("-", " ")
    out.add((term, RDFS.label, Literal(label)))
    # description
    for _, _, desc in yin_g.triples((yin_term, YIN["description"], None)):
        out.add((term, RDFS.comment, desc))
    # provenance WITHOUT eurecom (use flattened IRI of the source)
    out.add((term, PROV.wasDerivedFrom, flat_iri(base_ns, yin_term)))

def collect(s: Iterable) -> set:
    return set(s)

def get_parent(yin_g: Graph, term: URIRef) -> Optional[URIRef]:
    for _,_,p in yin_g.triples((term, YIN["parent"], None)):
        return p
    s = str(term)
    return URIRef(s.rsplit("/",1)[0]) if "/" in s else None

def climb_to_domain(yin_g: Graph, class_map: dict, start: URIRef, max_depth=12) -> Optional[URIRef]:
    parent = get_parent(yin_g, start)
    hops = 0
    while parent is not None and hops < max_depth:
        dom = class_map.get(parent)
        if dom is not None:
            return dom
        parent = get_parent(yin_g, parent)
        hops += 1
    return None

def xsd_range(yin_g: Graph, leaf: URIRef) -> URIRef:
    for _,_,ty in yin_g.triples((leaf, YIN["type"], None)):
        seg = last_seg(ty).lower()
        if str(ty).startswith(str(XSD)):
            return ty
        if seg in ("string","enumeration","identityref"): return XSD.string
        if seg in ("bool","boolean"): return XSD.boolean
        if seg in ("float","double","decimal"): return XSD.decimal
        if "int" in seg: return XSD.integer
    return XSD.string

def is_leafref(yin_g: Graph, term: URIRef) -> bool:
    if (term, RDF.type, YIN["Leafref"]) in yin_g:
        return True
    for _,_,t in yin_g.triples((term, YIN["type"], None)):
        if "leafref" in last_seg(t).lower():
            return True
    # some models mark key refs; treat name ending with -ref as leafref
    if local_from(term).endswith("-ref"): return True
    return False

def guess_target_name(yin_g: Graph, lref: URIRef) -> Optional[str]:
    # explicit path if present
    for _,_,p in yin_g.triples((lref, YIN["leafrefPath"], None)):
        return local_from(p)
    # name/label heuristics
    loc = local_from(lref)
    if loc.endswith("-ref"): return loc[:-4]
    for _,_,lab in yin_g.triples((lref, RDFS.label, None)):
        m = re.search(r"([A-Za-z0-9_-]+)-ref$", str(lab))
        if m: return norm_token(m.group(1))
    return None

# ---------- main ----------
def main():
    args = parse_args()
    base = args.base_ns

    yin_g = Graph()
    yin_g.parse(args.infile, format="turtle")

    out = Graph()
    nm = NamespaceManager(out)
    nm.bind("owl", OWL); nm.bind("rdfs", RDFS); nm.bind("xsd", XSD); nm.bind("prov", PROV)
    out.namespace_manager = nm

    # Classes from structural nodes
    yin_lists = collect(yin_g.subjects(RDF.type, YIN["List"]))
    yin_conts = collect(yin_g.subjects(RDF.type, YIN["Container"]))
    struct_nodes = sorted(yin_lists | yin_conts, key=lambda u: str(u))

    class_map: dict[URIRef, URIRef] = {}
    for y in struct_nodes:
        c = flat_iri(base, y)
        class_map[y] = c
        out.add((c, RDF.type, OWL.Class))
        add_ann(out, c, yin_g, y, base)

    # Helper: index local-name -> classes (for leafref range)
    local2classes: dict[str, set[URIRef]] = {}
    for y, c in class_map.items():
        ln = local_from(y)
        local2classes.setdefault(ln, set()).add(c)

    # ---------- Datatype properties from Leaf ----------
    for leaf in yin_g.subjects(RDF.type, YIN["Leaf"]):
        dom = climb_to_domain(yin_g, class_map, leaf)
        if dom is None:
            continue
        p = flat_iri(base, leaf)
        out.add((p, RDF.type, OWL.DatatypeProperty))
        out.add((p, RDFS.domain, dom))
        out.add((p, RDFS.range, xsd_range(yin_g, leaf)))
        add_ann(out, p, yin_g, leaf, base)

    # ---------- Object properties (leafrefs) ----------
    leafref_candidates = collect(yin_g.subjects(RDF.type, YIN["Leafref"]))
    # include Leaves that smell like refs
    for leaf in yin_g.subjects(RDF.type, YIN["Leaf"]):
        if is_leafref(yin_g, leaf):
            leafref_candidates.add(leaf)

    for ref in leafref_candidates:
        dom = climb_to_domain(yin_g, class_map, ref)
        if dom is None:
            continue
        p = flat_iri(base, ref)  # property IRI mirrors leaf name (e.g., source-node)
        out.add((p, RDF.type, OWL.ObjectProperty))
        out.add((p, RDFS.domain, dom))
        add_ann(out, p, yin_g, ref, base)

        tgt_name = guess_target_name(yin_g, ref)
        if tgt_name and tgt_name in local2classes:
            for rng in sorted(local2classes[tgt_name], key=lambda u: str(u)):
                out.add((p, RDFS.range, rng))

    # ---------- Object properties (hierarchy containment) ----------
    # use explicit YIN structure relations when available
    RELS = [YIN["hasList"], YIN["hasContainer"]]
    for parent in struct_nodes:
        parent_cls = class_map.get(parent)
        if parent_cls is None:
            continue
        for rel in RELS:
            for _, _, child in yin_g.triples((parent, rel, None)):
                child_cls = class_map.get(child)
                if child_cls is None:
                    continue
                # has<ChildLocalCamel>
                child_local = local_from(child)
                prop_local = f"has{to_camel(child_local)}"
                prop = URIRef(f"{base.rstrip('/')}/{module_from(parent)}/{prop_local}")
                out.add((prop, RDF.type, OWL.ObjectProperty))
                out.add((prop, RDFS.domain, parent_cls))
                out.add((prop, RDFS.range, child_cls))
                out.add((prop, RDFS.label, Literal(prop_local)))
                # provenance to Huawei-IRI of child node (no eurecom)
                out.add((prop, PROV.wasDerivedFrom, flat_iri(base, child)))

    # Save
    out.serialize(destination=args.outfile, format="turtle")
    print(f"Wrote: {args.outfile}")

if __name__ == "__main__":
    main()
