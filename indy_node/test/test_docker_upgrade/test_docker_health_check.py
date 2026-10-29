import subprocess
import tempfile

import pytest

from indy_node.server.upgrader import Upgrader


def _make_upgrader(tconf):
    data_dir = tempfile.mkdtemp()
    return Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)


def _make_result(returncode=0, stdout='', stderr=''):
    r = type('', (), {})()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def _make_sequential_run(results):
    call_count = [0]
    def _run(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(results):
            return results[idx]
        return _make_result(returncode=1, stderr='unexpected call')
    return _run


def test_container_becomes_running_immediately(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='running\n'))
    assert upgrader._wait_for_container_healthy(timeout=10) is True


def test_container_becomes_running_after_restarting(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', _make_sequential_run([
        _make_result(returncode=0, stdout='restarting\n'),
        _make_result(returncode=0, stdout='restarting\n'),
        _make_result(returncode=0, stdout='running\n'),
    ]))
    assert upgrader._wait_for_container_healthy(timeout=10) is True


def test_container_stays_created_then_running(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', _make_sequential_run([
        _make_result(returncode=0, stdout='created\n'),
        _make_result(returncode=0, stdout='created\n'),
        _make_result(returncode=0, stdout='running\n'),
    ]))
    assert upgrader._wait_for_container_healthy(timeout=10) is True


def test_container_in_unexpected_state(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='exited\n'))
    with pytest.raises(RuntimeError, match='unexpected state'):
        upgrader._wait_for_container_healthy(timeout=10)


def test_container_never_becomes_running(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='restarting\n'))
    with pytest.raises(RuntimeError, match='did not reach running state'):
        upgrader._wait_for_container_healthy(timeout=3)


def test_inspect_fails_during_poll(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=1, stderr='No such container'))
    with pytest.raises(RuntimeError, match='did not reach running state'):
        upgrader._wait_for_container_healthy(timeout=3)


def test_inspect_raises_exception(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    def _raise(*args, **kwargs):
        raise RuntimeError('docker daemon unreachable')
    monkeypatch.setattr(subprocess, 'run', _raise)
    with pytest.raises(RuntimeError, match='did not reach running state'):
        upgrader._wait_for_container_healthy(timeout=3)
