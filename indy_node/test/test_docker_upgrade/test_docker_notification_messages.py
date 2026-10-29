import tempfile
from datetime import datetime

import dateutil.tz

from indy_node.server.upgrade_log import UpgradeLogData, UpgradeLog
from indy_node.server.upgrader import Upgrader

whitelist = ['failed upgrade']


class FakeNotifier:
    def __init__(self):
        self.scheduled = []
        self.complete = []
        self.fail = []
        self.cancel = []

    def sendMessageUponNodeUpgradeScheduled(self, msg):
        self.scheduled.append(msg)

    def sendMessageUponNodeUpgradeComplete(self, msg):
        self.complete.append(msg)

    def sendMessageUponNodeUpgradeFail(self, msg):
        self.fail.append(msg)

    def sendMessageUponPoolUpgradeCancel(self, msg):
        self.cancel.append(msg)


def _make_upgrader(tconf):
    data_dir = tempfile.mkdtemp()
    upgrader = Upgrader(nodeId='Node1', nodeName='Node1', dataDir=data_dir, config=tconf, ledger=None)
    upgrader._notifier = FakeNotifier()
    return upgrader


def test_schedule_with_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(upgrader._actionLog, 'append_scheduled', lambda ev: None)
    monkeypatch.setattr(upgrader, '_schedule', lambda cb, delay: None)

    when = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())
    ev_data = UpgradeLogData(when, '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    upgrader._scheduleUpgrade(ev_data, 10)

    assert len(upgrader._notifier.scheduled) == 1
    assert 'Docker image' in upgrader._notifier.scheduled[0]
    assert 'img:latest' in upgrader._notifier.scheduled[0]


def test_schedule_without_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(upgrader._actionLog, 'append_scheduled', lambda ev: None)
    monkeypatch.setattr(upgrader, '_schedule', lambda cb, delay: None)

    when = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())
    ev_data = UpgradeLogData(when, '1.2.3', 'some_id', tconf.UPGRADE_ENTRY)
    upgrader._scheduleUpgrade(ev_data, 10)

    assert len(upgrader._notifier.scheduled) == 1
    assert 'package' in upgrader._notifier.scheduled[0]
    assert tconf.UPGRADE_ENTRY in upgrader._notifier.scheduled[0]


def test_action_failed_without_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY)
    upgrader._action_failed(ev_data, reason='test error')

    assert len(upgrader._notifier.fail) == 1
    assert 'package' in upgrader._notifier.fail[0]
    assert tconf.UPGRADE_ENTRY in upgrader._notifier.fail[0]


def test_action_failed_with_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    upgrader._action_failed(ev_data, reason='test error')

    assert len(upgrader._notifier.fail) == 1
    assert 'Docker image' in upgrader._notifier.fail[0]
    assert 'img:latest' in upgrader._notifier.fail[0]


def test_cancel_without_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(upgrader._actionLog, 'append_cancelled', lambda ev: None)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY)
    upgrader.scheduledAction = ev_data
    upgrader._cancelScheduledUpgrade('test cancel')

    assert len(upgrader._notifier.cancel) == 1
    assert 'package' in upgrader._notifier.cancel[0]
    assert tconf.UPGRADE_ENTRY in upgrader._notifier.cancel[0]


def test_cancel_with_image(tconf, monkeypatch):
    upgrader = _make_upgrader(tconf)
    monkeypatch.setattr(upgrader._actionLog, 'append_cancelled', lambda ev: None)

    ev_data = UpgradeLogData(datetime.utcnow(), '1.2.3', 'some_id', tconf.UPGRADE_ENTRY, image_name='img:latest')
    upgrader.scheduledAction = ev_data
    upgrader._cancelScheduledUpgrade('test cancel')

    assert len(upgrader._notifier.cancel) == 1
    assert 'Docker image' in upgrader._notifier.cancel[0]
    assert 'img:latest' in upgrader._notifier.cancel[0]
