import pytest

from indy_common.constants import APP_NAME
from indy_common.version import src_version_cls
from indy_node.server.upgrader import Upgrader


@pytest.mark.parametrize(
    'lower_version,higher_version',
    [
        ('0.0.5', '0.0.6'),
        ('0.1.2', '0.2.6'),
        ('1.10.2', '2.0.6'),
        ('1.2.3.dev1', '1.2.3rc1'),
        ('1.2.3.dev1', '1.2.3'),
        ('1.2.3.rc2', '1.2.3'),
    ]
)
def test_versions_comparison(lower_version, higher_version):
    assert Upgrader.compareVersions(higher_version, lower_version) == 1
    assert Upgrader.compareVersions(lower_version, higher_version) == -1
    assert Upgrader.compareVersions(higher_version, higher_version) == 0

    version_cls = src_version_cls(APP_NAME)
    lower = version_cls(lower_version)
    higher = version_cls(higher_version)
    assert higher > lower
    assert not (lower > higher)
