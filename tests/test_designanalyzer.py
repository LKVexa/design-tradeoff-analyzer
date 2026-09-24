import unittest
import math

from designanalyzer.core import (DesignError, analyze, load_design,
                                 single_points_of_failure, support_map,
                                 trade_off, what_if_remove)

DESIGN_A = {
    "name": "single-gateway",
    "components": [
        {"id": "web", "kind": "service"},
        {"id": "gateway", "kind": "proxy"},
        {"id": "api", "kind": "service"},
        {"id": "db", "kind": "datastore"},
        {"id": "cache", "kind": "datastore"},
    ],
    "connections": [
        {"from": "web", "to": "gateway"},
        {"from": "gateway", "to": "api"},
        {"from": "api", "to": "db"},
        {"from": "api", "to": "cache"},
    ],
    "requirements": [
        {"id": "R1", "text": "serve user pages", "supported_by": ["web", "gateway", "api"]},
        {"id": "R2", "text": "persist orders", "supported_by": ["db"]},
        {"id": "R3", "text": "fast reads", "supported_by": ["cache", "db"]},
        {"id": "R4", "text": "audit trail", "supported_by": []},
    ],
    "nfrs": [
        {"id": "N1", "name": "availability", "target": "99.9%", "satisfied_by": []},
        {"id": "N2", "name": "latency", "target": "p95<200ms", "satisfied_by": ["cache"]},
    ],
}

DESIGN_B = {
    "name": "dual-path",
    "components": [
        {"id": "web", "kind": "service"},
        {"id": "gw1", "kind": "proxy"},
        {"id": "gw2", "kind": "proxy"},
        {"id": "api", "kind": "service"},
        {"id": "db", "kind": "datastore"},
    ],
    "connections": [
        {"from": "web", "to": "gw1"}, {"from": "web", "to": "gw2"},
        {"from": "gw1", "to": "api"}, {"from": "gw2", "to": "api"},
        {"from": "api", "to": "db"},
    ],
    "requirements": [
        {"id": "R1", "text": "serve user pages", "supported_by": ["web", "gw1", "gw2", "api"]},
    ],
    "nfrs": [
        {"id": "N1", "name": "availability", "target": "99.9%",
         "satisfied_by": ["gw1", "gw2"]},
        {"id": "N2", "name": "latency", "target": "p95<200ms", "satisfied_by": []},
    ],
}


class Loading(unittest.TestCase):
    def test_valid_design(self):
        d = load_design(DESIGN_A)
        self.assertTrue(d["design_digest"].startswith("sha256:"))

    def test_validation(self):
        with self.assertRaises(DesignError):
            load_design({"name": "x"})
        bad = dict(DESIGN_A, connections=[{"from": "web", "to": "ghost"}])
        with self.assertRaises(DesignError):
            load_design(bad)
        bad2 = dict(DESIGN_A, requirements=[{"id": "R", "text": "t",
                                             "supported_by": ["ghost"]}])
        with self.assertRaises(DesignError):
            load_design(bad2)


class Dependencies(unittest.TestCase):
    def test_spof_detection(self):
        a = load_design(DESIGN_A)
        self.assertEqual(single_points_of_failure(a), ["api", "gateway"])
        b = load_design(DESIGN_B)
        self.assertEqual(single_points_of_failure(b), ["api"])  # gateways redundant

    def test_support_map_gaps(self):
        smap = support_map(load_design(DESIGN_A))
        self.assertEqual(smap["unsupported_requirements"], ["R4"])
        self.assertEqual(smap["unsatisfied_nfrs"], ["N1"])
        self.assertIn("R2", smap["by_component"]["db"]["requirements"])


class WhatIf(unittest.TestCase):
    def test_remove_sole_supporter(self):
        s = what_if_remove(load_design(DESIGN_A), "db")
        self.assertEqual([r["id"] for r in s["requirements_losing_all_support"]],
                         ["R2"])
        weakened = {r["id"]: r["remaining_support"]
                    for r in s["requirements_weakened"]}
        self.assertEqual(weakened["R3"], ["cache"])

    def test_remove_redundant_component(self):
        s = what_if_remove(load_design(DESIGN_B), "gw1")
        self.assertEqual(s["requirements_losing_all_support"], [])
        self.assertTrue(s["requirements_weakened"])

    def test_nfr_single_satisfier(self):
        s = what_if_remove(load_design(DESIGN_A), "cache")
        self.assertEqual(s["nfrs_losing_all_support"], ["N2"])

    def test_unknown_component(self):
        with self.assertRaises(DesignError):
            what_if_remove(load_design(DESIGN_A), "ghost")


