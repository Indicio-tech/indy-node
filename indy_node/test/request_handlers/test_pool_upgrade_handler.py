import pytest
from indy_common.constants import POOL_UPGRADE, ACTION, START
from indy_node.server.request_handlers.config_req_handlers.pool_upgrade_handler import PoolUpgradeHandler
from plenum.common.constants import VERSION, TXN_PAYLOAD, TXN_PAYLOAD_DATA
from plenum.common.exceptions import InvalidClientRequest

from plenum.common.request import Request
from plenum.common.util import randomString
from plenum.test.testing_utils import FakeSomething


@pytest.fixture(scope='function')
def pool_upgrade_request():
    return Request(identifier=randomString(),
                   reqId=5,
                   operation={
                       'type': POOL_UPGRADE,
                       ACTION: START,
                       VERSION: '1.2.3'
                   })


@pytest.fixture(scope='function')
def pool_upgrade_handler(write_auth_req_validator):
    return PoolUpgradeHandler(
        None,
        FakeSomething(),
        write_auth_req_validator,
        FakeSomething()
    )


def test_pool_upgrade_static_validation_fails_action(pool_upgrade_handler,
                                                     pool_upgrade_request):
    pool_upgrade_request.operation[ACTION] = 'smth'
    with pytest.raises(InvalidClientRequest) as e:
        pool_upgrade_handler.static_validation(pool_upgrade_request)
    e.match('not a valid action')


def test_pool_upgrade_static_validation_fails_schedule(pool_upgrade_handler,
                                                       pool_upgrade_request):
    pool_upgrade_handler.pool_manager.getNodesServices = lambda: 1
    pool_upgrade_handler.upgrader.isScheduleValid = lambda schedule, node_srvs, force: (False, '')
    with pytest.raises(InvalidClientRequest) as e:
        pool_upgrade_handler.static_validation(pool_upgrade_request)
    e.match('not a valid schedule since')


def test_pool_upgrade_static_validation_passes(pool_upgrade_handler,
                                               pool_upgrade_request):
    pool_upgrade_handler.pool_manager.getNodesServices = lambda: 1
    pool_upgrade_handler.upgrader.isScheduleValid = lambda schedule, node_srvs, force: (True, '')
    pool_upgrade_handler.static_validation(pool_upgrade_request)
