import json
import os
import select
import signal
import socket
import sys
import time

from stp_core.common.log import getlogger

logger = getlogger()

CONTROL_SERVICE_HOST = "127.0.0.1"
CONTROL_SERVICE_PORT = 30003
NODE_INFO_STALE_SECONDS = 300


class NodeControlTool:
    def __init__(self, config=None):
        self.config = config
        self._load_config()
        self._listen()

    def _load_config(self):
        if self.config is not None:
            self.host = getattr(self.config, 'controlServiceHost', CONTROL_SERVICE_HOST)
            self.port = int(getattr(self.config, 'controlServicePort', CONTROL_SERVICE_PORT))
            self.network_name = getattr(self.config, 'NETWORK_NAME', 'sandbox')
            self.ledger_dir = getattr(self.config, 'LEDGER_DIR', '/var/lib/indy')
        else:
            self.host = CONTROL_SERVICE_HOST
            self.port = CONTROL_SERVICE_PORT
            self.network_name = os.environ.get('NETWORK_NAME', 'sandbox')
            self.ledger_dir = os.environ.get('LEDGER_DIR', '/var/lib/indy')

        self.node_name = os.environ.get('NODE_NAME', '')
        self.client_port = int(os.environ.get('CLIENT_PORT', '0'))

    def _listen(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.setblocking(0)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        logger.info('Node control tool listening on {} port {}'.format(
            self.host, self.port))

    def _handle_health(self):
        checks = {}

        checks['control_tool'] = 'ok'

        if self.client_port > 0:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect(('127.0.0.1', self.client_port))
                s.close()
                checks['zmq_client_port'] = 'ok'
            except (ConnectionRefusedError, socket.timeout, OSError):
                checks['zmq_client_port'] = 'unhealthy'
        else:
            checks['zmq_client_port'] = 'unknown'

        node_info_path = os.path.join(
            self.ledger_dir, self.network_name, 'data', self.node_name, 'node_info')
        try:
            mtime = os.path.getmtime(node_info_path)
            age = time.time() - mtime
            if age > NODE_INFO_STALE_SECONDS:
                checks['node_info'] = 'stale'
            else:
                checks['node_info'] = 'ok'
        except OSError:
            checks['node_info'] = 'missing'

        zmq_status = checks.get('zmq_client_port', 'unknown')
        if zmq_status == 'unhealthy':
            status = 'unhealthy'
        elif checks.get('node_info') in ('missing', 'stale'):
            status = 'degraded'
        else:
            status = 'ok'

        response = {
            'status': status,
            'checks': checks,
            'node_name': self.node_name,
            'ports': {
                'node': int(os.environ.get('NODE_PORT', '0')),
                'client': self.client_port,
            },
        }
        return response

    def _handle_restart(self):
        logger.info('Restart requested, sending SIGTERM to PID 1')
        try:
            os.kill(1, signal.SIGTERM)
        except ProcessLookupError:
            logger.warning('PID 1 not found')
        return {'status': 'ok', 'message': 'restart signal sent'}

    def _process_data(self, data):
        try:
            command = json.loads(data.decode('utf-8'))
        except (json.decoder.JSONDecodeError, UnicodeDecodeError) as e:
            return {'status': 'error', 'message': 'invalid JSON: {}'.format(e)}

        msg_type = command.get('message_type') or command.get('command')
        if msg_type == 'health':
            return self._handle_health()
        elif msg_type == 'restart':
            return self._handle_restart()
        else:
            return {'status': 'error', 'message': 'unknown command: {}'.format(msg_type)}

    def start(self):
        readers = [self.server]
        writers = []
        errs = []

        logger.info('Node control tool starting event loop')
        while readers:
            readable, writable, exceptional = select.select(
                readers, writers, errs, 1.0)
            for s in readable:
                if s is self.server:
                    connection, client_address = s.accept()
                    connection.setblocking(0)
                    readers.append(connection)
                else:
                    try:
                        data = s.recv(8192)
                        if data:
                            response = self._process_data(data)
                            response_bytes = json.dumps(response).encode('utf-8')
                            s.sendall(response_bytes)
                        readers.remove(s)
                        s.close()
                    except Exception as e:
                        logger.warning('Error handling connection: {}'.format(e))
                        readers.remove(s)
                        s.close()


def daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = open(os.devnull, 'r')
    os.dup2(devnull.fileno(), sys.stdin.fileno())


if __name__ == '__main__':
    daemon = '--daemon' in sys.argv

    try:
        from indy_common.config_util import getConfig
        config = getConfig()
    except Exception:
        config = None

    if daemon:
        daemonize()

    tool = NodeControlTool(config=config)
    tool.start()