class TradeOffAndRisk(unittest.TestCase):
    def test_trade_off_recomputable_no_winner_declared(self):
        cmp_ = trade_off([load_design(DESIGN_A), load_design(DESIGN_B)],
                         {"availability": 0.7, "latency": 0.3})
        for row in cmp_["comparison"]:
            self.assertEqual(row["total"],
                             math.fsum(p["weighted"] for p in row["arithmetic"]))
        # B satisfies availability (weight .7): B ahead of A
        self.assertEqual(cmp_["comparison"][0]["design"], "dual-path")
        self.assertIn("human decision", cmp_["note"])

    def test_coverage_states(self):
        cmp_ = trade_off([load_design(DESIGN_A)], {"availability": 1.0})
        p = cmp_["comparison"][0]["arithmetic"][0]
        self.assertEqual(p["coverage"], "declared-unsatisfied")

    def test_full_report(self):
        rep = analyze(load_design(DESIGN_A))
        self.assertTrue(rep["advisory_only"] and rep["human_decision_required"])
        risks = [r["risk"] for r in rep["risk_register"]]
        self.assertTrue(any("R4" in r for r in risks))
        self.assertTrue(any("single point of failure" in r for r in risks))
        for r in rep["risk_register"]:
            self.assertIn("evidence", r)                 # evidence-grounded
        self.assertEqual(len(rep["what_if_scenarios"]), 2)  # per SPOF

    def test_no_approval_api(self):
        import designanalyzer.core as m
        for name in dir(m):
            for bad in ("approve", "settle", "deploy", "accept_risk", "authorize"):
                self.assertNotIn(bad, name.lower())

    def test_deterministic(self):
        a = analyze(load_design(DESIGN_A))
        b = analyze(load_design(DESIGN_A))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


class HardeningFixes(unittest.TestCase):
    """Regression tests for findings A015-F1..F6 (0.1.1-partial)."""

    def _d(self):
        return {
            "name": "d",
            "components": [{"id": "a", "kind": "s"}, {"id": "b", "kind": "s"}],
            "connections": [{"from": "a", "to": "b"}],
            "requirements": [{"id": "R1", "text": "t", "supported_by": ["a"]}],
            "nfrs": [{"id": "N1", "name": "lat", "target": "x",
                      "satisfied_by": ["b"]}],
        }

    # F1: validation bypass via supported_by/satisfied_by fallback
    def test_f1_nfr_ghost_satisfier_rejected(self):
        bad = self._d()
        bad["nfrs"][0]["supported_by"] = []          # decoy key
        bad["nfrs"][0]["satisfied_by"] = ["ghost"]
        with self.assertRaises(DesignError):
            load_design(bad)

    def test_f1_valid_design_still_loads(self):
        d = load_design(self._d())
        self.assertNotIn("ghost", d["nfrs"][0]["satisfied_by"])

    # F2: aliasing/isolation
    def test_f2_returned_design_isolated_from_input(self):
        raw = self._d()
        d = load_design(raw)
        dig = d["design_digest"]
        raw["components"].append({"id": "evil", "kind": "x"})
        raw["requirements"][0]["supported_by"].append("evil")
        self.assertEqual([c["id"] for c in d["components"]], ["a", "b"])
        self.assertEqual(d["requirements"][0]["supported_by"], ["a"])
        self.assertEqual(load_design(self._d())["design_digest"], dig)

    # F3: error contract — malformed input raises DesignError, not bare
    # TypeError/AttributeError/KeyError
    def test_f3_malformed_inputs_raise_designerror(self):
        cases = [
            None, [],
            dict(self._d(), components=[1]),
            dict(self._d(), components="x"),
            dict(self._d(), connections=[1]),
            dict(self._d(), components=[{"id": ["u"], "kind": "s"}]),
            dict(self._d(), requirements=[1]),
            dict(self._d(), requirements=[{"id": 5, "supported_by": []}]),
            dict(self._d(), nfrs=[{"id": "N1", "satisfied_by": "a"}]),
        ]
        for bad in cases:
            with self.assertRaises(DesignError, msg=repr(bad)):
                load_design(bad)

    def test_f3_unloaded_design_raises_designerror(self):
        raw = self._d()
        with self.assertRaises(DesignError):
            what_if_remove(raw, "a")
        with self.assertRaises(DesignError):
            trade_off([raw], {"lat": 1.0})
        with self.assertRaises(DesignError):
            analyze(raw)
        with self.assertRaises(DesignError):
            support_map(raw)
        with self.assertRaises(DesignError):
            single_points_of_failure(raw)

    # F4: weight validation
    def test_f4_nonfinite_or_negative_weights_rejected(self):
        d = load_design(self._d())
        for w in ({"lat": float("nan")}, {"lat": float("inf")},
                  {"lat": 2.0, "av": -1.0}, {"lat": "1"}, {"lat": True}, {}):
            with self.assertRaises(DesignError, msg=repr(w)):
                trade_off([d], w)
        ok = trade_off([d], {"lat": 1, "av": 0.0})  # int + zero still fine
        self.assertEqual(ok["comparison"][0]["total"], 1.0)

    # F5: strict canonical digest — NaN/Infinity in the design rejected
    def test_f5_nan_in_design_rejected(self):
        bad = self._d()
        bad["nfrs"][0]["target"] = float("nan")
        with self.assertRaises(DesignError):
            load_design(bad)
        bad["nfrs"][0]["target"] = float("inf")
        with self.assertRaises(DesignError):
            load_design(bad)

    # F6: duplicate requirement/nfr ids rejected
    def test_f6_duplicate_ids_rejected(self):
        dup = self._d()
        dup["requirements"].append({"id": "R1", "text": "t2",
                                    "supported_by": []})
        with self.assertRaises(DesignError):
            load_design(dup)
        dup2 = self._d()
        dup2["nfrs"].append({"id": "N1", "name": "x", "target": "y",
                             "satisfied_by": []})
        with self.assertRaises(DesignError):
            load_design(dup2)
