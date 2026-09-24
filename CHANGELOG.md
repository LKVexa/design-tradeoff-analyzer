# 0.1.2a1 — 2026-09-23

- Revalidate digest-bound models at every analysis entry point.
- Bound model structures and use iterative graph traversal.
- Distinguish articulation candidates from sole declared support.
- Respect explicit empty scenarios and expose graph splits and weakened NFRs.
- Block incompatible-target comparisons and preserve scoring precision.
- Add 38 regressions, packaging, CI, README and Apache 2.0 LICENSE/NOTICE.
- Compatibility: reload raw models and regenerate comparison reports.

# Changelog — Design Analyzer for Trade-Off and Risk

## 0.1.1-partial (2026-09-14)

Maintenance/hardening release (repairs only; no new public API, no
capability removed). Baseline fingerprint: build-0001 product.zip
sha256 f8fd58ff90c4a8a1c54edf42e7bd8d3c4d5dc4c1dee48c824f3a9f90697b10a8
(version 0.1.0-partial). All findings below were reproduced on the
baseline with live probes before fixing.

### Fixes
- A015-F1 (high) — validation bypass: an NFR carrying a decoy
  `supported_by` key skipped validation of its `satisfied_by` list
  (`load_design` used `r.get("supported_by", r.get("satisfied_by", []))`),
  so unknown component references passed load and later crashed
  `support_map`/`analyze` with bare `KeyError: 'ghost'`. Observed:
  load accepted `satisfied_by: ["ghost"]`; expected: DesignError at load.
  Requirements and NFRs are now validated on their own field.
- A015-F2 (high) — aliasing: `load_design` returned a shallow copy
  sharing nested lists/dicts with the caller's input; mutating the raw
  input after load silently mutated the "validated" design while
  `design_digest` stayed stale (evidence-grounding broken). The loaded
  design is now an independent deep (canonical JSON) copy.
- A015-F3 (medium) — error-contract leaks: malformed inputs (non-dict
  design, non-dict components/connections/requirements, unhashable ids)
  raised bare TypeError/AttributeError, and passing an unvalidated dict
  to `what_if_remove`/`trade_off` raised bare `KeyError:
  'design_digest'`. All analysis entry points now raise the documented
  DesignError; analysis functions require a design produced by
  `load_design`.
- A015-F4 (medium) — weight validation: `trade_off` accepted NaN and
  Infinity weights (producing NaN totals and undefined row ordering)
  and negative weights whenever the sum stayed positive. Weights must
  now be finite, non-negative numbers with a positive sum.
- A015-F5 (medium) — non-strict canonicalization: NaN/Infinity values
  inside a design were serialized with Python's non-standard JSON
  extension, yielding a non-interoperable "canonical" digest. `_digest`
  now uses `allow_nan=False` and rejects such designs with DesignError.
- A015-F6 (low) — duplicate `requirements`/`nfrs` ids were accepted and
  silently conflated in support maps and reports; duplicates are now
  rejected at load.

### Tests
- 13 baseline tests unchanged and passing; 8 new regression tests
  (positive + negative) covering F1–F6. Total 21 passing.

### Compatibility
- Reports keep schema `designanalyzer/report/v1`; `analyzer_version`
  now reports `0.1.1-partial`. Behavior changes only for inputs that
  were previously malformed/undefined (they now fail fast with
  DesignError). Well-formed designs produce identical analysis output.

### Rollback
- Restore build-0001 `product/` (baseline is preserved read-only at
  `D:\Users\russe\JY\JY-S018-P001__design-analyzer\build-0001`).

## 0.1.0-partial

- Initial partial candidate (build-0001).
