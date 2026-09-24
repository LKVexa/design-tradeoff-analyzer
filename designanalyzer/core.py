"""Bounded declared-design analysis. All findings require human interpretation."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import unicodedata

VERSION = "0.1.2a1"
MAX_BYTES = 16 * 1024 * 1024


class DesignError(Exception):
    """Invalid design, analysis input or exceeded resource limit."""


def _canonical(obj):
    def validate(value, depth=0):
        if depth > 40:
            raise DesignError("JSON nesting exceeds 40 levels")
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise DesignError("JSON object keys must be strings")
            for v in value.values():
                validate(v, depth + 1)
        elif type(value) is list:
            for v in value:
                validate(v, depth + 1)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise DesignError("only JSON values are supported")
    try:
        validate(obj)
        text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise DesignError("model exceeds 16 MiB")
        return text
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise DesignError("invalid JSON model") from exc


def _digest(obj):
    return "sha256:" + hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _text(value, field, limit=65536):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise DesignError(f"{field} must be a nonempty bounded string")
    if any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value):
        raise DesignError(f"{field} must be single-line text without control characters")
    return value


def _label(value, field):
    value = _text(value, field, 512)
    if value != value.strip():
        raise DesignError(f"{field} must not have surrounding whitespace")
    return value


def _number(value):
    if type(value) not in (int, float):
        raise DesignError("expected a finite number")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise DesignError("expected a finite number") from exc
    if not math.isfinite(value):
        raise DesignError("expected a finite number")
    return value


def _mapping(value, field):
    if type(value) is not dict:
        raise DesignError(f"{field} must be an object")


def _list(value, field, limit):
    if type(value) is not list or len(value) > limit:
        raise DesignError(f"{field} must be a list with at most {limit} entries")
    return value


def _references(value, field, ids):
    values = _list(value, field, 2000)
    seen = set()
    for cid in values:
        _label(cid, field)
        if cid not in ids or cid in seen:
            raise DesignError("unknown or duplicate component reference")
        seen.add(cid)


def load_design(raw):
    """Validate a declared model and return an independent digest-bound snapshot."""
    _mapping(raw, "design")
    if "design_digest" in raw:
        raise DesignError("load_design requires raw content without design_digest")
    _canonical(raw)
    _label(raw.get("name"), "design name")
    for field, limit in (("components", 2000), ("connections", 10000),
                         ("requirements", 2000), ("nfrs", 2000)):
        _list(raw.get(field), field, limit)
    ids = set()
    for component in raw["components"]:
        _mapping(component, "component")
        cid = _label(component.get("id"), "component id")
        _label(component.get("kind"), "component kind")
        if cid in ids:
            raise DesignError("duplicate component id")
        ids.add(cid)
    for edge in raw["connections"]:
        _mapping(edge, "connection")
        for endpoint in ("from", "to"):
            cid = _label(edge.get(endpoint), "connection endpoint")
            if cid not in ids:
                raise DesignError("connection references an unknown component")
        if "label" in edge:
            _text(edge["label"], "connection label")
    names = set()
    for field, reference in (("requirements", "supported_by"), ("nfrs", "satisfied_by")):
        seen = set()
        for entry in raw[field]:
            _mapping(entry, field)
            identity = _label(entry.get("id"), field + " id")
            if identity in seen:
                raise DesignError("duplicate requirement or NFR id")
            seen.add(identity)
            if field == "requirements":
                _text(entry.get("text"), "requirement text")
            else:
                name = _label(entry.get("name"), "NFR name")
                if name in names:
                    raise DesignError("NFR names must be unique within each design")
                names.add(name)
                target = entry.get("target")
                if type(target) is str:
                    _text(target, "NFR target")
                else:
                    _number(target)
            _references(entry.get(reference, []), reference, ids)
    return dict(copy.deepcopy(raw), design_digest=_digest(raw))


def _loaded(design):
    _mapping(design, "loaded design")
    if "design_digest" not in design:
        raise DesignError("use load_design first")
    raw = {k: v for k, v in design.items() if k != "design_digest"}
    snapshot = load_design(raw)
    if snapshot != design:
        raise DesignError("design digest mismatch; reload changed source")
    return snapshot


def _report(payload):
    result = dict(payload, advisory_only=True, human_decision_required=True)
    result["report_digest"] = _digest(result)
    return result


def _adjacency(design):
    adjacency = {c["id"]: set() for c in design["components"]}
    for edge in design["connections"]:
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])
    return adjacency


def _articulations(adjacency):
    # Iterative Tarjan traversal avoids the recursion limit on long valid graphs.
    discovery, low, parent, children, points = {}, {}, {}, {}, set()
    for root in sorted(adjacency):
        if root in discovery:
            continue
        parent[root], children[root] = None, 0
        discovery[root] = low[root] = len(discovery)
        stack = [(root, iter(sorted(adjacency[root])))]
        while stack:
            node, neighbors = stack[-1]
            neighbor = next(neighbors, None)
            if neighbor is None:
                stack.pop()
                ancestor = parent[node]
                if ancestor is None:
                    if children[node] > 1:
                        points.add(node)
                else:
                    low[ancestor] = min(low[ancestor], low[node])
                    if parent[ancestor] is not None and low[node] >= discovery[ancestor]:
                        points.add(ancestor)
            elif neighbor != parent[node]:
                if neighbor in discovery:
                    low[node] = min(low[node], discovery[neighbor])
                else:
                    parent[neighbor], children[neighbor] = node, 0
                    children[node] += 1
                    discovery[neighbor] = low[neighbor] = len(discovery)
                    stack.append((neighbor, iter(sorted(adjacency[neighbor]))))
    return sorted(points)


def single_points_of_failure(design):
    """Compatibility name: returns graph articulation candidates, not proven failures."""
    return _articulations(_adjacency(_loaded(design)))


def _support(design):
    by_component = {cid: {"requirements": [], "nfrs": []}
                    for cid in sorted(_adjacency(design))}
    unsupported, unsatisfied = [], []
    for field, reference, output, gaps in (
            ("requirements", "supported_by", "requirements", unsupported),
            ("nfrs", "satisfied_by", "nfrs", unsatisfied)):
        for entry in sorted(design[field], key=lambda e: e["id"]):
            supporters = entry.get(reference, [])
            if not supporters:
                gaps.append(entry["id"])
            for cid in supporters:
                by_component[cid][output].append(entry["id"])
    return {"by_component": by_component, "unsupported_requirements": unsupported,
            "unsatisfied_nfrs": unsatisfied}


def support_map(design):
    design = _loaded(design)
    return _report(dict(_support(design), design_digest=design["design_digest"],
                        interpretation="caller-declared support; satisfaction is not independently verified"))


def _groups(adjacency, removed=None):
    remaining, groups = set(adjacency) - {removed}, []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        group, stack = [start], [start]
        while stack:
            for neighbor in sorted(adjacency[stack.pop()]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    group.append(neighbor)
                    stack.append(neighbor)
        groups.append(sorted(group))
    return groups


def _scenario(design, component_id, adjacency):
    lost, weakened, nfr_lost, nfr_weakened = [], [], [], []
    for requirement in sorted(design["requirements"], key=lambda e: e["id"]):
        supporters = requirement.get("supported_by", [])
        if component_id in supporters:
            remaining = sorted(set(supporters) - {component_id})
            (weakened if remaining else lost).append(
                {"id": requirement["id"], "remaining_support": remaining})
    for nfr in sorted(design["nfrs"], key=lambda e: e["id"]):
        supporters = nfr.get("satisfied_by", [])
        if component_id in supporters:
            remaining = sorted(set(supporters) - {component_id})
            if remaining:
                nfr_weakened.append({"id": nfr["id"], "remaining_support": remaining})
            else:
                nfr_lost.append(nfr["id"])
    return _report({
        "scenario": "remove:" + component_id,
        "requirements_losing_all_support": lost, "requirements_weakened": weakened,
        "nfrs_losing_all_support": nfr_lost, "nfrs_weakened": nfr_weakened,
        "connected_groups_before": _groups(adjacency),
        "connected_groups_after": _groups(adjacency, component_id),
        "interpretation": "direct declared support only; remaining support does not prove service continuity",
        "evidence": {"design_digest": design["design_digest"], "component": component_id}})


def what_if_remove(design, component_id):
    design = _loaded(design)
    _label(component_id, "component_id")
    adjacency = _adjacency(design)
    if component_id not in adjacency:
        raise DesignError("unknown component")
    return _scenario(design, component_id, adjacency)


def trade_off(designs, nfr_weights):
    _list(designs, "designs", 50)
    if not designs:
        raise DesignError("at least one design is required")
    _mapping(nfr_weights, "nfr_weights")
    if not 1 <= len(nfr_weights) <= 100:
        raise DesignError("1..100 NFR weights required")
    checked = {}
    for name, weight in nfr_weights.items():
        _label(name, "NFR weight name")
        weight = _number(weight)
        if weight < 0:
            raise DesignError("NFR weights must be nonnegative")
        checked[name] = weight
    largest = max(checked.values())
    if largest <= 0:
        raise DesignError("NFR weights must have positive total")
    scaled = {name: weight / largest for name, weight in checked.items()}
    total = math.fsum(scaled.values())
    weights = {name: weight / total for name, weight in sorted(scaled.items())}
    if any(checked[k] > 0 and v == 0 for k, v in weights.items()):
        raise DesignError("weight ratios underflow floating-point precision")
    designs = [_loaded(d) for d in designs]
    _canonical(designs)
    if len({d["name"] for d in designs}) != len(designs):
        raise DesignError("design names must be unique in a comparison")
    incompatible = []
    for name, weight in weights.items():
        targets = [(d["name"], n["target"]) for d in designs
                   for n in d["nfrs"] if n["name"] == name]
        # Numeric targets compare numerically; string targets compare exactly.
        if weight > 0 and any((type(t) is str) != (type(targets[0][1]) is str) or t != targets[0][1]
                              for _, t in targets[1:]):
            incompatible.append({"nfr": name, "targets": [
                {"design": design, "target": target} for design, target in targets]})
    if incompatible:
        return _report({"status": "BLOCKED", "comparison": [], "weights": weights,
                        "incompatible_targets": incompatible,
                        "design_digests": [d["design_digest"] for d in designs],
                        "note": "NFR targets differ; align targets before comparison. Architecture choice is a human decision."})
    rows = []
    for design in designs:
        nfrs = {n["name"]: n for n in design["nfrs"]}
        parts = []
        for name, weight in weights.items():
            entry = nfrs.get(name)
            covered = bool(entry and entry.get("satisfied_by"))
            score = 1.0 if covered else (0.5 if entry else 0.0)
            parts.append({"nfr": name, "weight": weight, "component_score": score,
                          "weighted": weight * score,
                          "coverage": "satisfied" if covered else "declared-unsatisfied" if entry else "absent",
                          "nfr_id": entry["id"] if entry else None,
                          "target": entry["target"] if entry else None,
                          "declared_support": sorted(entry.get("satisfied_by", [])) if entry else []})
        total = math.fsum(p["weighted"] for p in parts)
        rows.append({"design": design["name"], "design_digest": design["design_digest"],
                     "total": total, "display_total": round(total, 4), "arithmetic": parts,
                     "spof_count": len(_articulations(_adjacency(design)))})
    rows.sort(key=lambda r: (-r["total"], r["design"]))
    return _report({"status": "COMPARABLE", "comparison": rows, "weights": weights,
                    "incompatible_targets": [],
                    "note": "declared coverage comparison only; architecture choice is a human decision",
                    "scoring_rule": "1 for declared support, 0.5 for declaration without support, 0 for absent; no measured validation"})


def analyze(design, what_if_components=None):
    design = _loaded(design)
    adjacency = _adjacency(design)
    articulation = _articulations(adjacency)
    if what_if_components is None:
        selected = articulation[:100]
    else:
        _list(what_if_components, "what_if_components", 100)
        _references(what_if_components, "what_if_components", set(adjacency))
        selected = sorted(what_if_components)
    scenarios = [_scenario(design, cid, adjacency) for cid in selected]
    support = _support(design)
    risks = []
    for key, label, severity in (("unsupported_requirements", "requirement", "high"),
                                  ("unsatisfied_nfrs", "NFR", "medium")):
        for identity in support[key]:
            risks.append({"risk": f"{label} {identity} has no declared supporting component",
                          "severity": severity, "evidence": {"design_digest": design["design_digest"],
                          "requirement" if label == "requirement" else "nfr": identity}})
    sole_support = {}
    for field, reference in (("requirements", "supported_by"), ("nfrs", "satisfied_by")):
        for entry in design[field]:
            supporters = entry.get(reference, [])
            if len(supporters) == 1:
                sole_support.setdefault(supporters[0], {"requirements": [], "nfrs": []})[field].append(entry["id"])
    for cid, mappings in sorted(sole_support.items()):
        risks.append({"risk": f"component {cid} is the sole declared supporter for mapped objectives",
                      "severity": "high" if mappings["requirements"] else "medium",
                      "evidence": {"design_digest": design["design_digest"], "component": cid,
                                   **{k: sorted(v) for k, v in mappings.items()}}})
    for cid in articulation:
        risks.append({"risk": f"component {cid} is a structural single point of failure candidate",
                      "severity": "medium", "evidence": {"design_digest": design["design_digest"],
                      "component": cid, "basis": "articulation of the undirected declared connection graph"}})
    risks.sort(key=lambda r: ({"high": 0, "medium": 1}[r["severity"]], r["risk"]))
    return _report({
        "schema": "designanalyzer/report/v1", "analyzer_version": VERSION,
        "design": design["name"], "design_digest": design["design_digest"],
        "support_map": support, "single_points_of_failure": articulation,
        "articulation_candidates": articulation, "sole_support_components": sorted(sole_support),
        "what_if_scenarios": scenarios,
        "omitted_default_scenarios": max(0, len(articulation) - 100) if what_if_components is None else 0,
        "risk_register": risks,
        "boundary": "Graph structure and caller-declared support do not establish runtime failures or NFR achievement. Architecture, risk acceptance and deployment remain human decisions.",
    })
