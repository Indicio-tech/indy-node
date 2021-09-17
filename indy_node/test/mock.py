import json
from random import randint

from indy_common.constants import GET_NYM, NYM


def build_nym_request(identifier, dest, verkey, diddoc_content, role):

    request = {
        "identifier": identifier,
        "reqId": randint(100, 1000000),
        "protocolVersion": 2
    }

    operation = {
        "dest": dest,
        "type": NYM
    }

    if verkey:
        operation["verkey"] = verkey
    if diddoc_content:
        operation["diddoc_content"] = diddoc_content
    if role:
        operation["role"] = role

    request["operation"] = operation
    return json.dumps(request)


def build_get_nym_request(
    identifier, dest, timestamp
):
    request = {
        "identifier": identifier,
        "reqId": randint(100, 1000000),
        "protocolVersion": 2
    }

    operation = {
        "dest": dest,
        "type": GET_NYM
    }

    if timestamp:
        operation["timestamp"] = timestamp

    request["operation"] = operation
    return json.dumps(request)
