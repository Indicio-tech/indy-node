import subprocess
import tempfile
from datetime import datetime

from indy_node.server.upgrade_log import UpgradeLogData
from indy_node.server.upgrader import Upgrader


def _make_upgrader(tconf):
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)
    return upgrader


def _make_result(returncode=0, stdout='', stderr=''):
    r = type('', (), {})()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_matching_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='img:latest\n'))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    assert upgrader._did_docker_upgrade_succeed(ev_data) is True


def test_non_matching_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=0, stdout='other-img:1.0\n'))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    assert upgrader._did_docker_upgrade_succeed(ev_data) is False


def test_inspect_fails(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: _make_result(returncode=1, stderr='No such container'))

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    assert upgrader._did_docker_upgrade_succeed(ev_data) is False


def test_inspect_exception(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    def _raise(*args, **kwargs):
        raise RuntimeError('docker not available')
    monkeypatch.setattr(subprocess, 'run', _raise)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    assert upgrader._did_docker_upgrade_succeed(ev_data) is False
