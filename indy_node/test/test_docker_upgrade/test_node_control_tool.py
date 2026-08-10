import json
import os
import socket
import tempfile
import time

import pytest

from indy_node.utils.node_control_tool import NodeControlTool


class FakeConfig:
    controlServiceHost = '127.0.0.1'
    controlServicePort = '0'
    NETWORK_NAME = 'sandbox'
    LEDGER_DIR = '/tmp'


def _make_tool(tmpdir, env_overrides=None, client_port=0):
    old_env = {}
    if env_overrides:
        for k, v in env_overrides.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = str(v)

    config = FakeConfig()
    config.LEDGER_DIR = tmpdir
    tool = NodeControlTool(config=config)
    tool.client_port = client_port

    if env_overrides:
        for k in old_env:
            if old_env[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_env[k]

    return tool


def _send_command(tool, command):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((tool.host, tool.port))
    s.sendall(json.dumps(command).encode('utf-8'))
    response = s.recv(4096)
    s.close()
    return json.loads(response.decode('utf-8'))


def test_health_returns_ok_when_everything_healthy(tmpdir):
    node_dir = os.path.join(str(tmpdir), 'sandbox', 'data', 'Node1')
    os.makedirs(node_dir)
    node_info = {'name': 'Node1', 'portN': 9701, 'portC': 9702}
    with open(os.path.join(node_dir, 'node_info'), 'w') as f:
        json.dump(node_info, f)

    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)
    tool.client_port = 0

    response = _send_command(tool, {'command': 'health'})
    assert response['status'] == 'ok'
    assert response['checks']['control_tool'] == 'ok'
    assert response['checks']['node_info'] == 'ok'
    assert response['node_name'] == 'Node1'
    tool.server.close()


def test_health_returns_degraded_when_node_info_missing(tmpdir):
    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)
    tool.client_port = 0

    response = _send_command(tool, {'command': 'health'})
    assert response['status'] == 'degraded'
    assert response['checks']['node_info'] == 'missing'
    tool.server.close()


def test_health_returns_degraded_when_node_info_stale(tmpdir):
    node_dir = os.path.join(str(tmpdir), 'sandbox', 'data', 'Node1')
    os.makedirs(node_dir)
    node_info_path = os.path.join(node_dir, 'node_info')
    with open(node_info_path, 'w') as f:
        json.dump({'name': 'Node1'}, f)

    old_time = time.time() - 600
    os.utime(node_info_path, (old_time, old_time))

    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)
    tool.client_port = 0

    response = _send_command(tool, {'command': 'health'})
    assert response['status'] == 'degraded'
    assert response['checks']['node_info'] == 'stale'
    tool.server.close()


def test_health_returns_unhealthy_when_zmq_port_unreachable(tmpdir):
    node_dir = os.path.join(str(tmpdir), 'sandbox', 'data', 'Node1')
    os.makedirs(node_dir)
    with open(os.path.join(node_dir, 'node_info'), 'w') as f:
        json.dump({'name': 'Node1'}, f)

    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '19999', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=19999)

    response = _send_command(tool, {'command': 'health'})
    assert response['status'] == 'unhealthy'
    assert response['checks']['zmq_client_port'] == 'unhealthy'
    tool.server.close()


def test_restart_returns_ok(tmpdir):
    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)

    original_kill = os.kill
    kill_calls = []

    def fake_kill(pid, sig):
        kill_calls.append((pid, sig))

    os.kill = fake_kill
    try:
        response = _send_command(tool, {'command': 'restart'})
        assert response['status'] == 'ok'
        assert len(kill_calls) == 1
        assert kill_calls[0] == (1, 15)
    finally:
        os.kill = original_kill
        tool.server.close()


def test_unknown_command_returns_error(tmpdir):
    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)

    response = _send_command(tool, {'command': 'bogus'})
    assert response['status'] == 'error'
    assert 'unknown command' in response['message']
    tool.server.close()


def test_health_accepts_message_type_key(tmpdir):
    env = {'NODE_NAME': 'Node1', 'CLIENT_PORT': '0', 'NODE_PORT': '9701'}
    tool = _make_tool(str(tmpdir), env_overrides=env, client_port=0)

    response = _send_command(tool, {'message_type': 'health'})
    assert response['status'] == 'ok'
    tool.server.close()
