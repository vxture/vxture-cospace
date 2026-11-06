# CoSpace working agreement

- Reference product template: `vx-agent-vxtpl`.
- worker01 runs the platform management services. CoSpace workloads belong on
  worker02 (`vx-worker-02`), with production stack root `/srv/md0/cospace`.
- Read `docs/50-deployment/10-worker02-correction.md` before deployment work.
- Never upload local source bundles directly to a server. Source must pass the
  GitHub checks; release tags build images from that commit, then deployment
  waits for the production Environment's reviewer.
- Main pushes do not deploy. Use feature branches and PRs after the initial
  empty-repository bootstrap. Squash merge only.
- Required checks: quality-gate, build, test-coverage, audit, gitleaks.
- Credentials, runtime data, local evidence and authentication state stay out
  of Git. Scan the exact staged tree and bundled archives before pushing.
- The platform owns subscriptions and commercial entitlements. Product code
  implements business functions and scene authorization, not commercial limits.
