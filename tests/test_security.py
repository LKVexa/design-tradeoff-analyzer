import copy
import hashlib
import itertools
import json
import math
import unittest
from designanalyzer.core import (DesignError, analyze, load_design,
    single_points_of_failure, support_map, trade_off, what_if_remove)
from tests.test_designanalyzer import DESIGN_A, DESIGN_B


def small(edges=()):
    return {"name": "small", "components": [{"id": c, "kind": "service"} for c in "abcd"],
            "connections": [{"from": a, "to": b} for a, b in edges],
            "requirements": [], "nfrs": []}


class Regression(unittest.TestCase):
    def test_tampered_design_rejected_by_all_apis(self):
        d = load_design(DESIGN_A)
        d["requirements"][0]["supported_by"] = []
        operations = (lambda: analyze(d), lambda: support_map(d),
            lambda: single_points_of_failure(d), lambda: what_if_remove(d, "db"),
            lambda: trade_off([d], {"availability": 1}))
        for operation in operations:
            with self.assertRaises(DesignError):
                operation()

    def test_fake_digest_rejected(self):
        d = dict(DESIGN_A, design_digest="sha256:fake")
        with self.assertRaises(DesignError):
            analyze(d)

    def test_reserved_digest_rejected_on_load(self):
        with self.assertRaises(DesignError):
            load_design(load_design(DESIGN_A))

    def test_unhashable_connection_endpoint(self):
        raw = dict(DESIGN_A, connections=[{"from": [], "to": "api"}])
        with self.assertRaises(DesignError):
            load_design(raw)

    def test_unhashable_support_reference(self):
        raw = copy.deepcopy(DESIGN_A)
        raw["requirements"][0]["supported_by"] = [[]]
        with self.assertRaises(DesignError):
            load_design(raw)

    def test_duplicate_support_rejected(self):
        raw = copy.deepcopy(DESIGN_A)
        raw["nfrs"][1]["satisfied_by"] = ["cache", "cache"]
        with self.assertRaises(DesignError):
            load_design(raw)

    def test_required_display_fields_checked(self):
        for field, key in (("components", "kind"), ("requirements", "text"),
                           ("nfrs", "name"), ("nfrs", "target")):
            raw = copy.deepcopy(DESIGN_A)
            del raw[field][0][key]
            with self.subTest(field=field, key=key), self.assertRaises(DesignError):
                load_design(raw)

    def test_blank_and_control_identifiers_rejected(self):
        for name in ("", " ", " a", "a\u202eb", "a\u2028b", "x" * 513):
            with self.subTest(name=name), self.assertRaises(DesignError):
                load_design(dict(DESIGN_A, name=name))

    def test_duplicate_nfr_names_rejected(self):
        raw = copy.deepcopy(DESIGN_A)
        raw["nfrs"][1]["name"] = "availability"
        with self.assertRaises(DesignError):
            load_design(raw)

    def test_json_mixed_keys_rejected(self):
        with self.assertRaises(DesignError):
            load_design(dict(DESIGN_A, extra={1: "x", "x": 1}))

    def test_json_cycles_rejected(self):
        extra = []
        extra.append(extra)
        with self.assertRaises(DesignError):
            load_design(dict(DESIGN_A, extra=extra))

    def test_json_surrogate_rejected(self):
        with self.assertRaises(DesignError):
            load_design(dict(DESIGN_A, extra="\ud800"))

    def test_component_limit(self):
        raw = small()
        raw["components"] = [{"id": str(i), "kind": "s"} for i in range(2001)]
        with self.assertRaises(DesignError):
            load_design(raw)

    def test_long_graph_does_not_recurse(self):
        raw = small()
        raw["components"] = [{"id": str(i), "kind": "s"} for i in range(1500)]
        raw["connections"] = [{"from": str(i), "to": str(i + 1)} for i in range(1499)]
        points = single_points_of_failure(load_design(raw))
        self.assertEqual(set(points), {str(i) for i in range(1, 1499)})

    def test_articulations_match_exhaustive_small_graphs(self):
        possible = list(itertools.combinations("abcd", 2))
        def components(edges, removed=None):
            left, count = set("abcd") - {removed}, 0
            while left:
                count += 1
                stack = [left.pop()]
                while stack:
                    node = stack.pop()
                    adjacent = {b if a == node else a for a, b in edges if node in (a, b)}
                    for neighbor in adjacent & left:
                        left.remove(neighbor)
                        stack.append(neighbor)
            return count
        for mask in range(1 << len(possible)):
            edges = [edge for i, edge in enumerate(possible) if mask & (1 << i)]
            before = components(edges)
            expected = [c for c in "abcd" if components(edges, c) > before]
            self.assertEqual(single_points_of_failure(load_design(small(edges))), expected)

    def test_explicit_empty_scenarios_stays_empty(self):
        self.assertEqual(analyze(load_design(DESIGN_A), [])["what_if_scenarios"], [])

    def test_invalid_scenario_collection(self):
        d = load_design(DESIGN_A)
        for value in ("db", (), {}, [None], ["db", "db"]):
            with self.subTest(value=value), self.assertRaises(DesignError):
                analyze(d, value)

    def test_scenario_limit(self):
        with self.assertRaises(DesignError):
            analyze(load_design(DESIGN_A), ["db"] * 101)

    def test_default_scenario_limit_is_explicit(self):
        raw = small()
        raw["components"] = [{"id": str(i), "kind": "s"} for i in range(105)]
        raw["connections"] = [{"from": str(i), "to": str(i + 1)} for i in range(104)]
        result = analyze(load_design(raw))
        self.assertEqual(len(result["what_if_scenarios"]), 100)
        self.assertEqual(result["omitted_default_scenarios"], 3)

    def test_sole_support_leaf_in_risks(self):
        report = analyze(load_design(DESIGN_A))
        self.assertIn("db", report["sole_support_components"])
        self.assertNotIn("db", report["articulation_candidates"])
        self.assertTrue(any(r["evidence"].get("component") == "db" for r in report["risk_register"]))

    def test_nfr_partial_support_shown(self):
        result = what_if_remove(load_design(DESIGN_B), "gw1")
        self.assertEqual(result["nfrs_weakened"], [{"id": "N1", "remaining_support": ["gw2"]}])

    def test_disconnection_groups_shown(self):
        result = what_if_remove(load_design(DESIGN_A), "api")
        self.assertEqual(result["connected_groups_after"], [["cache"], ["db"], ["gateway", "web"]])
        self.assertEqual(len(result["connected_groups_before"]), 1)

    def test_reports_preserve_human_authority(self):
        d = load_design(DESIGN_A)
        for report in (analyze(d), support_map(d), what_if_remove(d, "db"),
                       trade_off([d], {"availability": 1})):
            self.assertTrue(report["advisory_only"])
            self.assertTrue(report["human_decision_required"])
            payload = {k: v for k, v in report.items() if k != "report_digest"}
            text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            self.assertEqual(report["report_digest"], "sha256:" + hashlib.sha256(text.encode()).hexdigest())

    def test_comparison_rejects_invalid_design_collection(self):
        for value in (None, {}, (), [], "design"):
            with self.subTest(value=value), self.assertRaises(DesignError):
                trade_off(value, {"latency": 1})

    def test_duplicate_comparison_names_rejected(self):
        d = load_design(DESIGN_A)
        with self.assertRaises(DesignError):
            trade_off([d, d], {"availability": 1})

    def test_comparison_target_mismatch_blocks_ranking(self):
        raw = copy.deepcopy(DESIGN_B)
        raw["nfrs"][0]["target"] = "99.999%"
        report = trade_off([load_design(DESIGN_A), load_design(raw)], {"availability": 1})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["comparison"], [])
        self.assertEqual(report["incompatible_targets"][0]["nfr"], "availability")

    def test_zero_weight_target_mismatch_does_not_block(self):
        raw = copy.deepcopy(DESIGN_B)
        raw["nfrs"][0]["target"] = "99.999%"
        report = trade_off([load_design(DESIGN_A), load_design(raw)], {"availability": 0, "latency": 1})
        self.assertEqual(report["status"], "COMPARABLE")

    def test_equivalent_numeric_targets_compare(self):
        a, b = copy.deepcopy(DESIGN_A), copy.deepcopy(DESIGN_B)
        a["nfrs"][0]["target"], b["nfrs"][0]["target"] = 99, 99.0
        self.assertEqual(trade_off([load_design(a), load_design(b)], {"availability": 1})["status"], "COMPARABLE")

    def test_large_finite_weight_total_does_not_overflow(self):
        result = trade_off([load_design(DESIGN_A)], {"availability": 1e308, "latency": 1e308})
        self.assertEqual(result["weights"], {"availability": .5, "latency": .5})
        self.assertEqual(result["comparison"][0]["total"], .75)

    def test_huge_integer_weight_error_contract(self):
        with self.assertRaises(DesignError):
            trade_off([load_design(DESIGN_A)], {"latency": 10 ** 1000})

    def test_positive_weight_underflow_rejected(self):
        with self.assertRaises(DesignError):
            trade_off([load_design(DESIGN_A)], {"latency": 1e308, "availability": 5e-324})

    def test_close_comparisons_preserve_precision(self):
        a, b = copy.deepcopy(DESIGN_A), copy.deepcopy(DESIGN_B)
        a["name"], b["name"] = "a", "z"
        result = trade_off([load_design(a), load_design(b)], {"availability": .500001, "latency": .5})
        rows = result["comparison"]
        self.assertEqual(rows[0]["design"], "z")
        self.assertEqual(rows[0]["display_total"], rows[1]["display_total"])
        self.assertGreater(rows[0]["total"], rows[1]["total"])
        for row in rows:
            self.assertEqual(row["total"], math.fsum(p["weight"] * p["component_score"] for p in row["arithmetic"]))

    def test_comparison_includes_mapping_provenance(self):
        row = trade_off([load_design(DESIGN_A)], {"latency": 1})["comparison"][0]
        part = row["arithmetic"][0]
        self.assertEqual(part["nfr_id"], "N2")
        self.assertEqual(part["declared_support"], ["cache"])
        self.assertEqual(part["target"], "p95<200ms")

    def test_invalid_component_lookup_contract(self):
        with self.assertRaises(DesignError):
            what_if_remove(load_design(DESIGN_A), [])

    def test_input_and_report_snapshots_detached(self):
        d = load_design(DESIGN_A)
        report = analyze(d)
        report["support_map"]["by_component"]["db"]["requirements"].append("fake")
        self.assertNotIn("fake", support_map(d)["by_component"]["db"]["requirements"])

    def test_disconnected_graph_and_self_loops(self):
        d = load_design(small([("a", "b"), ("b", "c"), ("b", "b"), ("a", "b")]))
        self.assertEqual(single_points_of_failure(d), ["b"])

    def test_weight_key_validation(self):
        for weights in ({1: 1}, {"": 1}, {"x": 0}, {"x": -1}, {"x": True}):
            with self.subTest(weights=weights), self.assertRaises(DesignError):
                trade_off([load_design(DESIGN_A)], weights)

    def test_absent_nfr_is_explicit(self):
        part = trade_off([load_design(DESIGN_A)], {"unlisted": 1})["comparison"][0]["arithmetic"][0]
        self.assertEqual(part["coverage"], "absent")
        self.assertIsNone(part["nfr_id"])
        self.assertEqual(part["component_score"], 0)
