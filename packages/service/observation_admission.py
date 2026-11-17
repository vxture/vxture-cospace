"""Internal admission preflight; caller still owns authentication and scene authorization."""
from packages.data.evidence_content import check_evidence_content
from packages.infrastructure.spatial_observation_store import MAX_BATCH
from packages.spatial.opening_observations import Report, Scope
from packages.spatial.scene_identity import content_digest


def append_with_evidence(journal, scope, reports, *, authenticated_producer, evidence_root):
    """Check all evidence before one atomic append; never open a public write route.

    Receipt is returned to the trusted caller, not stored as a verification flag.
    The journal retains its original unverified report semantics.
    """
    if not isinstance(reports, list) or not 1 <= len(reports) <= MAX_BATCH:
        raise ValueError('observation_batch_budget')
    scope = Scope.model_validate(scope).model_dump()
    models = [Report.model_validate(report) for report in reports]
    if any(report.producer != authenticated_producer for report in models):
        raise ValueError('observation_authenticated_producer_mismatch')
    if any(not journal.registered(scope, entity) for entity in {report.entity_id for report in models}):
        raise ValueError('observation_subject_not_registered')
    documents = [report.model_dump() for report in models]
    context = {'scope': scope, 'reports': documents}
    digests = sorted({digest for report in models for digest in report.evidence_sha256})
    receipt = check_evidence_content(evidence_root, [{'id': 'sha256-' + digest, 'sha256': digest} for digest in digests],
                                     document_sha256=content_digest(context))
    records = journal.append_batch(scope, documents, authenticated_producer=authenticated_producer)
    return {'profile': 'cospace.observation-admission/0.1', 'records': records, 'evidence_receipt': receipt,
            'source_identity_verified': False, 'clock_quality_verified': False, 'real_release_ready': False}
