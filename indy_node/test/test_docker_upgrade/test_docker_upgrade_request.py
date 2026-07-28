import subprocess
import tempfile
from datetime import datetime

from indy_node.server.upgrade_log import UpgradeLogData
from indy_node.server.upgrader import Upgrader

whitelist = ['failed upgrade', 'No Docker image specified']


def _make_upgrader(tconf, monkeypatch):
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)
    monkeypatch.setattr(upgrader, '_schedule', lambda cb, delay: None)
    monkeypatch.setattr(upgrader, '_action_failed', lambda ev_data, reason=None, external_reason=False: None)
    monkeypatch.setattr(upgrader, '_unscheduleAction', lambda: None)
    monkeypatch.setattr(upgrader, 'scheduledAction', None)
    monkeypatch.setattr(upgrader, '_check_docker_available', lambda: None)
    monkeypatch.setattr(upgrader, '_save_current_image_for_rollback', lambda: None)
    monkeypatch.setattr(upgrader, '_wait_for_container_healthy', lambda timeout=None: True)
    return upgrader


def _make_result(returncode=0, stdout='', stderr=''):
    r = type('', (), {})()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_docker_upgrade_pull_fails(looper, tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=1, stderr='pull error'))

    action_failed_called = []
    monkeypatch.setattr(upgrader, '_action_failed', lambda ev_data, reason=None, external_reason=False: action_failed_called.append(reason))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(action_failed_called) == 1
    assert 'pull failed' in action_failed_called[0]


def test_docker_upgrade_up_fails(looper, tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)

    call_count = [0]
    def _run(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_result(returncode=0)
        return _make_result(returncode=1, stderr='up error')
    monkeypatch.setattr(subprocess, 'run', _run)

    action_failed_called = []
    monkeypatch.setattr(upgrader, '_action_failed', lambda ev_data, reason=None, external_reason=False: action_failed_called.append(reason))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(action_failed_called) == 1
    assert 'up failed' in action_failed_called[0]


def test_docker_upgrade_success(looper, tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0))

    times_up_called = []
    monkeypatch.setattr(upgrader, '_schedule', lambda cb, delay: times_up_called.append((cb, delay)))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(times_up_called) == 1


def test_docker_upgrade_no_image(looper, tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)

    action_failed_called = []
    monkeypatch.setattr(upgrader, '_action_failed', lambda ev_data, reason=None, external_reason=False: action_failed_called.append(reason))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY)
    looper.run(upgrader._sendUpgradeRequest(ev_data, 10))

    assert len(action_failed_called) == 1
    assert 'no Docker image specified' in action_failed_called[0]
