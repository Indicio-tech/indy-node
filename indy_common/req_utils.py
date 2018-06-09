from indy_common.constants import SCHEMA_NAME, SCHEMA_VERSION, SCHEMA_ATTR_NAMES, SCHEMA_FROM, \
    CLAIM_DEF_SIGNATURE_TYPE, CLAIM_DEF_SCHEMA_REF, CLAIM_DEF_TAG, CLAIM_DEF_PUBLIC_KEYS, CLAIM_DEF_FROM, \
    CLAIM_DEF_TAG_DEFAULT, CLAIM_DEF_CL

from plenum.common.constants import DATA
from plenum.common.request import Request
from plenum.common.txn_util import get_payload_data


# SCHEMA

def get_write_schema_name(req):
    return req.operation[DATA][SCHEMA_NAME]


def get_txn_schema_name(txn):
    return get_payload_data(txn)[DATA][SCHEMA_NAME]


def get_write_schema_version(req: Request):
    return req.operation[DATA][SCHEMA_VERSION]


def get_txn_schema_version(txn):
    return get_payload_data(txn)[DATA][SCHEMA_VERSION]


def get_write_schema_attr_names(req: Request):
    return req.operation[DATA][SCHEMA_ATTR_NAMES]


def get_txn_schema_attr_names(txn):
    return get_payload_data(txn)[DATA][SCHEMA_ATTR_NAMES]


def get_read_schema_name(req: Request):
    return req.operation[DATA][SCHEMA_NAME]


def get_read_schema_version(req: Request):
    return req.operation[DATA][SCHEMA_VERSION]


def get_read_schema_from(req: Request):
    return req.operation[SCHEMA_FROM]


# CLAIM DEF

def get_write_claim_def_signature_type(req: Request):
    return req.operation[CLAIM_DEF_SIGNATURE_TYPE]


def get_write_claim_def_schema_ref(req: Request):
    return req.operation[CLAIM_DEF_SCHEMA_REF]


def get_write_claim_def_tag(req: Request):
    return req.operation[CLAIM_DEF_TAG]


def get_write_claim_def_public_keys(req: Request):
    return req.operation[CLAIM_DEF_PUBLIC_KEYS]


def get_txn_claim_def_signature_type(txn):
    return get_payload_data(txn)[CLAIM_DEF_SIGNATURE_TYPE]


def get_txn_claim_def_schema_ref(txn):
    return get_payload_data(txn)[CLAIM_DEF_SCHEMA_REF]


def get_txn_claim_def_tag(txn):
    return get_payload_data(txn)[CLAIM_DEF_TAG]


def get_txn_claim_def_public_keys(txn):
    return get_payload_data(txn)[CLAIM_DEF_PUBLIC_KEYS]


def get_read_claim_def_signature_type(req: Request):
    return req.operation.get(CLAIM_DEF_SIGNATURE_TYPE, CLAIM_DEF_CL)


def get_read_claim_def_schema_ref(req: Request):
    return req.operation[CLAIM_DEF_SCHEMA_REF]


def get_read_claim_def_tag(req: Request):
    return req.operation.get(CLAIM_DEF_TAG, CLAIM_DEF_TAG_DEFAULT)


def get_read_claim_def_from(req: Request):
    return req.operation[CLAIM_DEF_FROM]
