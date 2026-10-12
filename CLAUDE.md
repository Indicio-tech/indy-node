# Running tests

Same constraint as indy-plenum: no Python on the host. Tests must run inside
Docker, the same way CI (`.github/workflows/reuseable_test.yaml`) runs them.

## Build the images

indy-node's base image normally installs plenum from PyPI
(`indicio-indy-plenum`), which is **not** what a local indy-plenum checkout
with uncommitted/unreleased changes looks like. To test indy-node against a
local indy-plenum branch instead of the released package:

```
# 1. Build (or reuse) indy-plenum's own base image first
cd ../indy-plenum
docker build -t indy-plenum-base:local -f Dockerfile.base .

# 2. Build an indy-node base image that installs the *local* indy-plenum
#    source (via git archive, so it reflects the committed tree, not stray
#    uncommitted files) instead of the pip-installed release
mkdir -p /tmp/node-base-build/indy-plenum-src
git -C ../indy-plenum archive HEAD | tar -x -C /tmp/node-base-build/indy-plenum-src
cat > /tmp/node-base-build/Dockerfile.base.local <<'EOF'
ARG PLENUM_BASE_IMAGE=indy-plenum-base:local
FROM ${PLENUM_BASE_IMAGE}
COPY indy-plenum-src /tmp/indy-plenum-src
RUN pip3 install --no-deps /tmp/indy-plenum-src && rm -rf /tmp/indy-plenum-src
RUN pip3 install python3-indy timeout-decorator>=0.5.0 distro==1.7.0 \
    pytest-xdist pytest-forked pytest-asyncio attrs pytest
EOF
cd /tmp/node-base-build
docker build -f Dockerfile.base.local --build-arg PLENUM_BASE_IMAGE=indy-plenum-base:local \
  -t indy-node-base:local .

# 3. Build indy-node itself on top (this picks up indy-node's own working
#    tree via `COPY . .` in its Dockerfile, uncommitted changes included)
cd /path/to/indy-node
docker build --build-arg BASE_IMAGE=indy-node-base:local -t indy-node-test:local .
```

If you only need indy-node tested against the **released** plenum package
(no local plenum changes in play), skip step 2 and build indy-node's own
`Dockerfile.base` directly — much faster, no rocksdb/ursa/libindy compile.

Rebuild `indy-node-test:local` after any indy-node code change. Rebuild the
`indy-node-base:local` layer only when the local indy-plenum source changes.

Sanity-check what actually landed in the image before trusting a test run:

```
docker run --rm --entrypoint="" indy-node-test:local python3 -c \
  "import stp_core.loop.looper as l, inspect; print(inspect.getsource(l.Looper.run))"
```

## Run tests

Single file/dir, don't care about cross-module config state:

```
docker run --rm --shm-size=256m --entrypoint="" indy-node-test:local \
  python3 -m pytest -l -vv <path>
```

Whole `indy_node` or `indy_common` package: use `runner.py` (same reasoning
as indy-plenum's CLAUDE.md — a process-global config singleton means each
top-level test module needs its own subprocess). CI splits each module into
11 slices:

```
docker run --rm --shm-size=256m --entrypoint="" indy-node-test:local runner.py \
  --pytest "python3 -m pytest -l -vv" --dir indy_node --output test-result-node.txt \
  --test-only-slice "1/11"
```

`--entrypoint=""` is required — indy-node's production `ENTRYPOINT` is
`/entrypoint.sh`, which expects `NODE_NAME`/`NODE_IP`/etc. and is not a test
entrypoint (this matches `options: --entrypoint=""` in the CI workflow).

Do not attempt to run pytest on the host — native deps are only in the image.

## `test_suspend_node` / "Too many open files" crash

If `indy_node/test/suspension` aborts with `Fatal Python error: Aborted` and
`Too many open files (src/ip_resolver.cpp:542)` (zmq), it is **not** the
RocksDB/shm issue it was previously assumed to be — it reproduces running
completely alone, with no other containers running. Root cause: Docker's
default `nofile` ulimit (1024) gets exhausted by the time `suspension` runs,
because the two modules `runner.py` runs before it in the same slice
(`anon_creds`, then `nym_txn` — 1,860 tests combined) leave enough zmq
sockets/fds around. Fix: raise the limit on every `docker run`:

```
docker run --rm --shm-size=256m --ulimit nofile=65536:65536 --entrypoint="" ...
```

Confirmed this turns slice 1 from "aborts after 1 of 3 modules" into
`1873 passed, 0 failed, 0 errors, 24 skipped`. CI's `reuseable_test.yaml`
does not currently set `--ulimit` on the container `options:` — it should,
or this will intermittently reproduce there too depending on module ordering
and what ran in the same job before `suspension`.

## Running slices in parallel

CI runs all 22 slices (11 × `indy_node`, 11 × `indy_common`) as a parallel
matrix. Locally, don't run them one at a time in a loop — use `xargs -P` (or
background each `docker run` and `wait`) to actually parallelize:

```
for m in indy_node indy_common; do for s in $(seq 1 11); do echo "$m $s"; done; done | \
  xargs -P 4 -I{} sh -c '
    set -- {}
    m=$1; s=$2
    docker run --rm --shm-size=256m --entrypoint="" indy-node-test:local \
      python3 runner.py --pytest "python3 -m pytest -l -vv" --dir "$m" \
      --output "test-result-${m}-${s}.txt" --test-only-slice "${s}/11" --nojunitxml \
      > "node-full-${m}-${s}.log" 2>&1
    echo "done: $m slice $s (exit $?)"
  '
```

Pick concurrency (`-P N`) from what the host actually has, not a guess —
check first:

```
nproc
free -h
```

8 cores / ~20GB free comfortably supports `-P 4`; each slice runs its own
pytest process (single-threaded aside from whatever the tests themselves
spawn), so 4 concurrent containers leaves headroom rather than saturating
every core. Push higher only after watching `docker stats` during a run to
confirm there's room — oversubscribing causes containers to starve each
other and can produce flaky timeouts that look like real test failures.
