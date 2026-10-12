import os
import pytest
from plenum.test.conftest import tdir
from indy_common.test.conftest import tconf, looper


@pytest.fixture
def whitelist():
    return ['Rollback also failed', 'Rollback failed', 'failed upgrade']
