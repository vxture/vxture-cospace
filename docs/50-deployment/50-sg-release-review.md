# SG3–SG5 release review

Review date: 2026-11-18 (Asia/Shanghai).

## Release scope

The release includes the merged SG0–SG5 implementation increments since
production v0.7.55: IFC design declarations and meshes, authorized read-only
queries and offline packages, independent ontology proposals, observation
storage/replay and integrity checks, controlled backup compatibility, and fixed
review snapshots with region queries and input-gap reports.

These are candidate-description and consumption capabilities. No sample input,
local dataset, synthetic observation database, credential, or local evidence is
deployed. No automatic business-data migration or adoption occurs. SG3–SG5 still
require factual/production acceptance; the release does not certify alignment,
physical connections, manufacturer reports or robot traversability. Offline-only
review utilities remain offline-only; deployment does not create a new UI entry
for each utility. Existing authorized IFC workbench entry points are retained.

## Temporary build dependency exception

OSV GHSA-fc5q-39xc-vjpf (CVE-2026-112366) reports exponential regular-expression
backtracking when picomatch processes attacker-controlled repeated extglobs.
The reviewed advisory was updated immediately after PR #140 passed its audit.
Both npm lockfiles contain picomatch 4.0.7; the npm registry still reports 4.0.7
as latest, and the advisory lists no fixed version at review time.

The affected paths are Vite/tinyglobby/fdir in the workbench and independent globe
example build toolchains. `pnpm --dir <project> why picomatch --prod` reports no
production dependency in either project. The final Docker stage is Python,
copies only compiled frontend assets from the Node builder, and copies neither
node_modules nor the Node toolchain. Public requests do not run Vite or supply
glob expressions to these build tools. Builds still execute the vulnerable tool;
only trusted, reviewed repository patterns may be supplied. This is exposure
assessment, not a claim that the library vulnerability is fixed.

`.osv-scanner.toml` ignores only this advisory until 2026-11-25T00:00:00Z, retaining
all other vulnerability findings and lockfile checks. The exception must be
removed when a fixed upstream release is available. Before expiry, reassess the
dependency paths, builder/runtime boundary and any new glob inputs; do not
automatically extend the date. A change introducing public/user glob inputs or
runtime picomatch invalidates this assessment immediately. No unreviewed upstream
patch or new dependency version is substituted.

## Sonar status

Main-branch Sonar has a pre-existing failing security rating, also present on
production v0.7.55 and the parent of PR #140. Its current new-code-period report
includes seven file-path/filesystem findings in preview jobs, IFC file helpers
and the storage inventory. These remain open; this release does not dismiss,
suppress, reclassify or change their quality gate. Main-branch Sonar must not be
reported as green. The release PR is checked separately for newly introduced
findings. The five repository-required checks remain quality-gate, build,
test-coverage, audit and gitleaks; none is bypassed.

## Deployment and acceptance

Use the checked main commit and a new immutable release tag. GitHub builds the
production image, then production Environment review gates deployment to
vx-worker-02 under /srv/md0/cospace. Do not upload local source or alter protected
environment rules. Verify the workflow result, running image revision/version,
health, public authentication boundaries and static assets after deployment.
Authenticated IFC features require configured authorized scene bindings; lack of
production sample data must not be represented as successful factual acceptance.
