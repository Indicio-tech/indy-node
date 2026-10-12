import pytest

pytestmark = pytest.mark.skip(
    reason="Obsolete: upgrader now uses Docker compose instead of node control tool"
)


def testScheduleNodeUpgrade():
    pass
