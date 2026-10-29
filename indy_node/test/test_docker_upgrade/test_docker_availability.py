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


def test_docker_available_succeeds(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='Server Version: 24.0\n'))
    upgrader._check_docker_available()


def test_docker_available_fails(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=1, stderr='Cannot connect to Docker daemon'))
    with pytest.raises(RuntimeError, match='Docker is not available'):
        upgrader._check_docker_available()


def test_docker_available_timeout(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='docker info', timeout=10)
    monkeypatch.setattr(subprocess, 'run', _timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        upgrader._check_docker_available()
