import os
import tempfile
import pytest
from plenum.test.conftest import tdir
from indy_common.test.conftest import tconf, looper


@pytest.fixture
def whitelist():
    return ['Rollback also failed', 'Rollback failed', 'failed upgrade']


@pytest.fixture
def compose_dir():
    # _set_compose_service_image does real file I/O against this directory's
    # docker-compose.yaml - tests that drive Upgrader's docker code paths
    # need a real (if trivial) compose file here, even when the actual
    # `docker`/`docker compose` subprocess calls themselves are mocked.
    d = tempfile.mkdtemp()
    with open(os.path.join(d, 'docker-compose.yaml'), 'w') as f:
        f.write(
            'services:\n'
            '  indy-node:\n'
            '    image: placeholder:latest\n'
        )
    return d
