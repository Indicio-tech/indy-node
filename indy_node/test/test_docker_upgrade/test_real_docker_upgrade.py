"""
Exercises Upgrader against a *real* docker/docker-compose daemon, instead of
mocking subprocess.run like the rest of test_docker_upgrade/. Requires a
docker socket mounted into the test container, e.g.:

    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
        --entrypoint="" indy-node-test-docker-upgrade:local \
        python3 -m pytest -l -vv indy_node/test/test_docker_upgrade/test_real_docker_upgrade.py

See indy-node/CLAUDE.md for how to build that image.

Scope: this proves Upgrader's own docker/compose orchestration (check
availability -> save rollback ref -> pull -> up --force-recreate -> wait
healthy -> rollback-on-health-failure) is correct when given a working
compose project. It does NOT exercise who writes the new image tag into the
compose file in production (that mechanism doesn't exist yet - see NEXT.md),
and it says nothing about whether the production node container should get a
mounted socket or a sidecar - these tests just mount the socket directly
because that's sufficient to validate the orchestration logic itself.

The "node" being upgraded is a trivial alpine placeholder, not the real
indy-node image - these tests only ever check `docker inspect`'s container
state/image, never anything node-protocol-specific.
"""
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

import pytest

from indy_node.server.upgrade_log import UpgradeLogData
from indy_node.server.upgrader import Upgrader

CONTAINER_NAME = 'indy-node'  # matches UPGRADE_ENTRY / compose service default


def _run(*args, **kwargs):
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    kwargs.setdefault('timeout', 60)
    return subprocess.run(list(args), **kwargs)


def _docker_available():
    try:
        return _run('docker', 'info').returncode == 0
    except Exception:
        return False


requires_real_docker = pytest.mark.skipif(
    not _docker_available(),
    reason='no docker socket available (mount /var/run/docker.sock to run this)')


def _build_fake_image(tag, dockerfile_body):
    build_dir = tempfile.mkdtemp(prefix='fake-node-build-')
    try:
        with open(os.path.join(build_dir, 'Dockerfile'), 'w') as f:
            f.write(dockerfile_body)
        result = _run('docker', 'build', '-t', tag, build_dir, timeout=120)
        assert result.returncode == 0, 'failed to build {}: {}'.format(tag, result.stderr)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


@pytest.fixture(scope='module')
def fake_node_images():
    images = {
        'v1': 'fake-node-test:v1',
        'v2': 'fake-node-test:v2',
        'crash': 'fake-node-test:crash',
    }
    _build_fake_image(images['v1'], 'FROM alpine:3.19\nCMD ["sleep", "3600"]\n')
    _build_fake_image(images['v2'], 'FROM alpine:3.19\nLABEL fake_node_version=2\nCMD ["sleep", "3600"]\n')
    _build_fake_image(images['crash'], 'FROM alpine:3.19\nCMD ["sh", "-c", "exit 1"]\n')
    yield images
    for tag in images.values():
        _run('docker', 'rmi', '-f', tag)


@pytest.fixture
def compose_project(fake_node_images):
    project_dir = tempfile.mkdtemp(prefix='fake-node-compose-')
    compose_path = os.path.join(project_dir, 'docker-compose.yaml')

    def write_service_image(tag):
        with open(compose_path, 'w') as f:
            f.write(
                'services:\n'
                '  indy-node:\n'
                '    image: {}\n'
                '    container_name: {}\n'
                '    pull_policy: never\n'
                '    restart: "no"\n'.format(tag, CONTAINER_NAME)
            )

    write_service_image(fake_node_images['v1'])
    _run('docker', 'compose', '--project-directory', project_dir, 'up', '-d', 'indy-node', timeout=30)

    yield project_dir, write_service_image

    _run('docker', 'compose', '--project-directory', project_dir, 'down', '-t', '1', timeout=30)
    _run('docker', 'rmi', '-f', 'indy-node-rollback')
    shutil.rmtree(project_dir, ignore_errors=True)


