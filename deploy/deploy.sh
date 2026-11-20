#!/usr/bin/env bash
# Called only by the GitHub production workflow, after Environment approval.
set -euo pipefail
test "$(hostname -s)" = vx-worker-02
test "${STACK_ROOT:-}" = /srv/md0/cospace
test "${PROJECT_NAME:-}" = cospace
test "${IMAGE_TAG:-}" != latest
[[ "$IMAGE_TAG" =~ ^sha-[a-f0-9]{7,40}$ ]]
cd "$STACK_ROOT/deploy"
test -f "$STACK_ROOT/etc/.env"
# Inspect UID 10001's private directories without weakening their permissions.
sudo -n true
for dir in data/business data/state etc/secrets; do sudo -n test -d "$STACK_ROOT/$dir"; done
for key in client-secret session-key webhook-secret; do
  sudo -n test -f "$STACK_ROOT/etc/secrets/$key"
done
sudo -n test -f "$STACK_ROOT/data/business/setup/workspace-scenes.json"
sudo -n test -d "$STACK_ROOT/data/business/runtime"
primary="ghcr.io/$GHCR_NAMESPACE/cospace-app:$IMAGE_TAG"
if ! timeout --kill-after=10s 180s docker pull "$primary"; then
  fallback="$ACR_REGISTRY/$ACR_NAMESPACE/cospace-app:$IMAGE_TAG"
  timeout --kill-after=10s 300s docker pull "$fallback"
  docker tag "$fallback" "$primary"
fi
revision="$(docker image inspect "$primary" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
test "$revision" = "$GITHUB_SHA"
# Resolve to a digest: container startup never depends on a mutable release tag.
COSPACE_IMAGE="$(docker image inspect "$primary" --format '{{index .RepoDigests 0}}')"
test -n "$COSPACE_IMAGE"
export COSPACE_IMAGE STACK_ROOT PROJECT_NAME
# Preserve each existing ontology database and previous service images before replacement.
# Failure leaves current containers running; backups remain private on worker02.
sudo -n timeout --kill-after=10s 180s python3 "$STACK_ROOT/deploy/linux/backup_ontology.py"
compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$STACK_ROOT/etc/.env" -f linux/compose.yml)
# Rendered config is piped to validation; never echo secret runtime values.
"${compose[@]}" config --format json | python3 -c '
import ipaddress,json,sys
c=json.load(sys.stdin);s=c["services"]["workbench"]
for p in s["ports"]:
    assert ipaddress.ip_address(p["host_ip"]) in ipaddress.ip_network("100.64.0.0/10"), "tailnet bind required"
assert s["container_name"] == "cospace-app"
for name in ("ifc-parser","ifc-worker"):
    worker=c["services"][name]
    assert worker["image"]==s["image"] and worker["network_mode"]=="none" and not worker.get("ports")
assert {v["target"] for v in c["services"]["ifc-parser"]["volumes"]}=={"/ifc-ipc"}
'
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 90 ifc-parser ifc-worker
"${compose[@]}" up -d --no-build --no-deps workbench
for attempt in $(seq 1 30); do
  if docker exec cospace-app python deploy/linux/healthcheck.py >/dev/null 2>&1 &&
     docker exec cospace-app python -c 'from packages.infrastructure.ifc_parser_channel import available; raise SystemExit(0 if available() else 1)'; then
    docker inspect --format '{{.Image}}' cospace-app > "$STACK_ROOT/deploy/IMAGE_ID"
    printf '%s\n' "$GITHUB_SHA" > "$STACK_ROOT/deploy/VERSION"
    echo 'CoSpace worker02 health accepted'
    exit 0
  fi
  sleep 2
done
echo 'CoSpace worker02 health failed; previous images and data retained' >&2
exit 1
