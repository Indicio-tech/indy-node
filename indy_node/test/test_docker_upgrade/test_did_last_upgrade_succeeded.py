import os
import tempfile
from datetime import datetime

from indy_node.server.upgrade_log import UpgradeLogData, UpgradeLog
from indy_node.server.upgrader import Upgrader


def _make_upgrader(tconf, monkeypatch):
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId=None, nodeName=None, dataDir=data_dir, config=tconf, ledger=None)
    return upgrader


def test_with_image_name_delegates(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)
    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')

    upgrader._actionLog.append_started(ev_data)
    monkeypatch.setattr(upgrader, '_did_docker_upgrade_succeed', lambda ev: True)

    assert upgrader.didLastExecutedUpgradeSucceeded is True


def test_without_image_name_returns_true(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)
    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY)

    upgrader._actionLog.append_started(ev_data)

    assert upgrader.didLastExecutedUpgradeSucceeded is True


def test_no_last_event_returns_false(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf, monkeypatch)

    assert upgrader.didLastExecutedUpgradeSucceeded is False
