# Security and interpretation boundaries

The analyzer reads caller-supplied JSON-like models and emits advisory reports.
It performs no deployment, approval, network interaction or source execution.
Requirements, support mappings, targets and component kinds are unverified
assertions. Graph results do not establish runtime reliability or target achievement.

All edges are treated as undirected. Cascades, AND/OR dependencies, quorum,
shared infrastructure and failure probabilities are not modeled. Human reviewers
must interpret every risk and validate the operational architecture separately.
The comparison's 1/0.5/0 score is a declared-coverage heuristic only.

Content digests do not provide authenticity, signatures, access control or
tamper-proof storage. Keep trusted baselines and enforce authorization in an
integration. Reports retain component names, source metadata and targets, with no
secret or personal-data redaction. Treat text as untrusted when rendering.

Count, depth and byte limits protect routine inputs; they are not an OS isolation
boundary against hostile in-process objects or every memory exhaustion scenario.
Exposed services need request size limits and process isolation. No third-party
runtime dependencies exist, and no build-tool vulnerability scan is claimed.
Report defects privately with synthetic models.
