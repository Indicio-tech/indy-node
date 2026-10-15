# Testing indy-node / indy-plenum v1.15.0-rc1

This is a release candidate for the Ubuntu 22.04 / Docker-native node work:
a real, production-image `.deb` → Docker migration path (not mocked), a
RocksDB bug fix in plenum, and hardening of the `POOL_UPGRADE`
image-upgrade/rollback path. It is **not yet an official release** — test it
against a non-critical node first, not a validator whose quorum participation
matters in production.

## What's in it

| Image | Tag | Carries |
|---|---|---|
| `ghcr.io/indicio-tech/indy-plenum` | `v1.15.0-rc1` | RocksDB `do_ops_in_batch` fix (was a silent no-op — writes were never actually being batched to disk) |
| `ghcr.io/indicio-tech/indy-node` | `v1.15.0-rc1` | The above, plus real-docker-execution upgrade/rollback tests, downgrade rejection, restarter/upgrader fixes |

Only `indy-node` is what you actually run — it has plenum built in. The
`indy-plenum` image/tag exists for reference and for anyone rebuilding
`indy-node` themselves; you don't need to pull it separately.

Branches: [`feature/docker_upgrades`](https://github.com/Indicio-tech/indy-plenum/tree/feature/docker_upgrades)
(indy-plenum), [`feature/docker`](https://github.com/Indicio-tech/indy-node/tree/feature/docker)
(indy-node).

## Access

These images are **internal** to the Indicio-tech GitHub org — you need org
membership and a GitHub personal access token with `read:packages` scope:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u <your-github-username> --password-stdin
docker pull ghcr.io/indicio-tech/indy-node:v1.15.0-rc1
```

## Migrating an existing node

Follow [`MIGRATION_GUIDE.md`](../MIGRATION_GUIDE.md) step by step — it
already reflects the design this RC implements (uid 1000 forced
unconditionally, named Docker volumes populated by copy, automatic
image-upgrade rollback). The **only change for this RC**: everywhere the
guide says

```yaml
image: ghcr.io/hyperledger/indy-node:latest
```

use

```yaml
image: ghcr.io/indicio-tech/indy-node:v1.15.0-rc1
```

instead. Pin the exact tag, not `:latest` — you want to know precisely
which build you tested.

Before you start, two things the guide doesn't repeat every time but are
worth restating for an RC specifically:

1. **Back up first.** `sudo tar czf /root/indy-node-backup-$(date +%s).tar.gz
   /var/lib/indy /etc/indy /var/log/indy` before Step 2's copy. The copy
   step is non-destructive (`cp -a`, not `mv`), but an extra independent
   backup costs nothing and this is pre-release software.
2. **Check with whoever's watching pool health before you stop the node.**
   Migration takes the node offline for the swap; confirm the rest of the
   pool can hold quorum without it for that window before you start (same
   assertion `test-network`'s `quorum-test`/`migrate.sh` make automatically
   in the test bed — on a real pool, that's a judgment call, not a script).

## Rollback

Two layers, both already in `MIGRATION_GUIDE.md`:
- **Manual**, if the Docker container never comes up healthy at all:
  reinstall the `.deb` and restart the old systemd service — your original
  `/var/lib/indy` and `/etc/indy` are untouched (Step 2 copies, never moves).
- **Automatic**, once you're running Docker and use `POOL_UPGRADE` with the
  `image` field for a *later* upgrade: the node tags the current image as
  `indy-node-rollback` before pulling the new one, and reverts to it
  automatically if the new container doesn't reach a healthy state within
  the timeout. This is the mechanism this RC's "restarter/upgrader fixes"
  and "downgrade rejection" line items are about — see the commit history on
  `feature/docker` for specifics (`indy_node/server/restarter.py`,
  `indy_node/server/upgrader.py`).

## Reporting back

Whatever you find — clean migration, a snag in the guide, a healthcheck
flake, timing that felt too tight — goes back as a comment/note so it can
feed into cutting the actual `v1.15.0` release. If something looks like a
genuine bug rather than a docs gap, flag which step and what you saw rather
than just "didn't work" — the migration has several distinct phases
(backup, copy+chown, compose up, systemd handoff) and knowing which one
failed narrows it down a lot.
