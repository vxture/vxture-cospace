# CoSpace deployment target correction

Date: 2026-11-06. Authority: owner instruction and
`vx-agent-vxtpl/CLAUDE.md`, `vx-agent-vxtpl/.github/workflows/deploy.yml`,
`vx-agent-vxtpl/docs/50-deployment/20-github-bootstrap-checklist.md`.

## Host responsibilities

- worker01 runs the central platform management services. It is not a CoSpace
  application deployment target.
- worker02 (`vx-worker-02`) runs product workloads. CoSpace production belongs
  under `/srv/md0/cospace`, following vxtpl's `/srv/md0/<product>` layout.
- Authentication remains at `https://accounts.vxture.com`. Product identity,
  subscriptions and commercial entitlements remain platform responsibilities.
- A domain's DNS record identifies its ingress, not its application host.
  Ingress configuration must follow the platform's edge registration mechanism.

## Historical deployment: incorrect target

The earlier P27 deployment record describes a direct local bundle deployment to
worker01 under `/srv/cospace`, container `cospace-workbench`. That operation
bypassed GitHub and used the wrong application host. The P27 records remain as
historical evidence; they are not instructions for future releases.

This correction does not claim the old container has been stopped, the data has
been migrated, or the edge upstream has been changed. Those server operations
must be recorded separately after they actually occur.

## Required release path

1. Scan the exact candidate source and archives for credentials before upload.
2. Bootstrap the empty GitHub main branch, then require PRs and the five checks:
   `quality-gate`, `build`, `test-coverage`, `audit`, `gitleaks`.
3. Build release images from a recorded Git commit using reusable `build.yml`.
4. Release tags select the production GitHub Environment with a required reviewer.
5. Deploy over the tailnet to worker02 only. Reject a different target or stack
   root. Main branch pushes must not deploy.
6. Plan and verify the existing state/secret migration and platform edge update
   before enabling the first worker02 release. Do not overwrite existing data.

Shared registry and tailnet credentials remain organization secrets, as in vxtpl.
Host credentials belong to the production Environment. Application secret values
remain outside source and images. Ports must come from the organization port
registry; this document does not allocate or copy a port table.
