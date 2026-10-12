import pytest

from indy_node.server.upgrader import Upgrader
from indy_node.test.pool_config.helper import sdk_ensure_pool_config_sent
from indy_node.test.upgrade.conftest import pckg


@pytest.fixture(scope='function', autouse=True)
def patch_current_pkg_version(monkeypatch, pckg):
    # See indy_node/test/upgrade/conftest.py: these tests reuse the upgrade
    # suite's fictional package version chain, so pin the downgrade check's
    # "current version" to that chain instead of the real installed version.
    monkeypatch.setattr(
        Upgrader, '_get_current_pkg_version', staticmethod(lambda: pckg[1]))


def genPoolConfig(writes: bool, force: bool):
    return dict(writes=writes, force=force)


@pytest.fixture(scope='module')
def poolConfigWTFF():
    return genPoolConfig(writes=True, force=False)


@pytest.fixture(scope='module')
def poolConfigWFFF():
    return genPoolConfig(writes=False, force=False)


@pytest.fixture(scope='module')
def poolConfigWTFT():
    return genPoolConfig(writes=True, force=True)


@pytest.fixture(scope='module')
def poolConfigWFFT():
    return genPoolConfig(writes=False, force=True)


@pytest.fixture(scope="module")
def poolConfigSent(looper, nodeSet, sdk_pool_handle, sdk_wallet_trustee, poolCfg):
    sdk_ensure_pool_config_sent(looper, sdk_pool_handle, sdk_wallet_trustee, poolCfg)
