#!/usr/bin/env bash
set -euo pipefail
python scripts/guardrails/check_deploy_target.py
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]
port="${DEPLOY_PORT:-22}"
[[ "$port" =~ ^[0-9]+$ ]]
[[ "$IMAGE_TAG" =~ ^sha-[a-f0-9]{7,40}$ ]]
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]
remote="$DEPLOY_USER@$DEPLOY_HOST"
ssh_opts=(-i ~/.ssh/deploy_key -p "$port" -o StrictHostKeyChecking=yes -o ConnectTimeout=30)
# Validate the physical host and existing state before creating any directories.
ssh "${ssh_opts[@]}" "$remote" "test \"\$(hostname -s)\" = vx-worker-02 && test \"\$(realpath /srv/md0/cospace)\" = /srv/md0/cospace && test ! -L /srv/md0/cospace/deploy && test -f /srv/md0/cospace/etc/.env && test -d /srv/md0/cospace/data/business && mkdir -p /srv/md0/cospace/deploy"
rsync -az --delete --exclude=VERSION --exclude=IMAGE_ID \
  -e "ssh -i $HOME/.ssh/deploy_key -p $port -o StrictHostKeyChecking=yes -o ConnectTimeout=30" \
  deploy/ "$remote:/srv/md0/cospace/deploy/"
# Unique remote helper per run. Secrets travel on SSH stdin, never in argv.
helper="/tmp/cospace-deploy-$GITHUB_RUN_ID.sh"
cat > "$RUNNER_TEMP/cospace-deploy.sh" <<'REMOTE'
set -euo pipefail
test "$(hostname -s)" = vx-worker-02
umask 077
export DOCKER_CONFIG
DOCKER_CONFIG="$(mktemp -d /tmp/cospace-registry.XXXXXXXX)"
cleanup() { rm -rf -- "$DOCKER_CONFIG"; rm -f -- "$0"; }
trap cleanup EXIT
login_registry() {
  local registry="$1" username="$2" password="$3"
  for attempt in 1 2 3; do
    if printf '%s' "$password" | docker login "$registry" -u "$username" --password-stdin; then return 0; fi
    sleep 2
  done
  echo "Registry authentication unavailable; image pull will try the other registry" >&2
  return 0
}
# A fallback registry outage must not block a working primary registry. Pulls
# still fail closed if neither registry can supply the requested revision.
login_registry ghcr.io "$GHCR_USERNAME" "$GHCR_TOKEN"
login_registry "$ACR_REGISTRY" "$ACR_USERNAME" "$ACR_PASSWORD"
if [[ -n "${COSPACE_AMAP_WEB_KEY:-}${COSPACE_AMAP_SECURITY_JS_CODE:-}" ]]; then
  [[ "$COSPACE_AMAP_WEB_KEY" =~ ^[a-fA-F0-9]{32}$ ]]
  [[ "$COSPACE_AMAP_SECURITY_JS_CODE" =~ ^[a-fA-F0-9]{32}$ ]]
  test ! -L /srv/md0/cospace/etc
  test ! -L /srv/md0/cospace/etc/amap.env
  amap_config="$(mktemp /srv/md0/cospace/etc/.amap.XXXXXXXX)"
  printf 'COSPACE_AMAP_WEB_KEY=%s\nCOSPACE_AMAP_SECURITY_JS_CODE=%s\n' "$COSPACE_AMAP_WEB_KEY" "$COSPACE_AMAP_SECURITY_JS_CODE" > "$amap_config"
  chmod 600 "$amap_config"
  mv -f -- "$amap_config" /srv/md0/cospace/etc/amap.env
fi
bash /srv/md0/cospace/deploy/deploy.sh
REMOTE
scp -i ~/.ssh/deploy_key -P "$port" -o StrictHostKeyChecking=yes "$RUNNER_TEMP/cospace-deploy.sh" "$remote:$helper"
cmd=''
for name in STACK_ROOT PROJECT_NAME IMAGE_TAG GHCR_NAMESPACE GHCR_USERNAME GHCR_TOKEN ACR_REGISTRY ACR_NAMESPACE ACR_USERNAME ACR_PASSWORD GITHUB_SHA COSPACE_AMAP_WEB_KEY COSPACE_AMAP_SECURITY_JS_CODE; do
  printf -v pair '%s=%q ' "$name" "${!name}"
  cmd+="$pair"
done
printf '%s bash %q\n' "$cmd" "$helper" | ssh "${ssh_opts[@]}" "$remote" bash -s
