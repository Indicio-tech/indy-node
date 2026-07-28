import subprocess
import tempfile

from indy_node.server.upgrader import _ROLLBACK_TAG, Upgrader


def _make_upgrader(tconf):
    data_dir = tempfile.mkdtemp()
    return Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)


def _make_result(returncode=0, stdout='', stderr=''):
    r = type('', (), {})()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_save_current_image_success(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    call_log = []

    def _run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get('args', [])
        call_log.append(cmd)
        if 'inspect' in str(cmd):
            return _make_result(returncode=0, stdout='ghcr.io/hyperledger/indy-node:latest\nsha256:abc123...\n')
        if 'tag' in str(cmd):
            return _make_result(returncode=0)
        return _make_result(returncode=1)

    monkeypatch.setattr(subprocess, 'run', _run)
    result = upgrader._save_current_image_for_rollback()

    assert result == 'ghcr.io/hyperledger/indy-node:latest'
    assert any('inspect' in str(c) for c in call_log)
    assert any('tag' in str(c) and _ROLLBACK_TAG in str(c) for c in call_log)


def test_save_current_image_no_container(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=1, stderr='No such container'))
    result = upgrader._save_current_image_for_rollback()
    assert result is None


def test_save_current_image_tag_fails(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    call_count = [0]

    def _run(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_result(returncode=0, stdout='img:latest\nsha256:def456...\n')
        return _make_result(returncode=1, stderr='tag error')

    monkeypatch.setattr(subprocess, 'run', _run)
    result = upgrader._save_current_image_for_rollback()
    assert result is None


def test_rollback_success(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    call_log = []

    def _run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get('args', [])
        call_log.append(cmd)
        return _make_result(returncode=0)

    monkeypatch.setattr(subprocess, 'run', _run)
    result = upgrader._rollback_upgrade('/opt/indy-node', 'ghcr.io/hyperledger/indy-node:latest')

    assert result is True
    assert any('tag' in str(c) and _ROLLBACK_TAG in str(c) for c in call_log)
    assert any('compose' in str(c) and 'up' in str(c) for c in call_log)


def test_rollback_tag_fails(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    call_count = [0]

    def _run(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_result(returncode=1, stderr='tag error')
        return _make_result(returncode=0)

    monkeypatch.setattr(subprocess, 'run', _run)
    result = upgrader._rollback_upgrade('/opt/indy-node', 'img:latest')

    assert result is True


def test_rollback_up_fails(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    call_count = [0]

    def _run(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_result(returncode=0)
        return _make_result(returncode=1, stderr='compose up failed')

    monkeypatch.setattr(subprocess, 'run', _run)
    result = upgrader._rollback_upgrade('/opt/indy-node', 'img:latest')

    assert result is False


def test_rollback_exception(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    def _raise(*args, **kwargs):
        raise RuntimeError('docker error')
    monkeypatch.setattr(subprocess, 'run', _raise)
    result = upgrader._rollback_upgrade('/opt/indy-node', 'img:latest')
    assert result is False


def test_send_upgrade_request_rollback_on_health_fail(looper, tconf, monkeypatch):
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)
    monkeypatch.setattr(upgrader, '_schedule', lambda cb, delay: None)
    monkeypatch.setattr(upgrader, '_unscheduleAction', lambda: None)
    monkeypatch.setattr(upgrader, 'scheduledAction', None)
    monkeypatch.setattr(upgrader, '_check_docker_available', lambda: None)
    monkeypatch.setattr(upgrader, '_save_current_image_for_rollback', lambda: 'img:latest')
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0))

    rollback_called = []
    monkeypatch.setattr(upgrader, '_rollback_upgrade', lambda compose_dir, current_ref: rollback_called.append((compose_dir, current_ref)))

    def _raise_health(*args, **kwargs):
        raise RuntimeError('container not running')
    monkeypatch.setattr(upgrader, '_wait_for_container_healthy', _raise_health)

    action_failed_called = []
    monkeypatch.setattr(upgrader, '_action_failed', lambda ev_data, reason=None, external_reason=False: action_failed_called.append(reason))

    from datetime import datetime
    from indy_node.server.upgrade_log import UpgradeLogData
    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='new-img:latest')
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(rollback_called) == 1
    assert rollback_called[0] == ('/opt/indy-node', 'img:latest')
    assert len(action_failed_called) == 1