def _make_upgrader(tconf, compose_dir):
    tconf = tconf
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)
    upgrader._schedule = lambda cb, delay: None
    upgrader._unscheduleAction = lambda: None
    upgrader.scheduledAction = None
    failed = []
    upgrader._action_failed = lambda ev_data, reason=None, external_reason=False: failed.append(reason)
    upgrader._failed_calls = failed
    return upgrader


def _running_image(container_name=CONTAINER_NAME):
    result = _run('docker', 'inspect', '--format', '{{.Config.Image}}', container_name)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _container_state(container_name=CONTAINER_NAME):
    result = _run('docker', 'inspect', '--format', '{{.State.Status}}', container_name)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


@requires_real_docker
def test_real_upgrade_happy_path(looper, tconf, monkeypatch, fake_node_images, compose_project):
    """Upgrader itself must rewrite the compose file's image to
    ev_data.image_name before pull/up - docker compose resolves the image
    strictly from the compose file, so without that write the "upgrade"
    would silently redeploy the still-running old image."""
    project_dir, _ = compose_project
    monkeypatch.setattr(tconf, 'COMPOSE_PROJECT_DIR', project_dir)
    assert _running_image() == fake_node_images['v1']

    upgrader = _make_upgrader(tconf, project_dir)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id',
                              tconf.UPGRADE_ENTRY, image_name=fake_node_images['v2'])
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert upgrader._failed_calls == []
    assert _running_image() == fake_node_images['v2']
    assert _container_state() == 'running'


@requires_real_docker
def test_real_rollback_after_health_failure(looper, tconf, monkeypatch, fake_node_images, compose_project):
    """New image's container exits immediately instead of reaching
    'running' - _wait_for_container_healthy should time out and trigger a
    real rollback back to the previously-running image."""
    import indy_node.server.upgrader as upgrader_module
    monkeypatch.setattr(upgrader_module, '_DOCKER_HEALTH_TIMEOUT', 6)
    monkeypatch.setattr(upgrader_module, '_DOCKER_HEALTH_POLL_INTERVAL', 0.5)

    project_dir, _ = compose_project
    monkeypatch.setattr(tconf, 'COMPOSE_PROJECT_DIR', project_dir)
    assert _running_image() == fake_node_images['v1']

    upgrader = _make_upgrader(tconf, project_dir)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id',
                              tconf.UPGRADE_ENTRY, image_name=fake_node_images['crash'])
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(upgrader._failed_calls) == 1
    assert 'running state' in upgrader._failed_calls[0]
    # rollback re-ran `up` against the original (now re-tagged) image ref
    assert _running_image() == fake_node_images['v1']
    assert _container_state() == 'running'


@requires_real_docker
def test_real_pull_failure_leaves_running_container_untouched(looper, tconf, monkeypatch, compose_project):
    """A nonexistent/unreachable image reference should fail at `docker
    compose pull` - before anything touches the running container. Rollback
    is not expected here (nothing was ever recreated), just that the
    existing container survives untouched and the action is marked failed.
    """
    project_dir, _ = compose_project
    monkeypatch.setattr(tconf, 'COMPOSE_PROJECT_DIR', project_dir)

    # pull_policy: never only works when the image already exists; force a
    # real pull attempt here against a tag that can't resolve.
    compose_path = os.path.join(project_dir, 'docker-compose.yaml')
    with open(compose_path, 'w') as f:
        f.write(
            'services:\n'
            '  indy-node:\n'
            '    image: indy-node-test-nonexistent-image:does-not-exist\n'
            '    container_name: {}\n'
            '    restart: "no"\n'.format(CONTAINER_NAME)
        )

    upgrader = _make_upgrader(tconf, project_dir)
    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id',
                              tconf.UPGRADE_ENTRY, image_name='indy-node-test-nonexistent-image:does-not-exist')
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(upgrader._failed_calls) == 1
    assert 'pull failed' in upgrader._failed_calls[0]
    assert _container_state() == 'running'
