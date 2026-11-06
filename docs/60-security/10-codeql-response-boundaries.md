# CodeQL response-boundary review

Date: 2026-11-06. Baseline: main `ba10e1321f5c0b9f82f711f3c16bf881585c1821`.

## Reviewed findings

| Alerts | Boundary | Assessment and change |
| --- | --- | --- |
| 5, 6 | DOM selection to React link URL | React escapes attributes and the URL has a fixed prefix; the reported path is not evidence of HTML execution. Encode the candidate/publication path segment explicitly so DOM text cannot become path syntax. |
| 1 | S2S query errors | Existing responses already restricted messages by equality. Return the matching constant from the public vocabulary, rather than the original exception string. Preserve 409/422 behavior. |
| 2 | Business HTTP errors | Broad ValueError/TypeError handlers could expose dependency diagnostics. Use explicit public error vocabularies and route-specific fallback codes. Apply the same boundary to custom domain exceptions. |
| 3 | Publication distribution errors | Existing responses already restricted messages by equality. Return trusted constants and preserve retirement, paused and missing-publication responses. |
| 4 | Local mock identity provider redirect header | The fixture is loopback-only and normally requires an exact configured redirect. Still reject control characters before emitting headers and URL-encode the header value. |

The review does not equate all six findings with demonstrated exploitable
production vulnerabilities. No finding is suppressed or dismissed to obtain a
passing result; the PR and main CodeQL analyses provide the final scan result.

## Error contract

`public_error` returns an exact constant from a caller-owned tuple, or its
constant fallback. It never returns arbitrary exception text. Prefix checks
are insufficient: a message can begin with a valid code and still contain a
private path or parser input. New public domain codes must be added explicitly.

Business errors retain their existing HTTP statuses and no-store responses.
Unknown internal diagnostics receive a bounded generic error. Access control
still runs before the protected operation.

## Verification

- `tests/test_public_errors.py`: exact-code selection, unknown diagnostics,
  known-code-plus-diagnostic rejection, authenticated business responses,
  lifecycle and ontology handlers, S2S responses, distribution responses,
  redirect header control characters, and encoded frontend path segments.
- Existing business, authentication, S2S, publication retirement, coordinate,
  ontology and upload regression tests continue to cover the public contracts.
- Frontend TypeScript/Vite build, complete CI suite, CodeQL for both languages,
  dependency audit, and staged source/archive secret scanning are required.
- Releases follow the existing GitHub tag and production Environment workflow.
