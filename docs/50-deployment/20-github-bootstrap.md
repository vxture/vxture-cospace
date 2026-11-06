# GitHub bootstrap and worker02 release

This repository adapts the vxtpl workflows to Python 3.14 / uv and Node 24 /
pnpm / Vite. vxtpl's Next.js build and PostgreSQL initialization do not apply to
the existing CoSpace runtime and are not copied as dummy jobs.

## Source and verification

- Five required checks: quality-gate, build, test-coverage, audit, gitleaks.
- CI builds the frontend from its frozen lockfile, installs Python's frozen
  dependencies, and runs the full pytest suite. The check called test-coverage
  preserves the template's name; it does not claim measured line coverage.
- OSV scans both production lockfiles; the scheduled watcher uses the same
  pinned binary and inputs. CodeQL analyzes Python and JavaScript/TypeScript.
- Local evidence, authentication state, deployment bundles and data are ignored.
  Two synthetic fixtures required by the test suite live in tests/fixtures.
- First-party DS tarballs retain their provenance and hashes. They require an
  archive content scan before publication as well as the ordinary staged scan.
- Gitleaks is upgraded from vxtpl's pin to 8.30.1 with its release SHA-256 so
  the CI gate can also traverse archives. Run
  `python scripts/security/scan_candidate.py` locally after staging changes;
  it scans the actual Git index with redacted findings under ignored output/.
- DOCX is skipped by the scanner's built-in archive traversal. The local and CI
  gates therefore explicitly expose archive members as inert flat files, then
  scan those contents. Nested archives have depth and size limits; no original
  paths, permissions or links are restored. A synthetic canary verified direct
  DOCX and DOCX inside TGZ detection. The only added rule exception is the
  reviewed `LinkedinLogoIcon` / `ChatCircleIcon` source-map identifier sequence.

For the initially empty remote only: first push main, observe CI contexts, then
apply `rebuild/main-ruleset.json`. All later changes use PRs and squash merges.
Enable native secret scanning and push protection, squash-only merges, automatic
branch deletion, and the production Environment's required reviewer.

## Release configuration

Use the same GitHub configuration layers and names as vxtpl:

- Organization: ALIYUN_ACR_USERNAME/PASSWORD, TAILSCALE_OAUTH_CLIENT_ID/SECRET;
  variables ALIYUN_ACR_REGISTRY/NAMESPACE and TAILSCALE_OAUTH_CLIENT_TAG.
- Production Environment: DEPLOY_HOST (vx-worker-02), DEPLOY_USER, DEPLOY_PORT,
  DEPLOY_SSH_KEY, optional DEPLOY_SSH_KEY_PASSPHRASE, DEPLOY_KNOWN_HOSTS.
- Production variables: STACK_ROOT (/srv/md0/cospace), PROJECT_NAME (cospace).
- DEPLOYMENT_READY must remain false until the existing data/secret migration,
  registry port assignment and platform edge acceptance have been completed.

No application secrets are copied from another product. No secrets are copied
from the old host into GitHub or source. Known hosts must be pinned; empty
known_hosts fails rather than trusting a first connection.

Only a vX.Y.Z tag pointing to main with all five successful checks can release.
Reusable build.yml builds from that SHA, publishes cospace-app to GHCR with an
ACR fallback, and records Git revision in OCI labels. Deployment requires the
production reviewer. The host checks worker02 and requires existing state; it
does not seed, replace, or migrate business data as a side effect of deployment.
The image is resolved to a digest before container startup. No tag is pushed as
part of the initial source upload.

## Existing-repository gaps

The existing Chinese source and unnumbered historical docs predate this import.
This workflow task does not claim that those have been converted to the full
vxtpl docs taxonomy or ASCII rule. That cleanup remains a separately visible
governance gap; the new deployment documents follow the numbered taxonomy.
The previous P27 worker01 deployment is an incident record, not a valid release
path. Follow `10-worker02-correction.md` before planning its migration.
