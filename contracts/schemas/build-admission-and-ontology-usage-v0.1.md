# Build admission and single-scene ontology usage 0.1

## N20: admission receipt

First coverage: newly admitted `ply_pointcloud` jobs. Other input formats and
historical jobs remain unrecorded. `PreviewInputs.resolve` rereads and parses the
declared files, checks digests, and compares effective registration, under the
existing serialized runtime mutation lock. Coordinate revisions retain the
existing explicit-confirmation and matching saved-preflight requirements.

After those checks and batch admission, before spawning a worker, job.json stores
`build_admission`: profile, originating job ID, UTC checked_at, method version,
input ID, SHA256 of the path-free input_binding, optional saved-preflight sequence
required by coordinate admission, passed status, source_files_checked, and SHA256
of the remaining receipt fields. Digests use Python JSON sort_keys, ASCII escapes,
compact separators, UTF-8. This is integrity metadata, not a signature.

Saved preflight is separate: an optional sequence records a coordinate-admission
prerequisite, never substitutes for resolve. The receipt records admission checks,
not worker success. The worker independently reads/checks files, validates the
receipt and preserves it in the frozen source; changed files fail execution.
Frozen-view and semantic/business/relation derivations inherit the original
receipt without claiming a new source check. Raw-input retries acquire a new
receipt with their own job ID; idempotent replay returns the original attempt.

The task is atomically replaced on local disk before Popen. A receipt/job write
failure prevents launch; it may leave an empty task directory. Spawn failure
persists a failed task and receipt. Restart marks queued/running jobs interrupted;
the receipt remains an admission observation. This is not a cross-store transaction
and does not protect external files against changes after checking. Candidate
access/composition checks task-source equality. Fixed publication source preserves
the receipt and publication manifest digest protects its snapshot. Provenance
reports recorded/invalid/not_recorded; old preflight_sequence stays null for API
compatibility. New optional fields require no DB migration; old images ignore them
and cannot enforce the new binding checks. Roll back image only after stopping
active tasks; preserve runtime data, then revalidate before resuming builds.

## N22: scoped usage observation

GET `/api/ontology-usage` accepts only space_id, ontology_id, version, sha256,
offset (0–10000, default0), limit (1–100, default20). Authentication, subscription,
current scene data.manage + space.preview, and exact workspace/shared rule read
are required. Authorization precedes scanning. Each request rechecks current
policy; no persisted count or global unused conclusion exists.

Reuse job/publication metadata without index, worker polling, full geometry or ZIP.
At most10000 source metadata records are examined, each at most262144 bytes,
including bounded model manifests. Ownership is checked before model reads and
filtering by fixed ontology_ref (all three fields). Candidates must have succeeded;
publications use their own fixed model manifest and verify its stored digest.
This checks declared metadata references, not rule/geometry/object compatibility.
Foreign-scene records contribute no returned identities, names, counts or rows.
Malformed ownership/metadata, missing models or exhausted budget yield partial
without offending paths or counts. A coarse partial flag can reflect an unreadable
global metadata record; it discloses no attributable scene information.

Items sort by kind/id; total is observed matching rows, even when partial, not a
global reference count. next_offset paginates that request-time observation.
Independent reads and pages are not transactional; refresh restarts observation.
The UI keeps the fixed rule in the URL and explicitly sets the queried scene in
the existing scene context. Comparison offers separate current/target queries.
Links hand off candidate and publication distinctly without changing selection,
upgrading ontology, annotating or publishing. Full workspace indexing and
automatic migration remain outside this contract.
