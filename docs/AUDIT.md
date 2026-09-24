# Audit and hardening — 0.1.2a1

Date: 2026-09-23. Source: JY-S018-P001 / 0.1.1-partial / run-0001 / product.
Reviewed all model validation, graph, mapping, removal, comparison and risk code.
Original source remains separate from this checkout.

## Repaired findings

- A design_digest key alone bypassed validation after callers changed content.
  All public analysis functions now validate the schema and recompute the digest.
- Required fields, unhashable references and duplicate support entries were
  insufficiently checked, causing exceptions or incorrect single-satisfier logic.
  Explicit bounded validation now rejects these cases as DesignError.
- Recursive DFS failed on valid long graphs. Iterative articulation traversal
  avoids recursion depth; tested against exhaustive small-graph ground truth.
- Articulation points were presented as complete, proven single points of
  failure. Results now state the undirected structural limit, and separate
  sole declared support risks identify relevant leaf/isolated components.
- Empty explicit scenario lists unexpectedly triggered default analysis.
  Empty lists now mean no scenarios; default expansion is capped at 100 with
  an explicit omission count. Scenarios add disconnected groups and weakened NFRs.
- Comparisons conflated equal NFR names with different targets and accepted
  duplicate NFR names/design names. Names now validate; incompatible positive-
  weight targets block ranking with evidence.
- Large finite weights could overflow their sum, and early rounding obscured
  close scores. Scale normalization and unrounded arithmetic repair both.
- Report authority flags and content binding were inconsistent. Mapping,
  scenario, comparison and full reports now carry advisory flags and digests.

## Verification and release

21 inherited tests passed before changes. 59 source and installed-wheel tests
pass afterward, including 38 regressions. One inherited arithmetic assertion now
checks the unrounded total. Graph verification includes a 1,500-node chain and
all 64 undirected graphs on four labeled vertices.

Historical check evidence is retained separately. CI covers Linux Python
3.10/3.12/3.14 and Windows Python 3.12. Version 0.1.1-partial -> 0.1.2a1;
reload raw designs and regenerate reports because validation, digests and
comparison behavior changed.

Added packaging, pinned-action CI, README, security documentation and Apache 2.0
LICENSE/NOTICE naming RUSSELL PHILIP SMITHSON. No third-party runtime dependencies
require upgrades. No build-tool vulnerability scan or exhaustive security audit
is claimed. The original acceptance catalog and phase roadmap remain unimplemented.
