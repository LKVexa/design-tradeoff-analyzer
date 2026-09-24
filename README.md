# Design Trade-Off Analyzer

**0.1.2a1 — experimental partial candidate, JY-S018-P001**

A Python library that validates declared component designs, maps support for
requirements and non-functional requirements (NFRs), explores component removal,
and compares declared NFR coverage. All reports are advisory and require human
interpretation. It neither establishes operational reliability nor approves designs.

## Install and use

Python 3.10 or newer; no third-party runtime dependencies.

~~~sh
python -m pip install .
python -m unittest discover -s tests -t .
~~~

~~~python
from designanalyzer.core import load_design, analyze, what_if_remove, trade_off

design = load_design({
    "name": "example",
    "components": [{"id": "api", "kind": "service"},
                   {"id": "db", "kind": "datastore"}],
    "connections": [{"from": "api", "to": "db"}],
    "requirements": [{"id": "R1", "text": "persist records",
                      "supported_by": ["db"]}],
    "nfrs": [{"id": "N1", "name": "availability", "target": "99.9%",
             "satisfied_by": []}],
})
report = analyze(design, what_if_components=["db"])
scenario = what_if_remove(design, "db")
comparison = trade_off([design], {"availability": 1})
~~~

## Meaning of the analysis

Connections are projected onto an **undirected simple graph**. Direction,
connection labels, protocols, capacity, quorum, shared infrastructure, fault
domains and runtime behavior are not modeled. Parallel edges collapse, and
self-loops do not create articulation points.

The compatibility function single_points_of_failure returns articulation
candidates: removing such a vertex increases the graph's connected-component
count. It is not a complete list of system failure points. Reports also expose
articulation_candidates and separately list sole_support_components from direct
requirement/NFR mappings. An isolated or leaf component can be the sole declared
supporter without being an articulation point.

Support mappings are caller assertions, not measured achievement. Removal
scenarios list lost and weakened direct support, weakened NFR support, and graph
groups before/after removal. Remaining support does not prove continuity.
There is no cascading failure, all-of/any-of dependency, availability or
probabilistic reliability calculation.

Risk severity is a fixed review heuristic: unsupported requirements and sole
requirement supporters are high; unsupported NFRs, sole NFR supporters and
articulation candidates are medium. This is not calibrated risk quantification.
Every risk cites the design digest and relevant declared element.

analyze(design) includes at most the first 100 sorted articulation scenarios and
reports omitted_default_scenarios explicitly. Pass an explicit component list to
choose up to 100 scenarios. An empty list requests none.

## Trade-off comparison

NFR names must be unique within each design, and compared designs need unique
names. Positive-weight NFRs with different targets block ranking with an explicit
incompatible_targets list. String targets compare exactly; numeric targets
compare numerically. Units or equivalent prose are not inferred.

The coverage heuristic gives 1 for a declared supporting component, 0.5 for an
NFR declared without support, and 0 for an absent NFR. The retained compatibility
label satisfied means declared support only. No test or measured target achievement
is implied. Arithmetic includes the NFR ID, target and declared supporters.
Absent names remain visible as zero coverage.

Weights must be finite and nonnegative with a positive total. Scale normalization
avoids overflow for large finite weights; unrepresentable positive ratios are
rejected. Components retain float precision through ranking; display_total alone
rounds to four decimals. spof_count is an articulation count, not a measured
failure count. Ranking ties sort by design name. Humans choose the architecture.

## Integrity, limits and compatibility

load_design returns an independent snapshot with a canonical SHA-256 digest.
Every analysis entry point validates the schema and recomputes that digest.
Reports have their own content digest and human-authority flags. Hashes detect
accidental mismatch but do not authenticate source assertions or stop a caller
from rewriting data and recomputing hashes.

Limits: 2,000 components, 10,000 connections, 2,000 requirements, 2,000 NFRs,
50 compared designs, 100 weights and 100 explicit scenarios. Labels are at most
512 characters and other text 65,536; JSON depth is at most 40. Models and
exported reports are limited to 16 MiB, including the combined comparison inputs.
Support references must be unique, known component IDs. Invalid input raises
DesignError. Unknown metadata is retained in the digest but not interpreted.

Version 0.1.1-partial -> 0.1.2a1 adds stricter required-field validation,
unique NFR names, target compatibility checks and full-precision scores.
Reload raw models and regenerate old reports. A single inherited arithmetic
assertion now recomputes the unrounded total.

59 tests include 21 inherited checks and 38 regressions. Verification includes
a 1,500-node chain and all 64 undirected graphs on four labeled vertices.
Source and installed-wheel results: [CHECK_RUNS](docs/CHECK_RUNS.json).
See [AUDIT](docs/AUDIT.md) and [SECURITY](SECURITY.md). CI tests Linux Python
3.10/3.12/3.14 and Windows Python 3.12.

The original 784-case acceptance catalog, phases P00–P15, prose/diagram
reconstruction, operational qualification and deployment remain unimplemented.
This is a partial candidate, not a production-readiness assessment.

## License

Copyright 2026 **RUSSELL PHILIP SMITHSON**.
[Apache License 2.0](LICENSE), with [NOTICE](NOTICE).
No third-party code is vendored.
