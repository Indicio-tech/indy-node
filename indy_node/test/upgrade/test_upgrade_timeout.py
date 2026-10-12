from datetime import datetime

from stp_core.loop.eventually import eventually
from indy_node.server.upgrade_log import UpgradeLogData
from indy_node.server.upgrader import Upgrader
import functools

whitelist = ['Failed to upgrade node',
             'failed upgrade',
             'This problem may have external reasons, check syslog for more information']


def testTimeoutWorks(nodeSet, looper, monkeypatch, tconf):
    """
    Checks that after some timeout upgrade is marked as failed if
    it not started
    """
    async def mock_send_upgrade(self, ev_data, failTimeout):
        logger.info("Waiting {} minutes for upgrade to be performed".format(failTimeout))
        timesUp = functools.partial(self._declareTimeoutExceeded, ev_data)
        self._schedule(timesUp, self.get_timeout(failTimeout))

    from stp_core.common.log import getlogger
    logger = getlogger()

    # patch get_timeout not to wait one whole minute
    monkeypatch.setattr(Upgrader, 'get_timeout', lambda self, timeout: timeout)
    # patch _sendUpgradeRequest to only schedule the timeout (skip Docker/upgrade)
    monkeypatch.setattr(Upgrader, '_sendUpgradeRequest', mock_send_upgrade)
    pending = {node.name for node in nodeSet}
    version = '1.5.1'
    timeout = 1

    def chk():
        nonlocal pending
        assert len(pending) == 0

    def upgrade_failed_callback_test(nodeName):
        nonlocal pending
        pending.remove(nodeName)

    ev_data = UpgradeLogData(datetime.utcnow(), version, 'some_id', tconf.UPGRADE_ENTRY)
    for node in nodeSet:
        monkeypatch.setattr(
            node.upgrader,
            '_actionFailedCallback',
            functools.partial(
                upgrade_failed_callback_test,
                node.name))
        looper.run(node.upgrader._sendUpgradeRequest(ev_data, timeout))

    looper.run(eventually(chk))
