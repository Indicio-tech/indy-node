import os

from indy_node.server.upgrade_log import UpgradeLog, UpgradeLogData
from indy_common.constants import APP_NAME


def test_upgrade_log_loads_entries_without_image_name(tdir):
    log_file = os.path.join(tdir, 'test_upgrade_log')
    entries = (
        "2019-02-28 07:36:23.135789\tscheduled\t2019-02-28 07:37:11+00:00\t1.6.83\t15513393820971606221\r\n"
        "2019-02-28 07:37:11.008484\tstarted\t2019-02-28 07:37:11+00:00\t1.6.83\t15513393820971606221\tindy-node\r\n"
        "2019-02-28 07:38:33.721644\tsucceeded\t2019-02-28 07:37:11+00:00\t1.6.83\t15513393820971606221\tindy-node\r\n"
    )
    with open(log_file, 'w', newline='') as f:
        f.write(entries)
    upgrade_log = UpgradeLog(log_file)

    assert len(upgrade_log) == 3
    for ev in upgrade_log:
        assert ev.data.image_name is None
    assert upgrade_log.last_event.data.image_name is None
    assert upgrade_log.last_event.data.pkg_name == APP_NAME
