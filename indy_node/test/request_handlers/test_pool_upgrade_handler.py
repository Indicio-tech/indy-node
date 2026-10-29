import pytest
from indy_common.constants import POOL_UPGRADE, ACTION, START, DOCKER_IMAGE, PACKAGE
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


def _set_schedule_valid(handler, valid=True):
    handler.pool_manager.getNodesServices = lambda: 1
    handler.upgrader.isScheduleValid = lambda schedule, node_srvs, force: (valid, '')


def test_pool_upgrade_static_validation_fails_action(pool_upgrade_handler,
                                                     pool_upgrade_request):
    pool_upgrade_request.operation[ACTION] = 'smth'
    with pytest.raises(InvalidClientRequest) as e:
        pool_upgrade_handler.static_validation(pool_upgrade_request)
    e.match('not a valid action')


def test_pool_upgrade_static_validation_fails_schedule(pool_upgrade_handler,
                                                       pool_upgrade_request):
    _set_schedule_valid(pool_upgrade_handler, False)
    with pytest.raises(InvalidClientRequest) as e:
        pool_upgrade_handler.static_validation(pool_upgrade_request)
    e.match('not a valid schedule since')


def test_pool_upgrade_static_validation_fails_missing_image_and_package(
        pool_upgrade_handler, pool_upgrade_request):
    _set_schedule_valid(pool_upgrade_handler)
    with pytest.raises(InvalidClientRequest) as e:
        pool_upgrade_handler.static_validation(pool_upgrade_request)
    e.match('One of')


def test_pool_upgrade_static_validation_passes_with_image(
        pool_upgrade_handler, pool_upgrade_request):
    _set_schedule_valid(pool_upgrade_handler)
    pool_upgrade_request.operation[DOCKER_IMAGE] = 'ghcr.io/hyperledger/indy-node:latest'
    pool_upgrade_handler.static_validation(pool_upgrade_request)


def test_pool_upgrade_static_validation_passes_with_package(
        pool_upgrade_handler, pool_upgrade_request):
    _set_schedule_valid(pool_upgrade_handler)
    pool_upgrade_request.operation[PACKAGE] = 'indy-node'
    pool_upgrade_handler.static_validation(pool_upgrade_request)
