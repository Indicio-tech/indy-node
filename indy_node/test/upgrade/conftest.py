from datetime import datetime, timedelta

import dateutil.tz
import pytest

from stp_core.loop.eventually import eventually
from plenum.common.constants import VERSION
from plenum.test.helper import randomText

from indy_common.constants import START, FORCE, APP_NAME

from indy_node.test import waits
from indy_node.test.upgrade.helper import bumpedVersion, \
    checkUpgradeScheduled, bumpVersion, sdk_ensure_upgrade_sent


@pytest.fixture(scope='module')
def nodeIds(nodeSet):
    return nodeSet[0].poolManager.nodeIds


@pytest.fixture(scope='function', params=[
    (APP_NAME, '1.0.0'),
])
def pckg(request):
    return request.param


@pytest.fixture(scope='function')
def validUpgrade(nodeIds, tconf, pckg):
    schedule = {}
    unow = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())
    startAt = unow + timedelta(seconds=100)
    acceptableDiff = tconf.MinSepBetweenNodeUpgrades + 1
    for i in nodeIds:
        schedule[i] = datetime.isoformat(startAt)
        startAt = startAt + timedelta(seconds=acceptableDiff + 3)

    new_version = bumpedVersion(pckg[1])

    return dict(name='upgrade-{}'.format(randomText(3)), version=new_version,
                action=START, schedule=schedule, timeout=1, package=pckg[0],
                sha256='db34a72a90d026dae49c3b3f0436c8d3963476c77468ad955845a1ccf7b03f55')


@pytest.fixture(scope='function')
def validUpgradeExpForceFalse(validUpgrade):
    nup = validUpgrade.copy()
    nup.update({FORCE: False})
    nup.update({VERSION: bumpVersion(validUpgrade[VERSION])})
    return nup


@pytest.fixture(scope='function')
def validUpgradeExpForceTrue(validUpgradeExpForceFalse):
    nup = validUpgradeExpForceFalse.copy()
    nup.update({FORCE: True})
    nup.update({VERSION: bumpVersion(validUpgradeExpForceFalse[VERSION])})
    return nup


@pytest.fixture(scope='function')
def validUpgradeSent(looper, nodeSet, tdir, sdk_pool_handle, sdk_wallet_trustee,
                     validUpgrade):
    sdk_ensure_upgrade_sent(looper, sdk_pool_handle,
                            sdk_wallet_trustee, validUpgrade)


@pytest.fixture(scope='function')
def validUpgradeSentExpForceFalse(
        looper,
        nodeSet,
        tdir,
        sdk_pool_handle,
        sdk_wallet_trustee,
        validUpgradeExpForceFalse):
    sdk_ensure_upgrade_sent(looper, sdk_pool_handle,
                            sdk_wallet_trustee, validUpgradeExpForceFalse)


@pytest.fixture(scope='function')
def validUpgradeSentExpForceTrue(looper, nodeSet, tdir, sdk_pool_handle,
                                 sdk_wallet_trustee, validUpgradeExpForceTrue):
    sdk_ensure_upgrade_sent(looper, sdk_pool_handle,
                            sdk_wallet_trustee, validUpgradeExpForceTrue)


@pytest.fixture(scope='function')
def upgradeScheduled(validUpgradeSent, looper, nodeSet, validUpgrade):
    looper.run(
        eventually(
            checkUpgradeScheduled,
            nodeSet,
            validUpgrade[VERSION],
            retryWait=1,
            timeout=waits.expectedUpgradeScheduled()))


@pytest.fixture(scope='function')
def upgradeScheduledExpForceFalse(validUpgradeSentExpForceFalse, looper,
                                  nodeSet, validUpgradeExpForceFalse):
    looper.run(eventually(checkUpgradeScheduled, nodeSet,
                          validUpgradeExpForceFalse[VERSION], retryWait=1,
                          timeout=waits.expectedUpgradeScheduled()))


@pytest.fixture(scope='function')
def upgradeScheduledExpForceTrue(validUpgradeSentExpForceTrue, looper, nodeSet,
                                 validUpgradeExpForceTrue):
    looper.run(eventually(checkUpgradeScheduled, nodeSet,
                          validUpgradeExpForceTrue[VERSION], retryWait=1,
                          timeout=waits.expectedUpgradeScheduled()))


@pytest.fixture(scope='function')
def invalidUpgrade(nodeIds, tconf, validUpgrade):
    nup = validUpgrade.copy()
    schedule = {}
    unow = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())
    startAt = unow + timedelta(seconds=60)
    acceptableDiff = tconf.MinSepBetweenNodeUpgrades + 1
    for i in nodeIds:
        schedule[i] = datetime.isoformat(startAt)
        startAt = startAt + timedelta(seconds=acceptableDiff - 3)
    nup.update(dict(name='upgrade-14', version=bumpedVersion(), action=START,
                    schedule=schedule,
                    sha256='46c715a90b1067142d548cb1f1405b0486b32b1a27d418ef3a52bd976e9fae50',
                    timeout=10))
    return nup
