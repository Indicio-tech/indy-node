import os
import subprocess
import asyncio
import time
from datetime import datetime
from functools import partial
from typing import Optional, Callable, Dict

import dateutil.parser
import dateutil.tz

from indy_node.server.node_maintainer import NodeMaintainer
from plenum.common.txn_util import is_forced, get_seq_no, get_type, get_payload_data, get_req_id, get_from
from stp_core.common.log import getlogger
from plenum.common.constants import VERSION
from common.version import InvalidVersionError

from indy_common.constants import ACTION, POOL_UPGRADE, START, SCHEDULE, \
    CANCEL, JUSTIFICATION, TIMEOUT, NODE_UPGRADE, \
    PACKAGE, APP_NAME, DOCKER_IMAGE, DEFAULT_DOCKER_IMAGE
from indy_common.version import src_version_cls
from indy_node.server.upgrade_log import UpgradeLogData, UpgradeLog
logger = getlogger()

_ROLLBACK_TAG = "indy-node-rollback"
_DOCKER_INFO_TIMEOUT = 10
_DOCKER_INSPECT_TIMEOUT = 10
_DOCKER_PULL_TIMEOUT = 120
_DOCKER_UP_TIMEOUT = 120
_DOCKER_HEALTH_POLL_INTERVAL = 2
_DOCKER_HEALTH_TIMEOUT = 30


class Upgrader(NodeMaintainer):

    def __init__(self, nodeId, nodeName, dataDir, config, ledger=None,
                 actionLog=None, actionFailedCallback: Callable = None,
                 action_start_callback: Callable = None):
        self._should_notify_about_upgrade = False
        super().__init__(nodeId, nodeName, dataDir, config, ledger, actionLog,
                         actionFailedCallback, action_start_callback)

    @staticmethod
    def get_action_id(txn):
        seq_no = get_seq_no(txn) or ''
        if is_forced(txn):
            seq_no = ''
        return '{}{}'.format(get_req_id(txn), seq_no)

    # implements legacy logic used only by migration logic,
    # please use Version classes in code instead
    # TODO refactor migration logic to get rid of that API usage
    @staticmethod
    def compareVersions(verA: str, verB: str) -> int:
        version_cls = src_version_cls(APP_NAME)
        return version_cls.cmp(version_cls(verA), version_cls(verB))

    def _defaultLog(self, dataDir, config):
        log = os.path.join(dataDir, config.upgradeLogFile)
        return UpgradeLog(file_path=log)

    def _is_action_started(self):
        last_action = self.lastActionEventInfo
        if not last_action:
            logger.debug('Node {} has no upgrade events'.format(self.nodeName))
            return False

        if last_action.ev_type != UpgradeLog.Events.started:
            logger.debug(
                "Upgrade for node {} was not scheduled. "
                "Last event is {}"
                .format(self.nodeName, last_action))
            return False

        return True

    def _update_action_log_for_started_action(self):
        ev_data = self.lastActionEventInfo.data

        self._should_notify_about_upgrade = True
        if not self.didLastExecutedUpgradeSucceeded:
            self._actionLog.append_failed(ev_data)
            self._action_failed(ev_data, external_reason=True)
            return

        self._actionLog.append_succeeded(ev_data)
        logger.info(
            "Node '{}' successfully upgraded to version {}"
            .format(self.nodeName, ev_data.version))
        if ev_data.image_name:
            self._notifier.sendMessageUponNodeUpgradeComplete(
                "Docker image {} on node '{}' to version {} scheduled on {} "
                " with upgrade_id {} completed successfully"
                .format(ev_data.image_name, self.nodeName,
                        ev_data.version, ev_data.when, ev_data.upgrade_id))
        else:
            self._notifier.sendMessageUponNodeUpgradeComplete(
                "Upgrade of package {} on node '{}' to version {} scheduled on {} "
                " with upgrade_id {} completed successfully"
                .format(ev_data.pkg_name, self.nodeName,
                        ev_data.version, ev_data.when, ev_data.upgrade_id))

    def should_notify_about_upgrade_result(self):
        # do not rely on NODE_UPGRADE txn in config ledger, since in
        # some cases (for example, when
        # we run POOL_UPGRADE with force=true), we may not have
        # IN_PROGRESS NODE_UPGRADE in the ledger.

        # send NODE_UPGRADE txn only if we were in Upgrade Started
        # state at the very beginning (after Node restarted)
        return self._should_notify_about_upgrade

    def notified_about_action_result(self):
        self._should_notify_about_upgrade = False

    def get_last_node_upgrade_txn(self, start_no: int = None):
        return self.get_upgrade_txn(
            lambda txn: get_type(txn) == NODE_UPGRADE and get_from(txn) == self.nodeId,
            start_no=start_no,
            reverse=True)

    def get_upgrade_txn(self, predicate: Callable = None, start_no: int = None,
                        reverse: bool = False) -> Optional[Dict]:
        def txn_filter(txn):
            return not predicate or predicate(txn)

        def traverse_end_condition(seq_no):
            if reverse:
                return seq_no > 0
            return seq_no <= len(self.ledger)

        inc = 1
        init_start_no = 1
        if reverse:
            inc = -1
            init_start_no = len(self.ledger)

        seq_no = start_no if start_no is not None else init_start_no
        while traverse_end_condition(seq_no):
            txn = self.ledger.getBySeqNo(seq_no)
            if txn_filter(txn):
                return txn
            seq_no += inc
        return None

    # TODO: PoolConfig and Updater both read config ledger independently
    def processLedger(self) -> None:
        """
        Checks ledger for planned but not yet performed upgrades
        and schedules upgrade for the most recent one

        Assumption: Only version is enough to identify a release, no hash
        checking is done
        :return:
        """
        logger.debug(
            '{} processing config ledger for any upgrades'.format(self))
        last_pool_upgrade_txn_start = self.get_upgrade_txn(
            lambda txn: get_type(txn) == POOL_UPGRADE and get_payload_data(txn)[ACTION] == START, reverse=True)
        if last_pool_upgrade_txn_start:
            logger.info('{} found upgrade START txn {}'.format(
                self, last_pool_upgrade_txn_start))
            last_pool_upgrade_txn_seq_no = get_seq_no(last_pool_upgrade_txn_start)

            # searching for CANCEL for this upgrade submitted after START txn
            last_pool_upgrade_txn_cancel = self.get_upgrade_txn(
                lambda txn:
                get_type(txn) == POOL_UPGRADE and get_payload_data(txn)[ACTION] == CANCEL and get_payload_data(txn)
                [VERSION] == get_payload_data(last_pool_upgrade_txn_start)[VERSION],
                start_no=last_pool_upgrade_txn_seq_no + 1)
            if last_pool_upgrade_txn_cancel:
                logger.info('{} found upgrade CANCEL txn {}'.format(
                    self, last_pool_upgrade_txn_cancel))
                return

            self.handleUpgradeTxn(last_pool_upgrade_txn_start)

    # TODO might necessary to improve tests
    @property
    def didLastExecutedUpgradeSucceeded(self) -> bool:
        """
        Checks last record in upgrade log to find out whether it
        is about scheduling upgrade. If so - checks whether current version
        is equals to the one in that record

        :returns: upgrade execution result
        """
        lastEventInfo = self.lastActionEventInfo
        if lastEventInfo:
            ev_data = lastEventInfo.data
            if ev_data.image_name:
                return self._did_docker_upgrade_succeed(ev_data)
            return True
        return False

    def _wait_for_container_healthy(self, timeout=None):
        if timeout is None:
            timeout = _DOCKER_HEALTH_TIMEOUT
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Status}}",
                     self.config.UPGRADE_ENTRY],
                    capture_output=True, text=True, timeout=_DOCKER_INSPECT_TIMEOUT
                )
                if result.returncode == 0:
                    status = result.stdout.strip()
                    if status == "running":
                        logger.info("Container {} is running".format(self.config.UPGRADE_ENTRY))
                        return True
                    elif status in ("created", "restarting"):
                        time.sleep(_DOCKER_HEALTH_POLL_INTERVAL)
                        continue
                    else:
                        raise RuntimeError(
                            "Container {} is in unexpected state: {}".format(
                                self.config.UPGRADE_ENTRY, status))
                else:
                    last_error = result.stderr.strip()
                    time.sleep(_DOCKER_HEALTH_POLL_INTERVAL)
            except Exception as exc:
                last_error = str(exc)
                time.sleep(_DOCKER_HEALTH_POLL_INTERVAL)
        raise RuntimeError(
            "Container {} did not reach running state within {}s. Last error: {}".format(
                self.config.UPGRADE_ENTRY, timeout, last_error or "unknown"))

    def _check_docker_available(self):
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=_DOCKER_INFO_TIMEOUT
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Docker is not available: {}. "
                "Ensure Docker Engine is installed and running."
                .format(result.stderr.strip()))

    def _save_current_image_for_rollback(self):
        try:
            inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{.Config.Image}}\n{{.Image}}",
                 self.config.UPGRADE_ENTRY],
                capture_output=True, text=True, timeout=_DOCKER_INSPECT_TIMEOUT
            )
            if inspect.returncode == 0:
                lines = inspect.stdout.strip().split('\n')
                if len(lines) >= 2:
                    current_ref = lines[0]
                    current_digest = lines[1]
                    tag_result = subprocess.run(
                        ["docker", "tag", current_digest, _ROLLBACK_TAG],
                        capture_output=True, text=True, timeout=_DOCKER_INSPECT_TIMEOUT
                    )
                    if tag_result.returncode == 0:
                        logger.info("Saved current image {} (digest {}) as rollback target".format(
                            current_ref, current_digest[:19]))
                        return current_ref
                    else:
                        logger.info("Could not tag current image for rollback: {}".format(
                            tag_result.stderr.strip()))
                else:
                    logger.info("Could not parse docker inspect output")
            else:
                logger.info("Could not inspect container {}: {}".format(
                    self.config.UPGRADE_ENTRY, inspect.stderr.strip()))
        except Exception as exc:
            logger.info("No previous container to save for rollback: {}".format(exc))
        return None

    def _rollback_upgrade(self, compose_dir, current_ref):
        logger.info("Attempting rollback to image {}".format(current_ref or _ROLLBACK_TAG))
        try:
            subprocess.run(
                ["docker", "tag", _ROLLBACK_TAG, current_ref],
                capture_output=True, text=True, timeout=_DOCKER_INSPECT_TIMEOUT
            )
            rollback_up = subprocess.run(
                ["docker", "compose", "--project-directory", compose_dir,
                 "up", "-d", "--force-recreate", "indy-node"],
                capture_output=True, text=True, timeout=_DOCKER_UP_TIMEOUT
            )
            if rollback_up.returncode == 0:
                logger.info("Rollback to {} appears successful".format(current_ref))
                return True
            else:
                logger.error("Rollback also failed: {}".format(rollback_up.stderr.strip()))
                return False
        except Exception as rollback_ex:
            logger.error("Rollback failed: {}".format(rollback_ex))
            return False

    def _did_docker_upgrade_succeed(self, ev_data) -> bool:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.Config.Image}}",
                 self.config.UPGRADE_ENTRY],
                capture_output=True, text=True, timeout=_DOCKER_INSPECT_TIMEOUT
            )
            if result.returncode == 0:
                running_image = result.stdout.strip()
                return running_image == ev_data.image_name
            else:
                logger.warning(
                    "{} failed to inspect Docker container: {}"
                    .format(self, result.stderr.strip())
                )
        except Exception as exc:
            logger.warning(
                "{} failed to check Docker container status: {}"
                .format(self, exc)
            )
        return False

    def handleUpgradeTxn(self, txn) -> None:
        """
        Handles transaction of type POOL_UPGRADE
        Can schedule or cancel upgrade to a newer
        version at specified time

        :param txn:
        """
        FINALIZING_EVENT_TYPES = [UpgradeLog.Events.succeeded, UpgradeLog.Events.failed]

        if get_type(txn) != POOL_UPGRADE:
            return

        logger.info("Node '{}' handles upgrade txn {}".format(self.nodeName, txn))
        txn_data = get_payload_data(txn)
        action = txn_data[ACTION]
        version = txn_data[VERSION]
        justification = txn_data.get(JUSTIFICATION)
        pkg_name = txn_data.get(PACKAGE, self.config.UPGRADE_ENTRY)
        image_name = txn_data.get(DOCKER_IMAGE)
        upgrade_id = self.get_action_id(txn)

        # TODO test
        try:
            version = src_version_cls(pkg_name)(version)
        except InvalidVersionError as exc:
            logger.warning(
                "{} can't handle upgrade txn with version {} for package {}: {}"
                .format(self, version, pkg_name, exc)
            )
            return

        if action == START:
            # forced txn could have partial schedule list
            if self.nodeId not in txn_data[SCHEDULE]:
                logger.info("Node '{}' disregards upgrade txn {}".format(
                    self.nodeName, txn))
                return

            last_event = self.lastActionEventInfo
            if last_event:
                if last_event.data.upgrade_id == upgrade_id and last_event.ev_type in FINALIZING_EVENT_TYPES:
                    logger.info(
                        "Node '{}' has already performed an upgrade with upgrade_id {}. "
                        "Last recorded event is {}"
                        .format(self.nodeName, upgrade_id, last_event.data))
                    return

            when = txn_data[SCHEDULE][self.nodeId]
            failTimeout = txn_data.get(TIMEOUT, self.defaultActionTimeout)

            if isinstance(when, str):
                when = dateutil.parser.parse(when)

            new_ev_data = UpgradeLogData(when, version, upgrade_id, pkg_name, image_name)

            if self.scheduledAction:
                if self.scheduledAction == new_ev_data:
                    logger.debug(
                        "Node {} already scheduled upgrade to version '{}' "
                        .format(self.nodeName, version))
                    return
                else:
                    logger.info(
                        "Node '{}' cancels previous upgrade and schedules a new one to {}"
                        .format(self.nodeName, version))
                    self._cancelScheduledUpgrade(justification)

            logger.info("Node '{}' schedules upgrade to {}".format(self.nodeName, version))

            self._scheduleUpgrade(new_ev_data, failTimeout)
            return

        if action == CANCEL:
            if self.scheduledAction and self.scheduledAction.version == version:
                self._cancelScheduledUpgrade(justification)
                logger.info("Node '{}' cancels upgrade to {}".format(
                    self.nodeName, version))
            return

        logger.error(
            "Got {} transaction with unsupported action {}".format(
                POOL_UPGRADE, action))

    def _scheduleUpgrade(self,
                         ev_data: UpgradeLogData,
                         failTimeout) -> None:
        """
        Schedules node upgrade to a newer version

        :param ev_data: upgrade event parameters
        """
        logger.info(
            "{}'s upgrader processing upgrade for version {}={}"
            .format(self, ev_data.pkg_name, ev_data.version))
        now = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())

        if ev_data.image_name:
            self._notifier.sendMessageUponNodeUpgradeScheduled(
                "Docker image {} on node '{}' to version {} "
                "has been scheduled on {}"
                .format(ev_data.image_name, self.nodeName,
                        ev_data.version, ev_data.when))
        else:
            self._notifier.sendMessageUponNodeUpgradeScheduled(
                "Upgrade of package {} on node '{}' to version {} "
                "has been scheduled on {}"
                .format(ev_data.pkg_name, self.nodeName,
                        ev_data.version, ev_data.when))
        self._actionLog.append_scheduled(ev_data)

        callAgent = partial(self._callUpgradeAgent, ev_data, failTimeout)
        delay = 0
        if now < ev_data.when:
            delay = (ev_data.when - now).total_seconds()
        self.scheduledAction = ev_data
        self._schedule(callAgent, delay)

    def _cancelScheduledUpgrade(self, justification=None) -> None:
        """
        Cancels scheduled upgrade

        :param when: time upgrade was scheduled to
        :param version: version upgrade scheduled for
        """

        if self.scheduledAction:
            why_prefix = ": "
            why = justification
            if justification is None:
                why_prefix = ", "
                why = "cancellation reason not specified"

            ev_data = self.scheduledAction
            if ev_data.image_name:
                logger.info("Cancelling upgrade {}"
                            " of node {}"
                            " of Docker image {}"
                            " to version {}"
                            " scheduled on {}"
                            "{}{}"
                            .format(ev_data.upgrade_id,
                                    self.nodeName,
                                    ev_data.image_name,
                                    ev_data.version,
                                    ev_data.when,
                                    why_prefix,
                                    why))
                self._notifier.sendMessageUponPoolUpgradeCancel(
                    "Upgrade of Docker image {} on node '{}' to version {} "
                    "has been cancelled due to {}"
                    .format(ev_data.image_name, self.nodeName,
                            ev_data.version, why))
            else:
                logger.info("Cancelling upgrade {}"
                            " of node {}"
                            " of package {}"
                            " to version {}"
                            " scheduled on {}"
                            "{}{}"
                            .format(ev_data.upgrade_id,
                                    self.nodeName,
                                    ev_data.pkg_name,
                                    ev_data.version,
                                    ev_data.when,
                                    why_prefix,
                                    why))
                self._notifier.sendMessageUponPoolUpgradeCancel(
                    "Upgrade of package {} on node '{}' to version {} "
                    "has been cancelled due to {}"
                    .format(ev_data.pkg_name, self.nodeName,
                            ev_data.version, why))

            self._unscheduleAction()
            self._actionLog.append_cancelled(ev_data)

    def _callUpgradeAgent(self, ev_data, failTimeout) -> None:
        """
        Callback which is called when upgrade time come.
        Writes upgrade record to upgrade log and asks
        node control service to perform upgrade

        :param when: upgrade time
        :param version: version to upgrade to
        """

        logger.info("{}'s upgrader calling agent for upgrade".format(self))
        self._actionLog.append_started(ev_data)
        self._action_start_callback()
        self.scheduledAction = None
        asyncio.ensure_future(
            self._sendUpgradeRequest(ev_data, failTimeout))

    async def _sendUpgradeRequest(self, ev_data, failTimeout):
        if ev_data.image_name:
            logger.info("Performing Docker upgrade to image {}".format(ev_data.image_name))
            compose_dir = self.config.COMPOSE_PROJECT_DIR
            try:
                self._check_docker_available()

                current_ref = self._save_current_image_for_rollback()

                pull = subprocess.run(
                    ["docker", "compose", "--project-directory", compose_dir, "pull", "indy-node"],
                    capture_output=True, text=True, timeout=_DOCKER_PULL_TIMEOUT
                )
                if pull.returncode != 0:
                    raise RuntimeError("docker compose pull failed: {}".format(pull.stderr.strip()))
                up = subprocess.run(
                    ["docker", "compose", "--project-directory", compose_dir, "up", "-d", "--force-recreate", "indy-node"],
                    capture_output=True, text=True, timeout=_DOCKER_UP_TIMEOUT
                )
                if up.returncode != 0:
                    raise RuntimeError("docker compose up failed: {}".format(up.stderr.strip()))

                try:
                    self._wait_for_container_healthy()
                except Exception as health_ex:
                    logger.warning("Health check failed after upgrade: {}".format(health_ex))
                    if current_ref:
                        self._rollback_upgrade(compose_dir, current_ref)
                    raise

            except Exception as ex:
                logger.warning("Docker upgrade failed: {}".format(ex))
                self._action_failed(ev_data, reason=str(ex))
                self._unscheduleAction()
                return
            logger.info("Waiting {} minutes for Docker upgrade to complete".format(failTimeout))
            timesUp = partial(self._declareTimeoutExceeded, ev_data)
            self._schedule(timesUp, self.get_timeout(failTimeout))
            return

        logger.warning("No image_name provided; upgrade cannot proceed without Docker image")
        self._action_failed(ev_data, reason="no Docker image specified")
        self._unscheduleAction()

    def _declareTimeoutExceeded(self, ev_data: UpgradeLogData):
        """
        This function is called when time for upgrade is up
        """
        logger.info("Timeout exceeded for {}:{}"
                    .format(ev_data.when, ev_data.version))
        last = self._actionLog.last_event
        # TODO test this
        if last and last.ev_type == UpgradeLog.Events.failed and last.data == ev_data:
            return None

        self._action_failed(ev_data, reason="exceeded upgrade timeout")

        self._unscheduleAction()
        self._actionFailedCallback()

    def _action_failed(self,
                       ev_data: UpgradeLogData,
                       reason=None,
                       external_reason=False):
        if reason is None:
            reason = "unknown reason"
        if ev_data.image_name:
            error_message = (
                "Node {} failed upgrade {} to "
                "version {} of Docker image {} "
                "scheduled on {} because of {}"
                .format(self.nodeName,
                        ev_data.upgrade_id,
                        ev_data.version,
                        ev_data.image_name,
                        ev_data.when,
                        reason)
            )
        else:
            error_message = (
                "Node {} failed upgrade {} to "
                "version {} of package {} "
                "scheduled on {} because of {}"
                .format(self.nodeName,
                        ev_data.upgrade_id,
                        ev_data.version,
                        ev_data.pkg_name,
                        ev_data.when,
                        reason)
            )
        logger.error(error_message)
        if external_reason:
            logger.error("This problem may have external reasons, "
                         "check syslog for more information")
        self._notifier.sendMessageUponNodeUpgradeFail(error_message)

    def isScheduleValid(self, schedule, node_srvs, force) -> (bool, str):
        """
        Validates schedule of planned node upgrades

        :param schedule: dictionary of node ids and upgrade times
        :param node_srvs: dictionary of node ids and services
        :return: a 2-tuple of whether schedule valid or not and the reason
        """

        # flag "force=True" ignore basic checks! only datetime format is
        # checked
        times = []
        non_demoted_nodes = set([k for k, v in node_srvs.items() if v])
        if not force and set(schedule.keys()) != non_demoted_nodes:
            return False, 'Schedule should contain id of all nodes'
        now = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc())
        for dateStr in schedule.values():
            try:
                when = dateutil.parser.parse(dateStr)
                if when <= now and not force:
                    return False, '{} is less than current time'.format(when)
                times.append(when)
            except ValueError:
                return False, '{} cannot be parsed to a time'.format(dateStr)
        if force:
            return True, ''
        times = sorted(times)
        for i in range(len(times) - 1):
            diff = (times[i + 1] - times[i]).total_seconds()
            if diff < self.config.MinSepBetweenNodeUpgrades:
                return False, 'time span between upgrades is {} ' \
                              'seconds which is less than specified ' \
                              'in the config'.format(diff)
        return True, ''

