from indy_common.constants import GET_NYM, TIMESTAMP, VALUE

from common.serializers.serialization import domain_state_serializer
from indy_common.constants import GET_NYM, TIMESTAMP
from indy_node.server.request_handlers.domain_req_handlers.nym_handler import NymHandler
from indy_node.server.request_handlers.utils import StateValue
from plenum.common.constants import TARGET_NYM, TXN_TIME, DOMAIN_LEDGER_ID, TXN_METADATA_SEQ_NO
from plenum.common.request import Request
from plenum.common.types import f
from plenum.common.txn_util import get_txn_time
from plenum.server.database_manager import DatabaseManager
from plenum.server.request_handlers.handler_interfaces.read_request_handler import (
    ReadRequestHandler,
)


class GetNymHandler(ReadRequestHandler):
    def __init__(self, node, database_manager: DatabaseManager):
        super().__init__(database_manager, GET_NYM, DOMAIN_LEDGER_ID)
        self.node = node

    def get_result(self, request: Request):
        # Needs validation that timestamp and seqNo are not set together
        self._validate_request_type(request)
        nym = request.operation[TARGET_NYM]
        timestamp = request.operation.get(TIMESTAMP, None)
        path = NymHandler.make_state_path_for_nym(nym)
        # Get old state based on seqNo (versionId) or timestamp.
        # See https://hyperledger.github.io/indy-did-method/#did-versions
        past_root = None
        timestamp = request.operation.get(TIMESTAMP, None)
        read_seq_no = request.operation.get("seqNo", None)

        if read_seq_no:
            db = self.database_manager.get_database(DOMAIN_LEDGER_ID)
            txn = self.node.getReplyFromLedger(db.ledger, read_seq_no, write=False)
            if txn and "result" in txn:
                timestamp_retrieved_from_seqNo = get_txn_time(txn.result)
                past_root = self.database_manager.ts_store.get_equal_or_prev(timestamp_retrieved_from_seqNo)
        elif timestamp:
            past_root = self.database_manager.ts_store.get_equal_or_prev(timestamp)
        else:
            return "No record found associated with this sequence number."

        nym_data, proof = self._get_value_from_state(path, head_hash=past_root, with_proof=True)
        if nym_data:
            nym_data = domain_state_serializer.deserialize(nym_data)
            nym_data[TARGET_NYM] = nym
            data = domain_state_serializer.serialize(nym_data)
            seq_no = nym_data[f.SEQ_NO.nm]
            update_time = nym_data[TXN_TIME]

        result = self.make_result(
            request=request,
            data=data,
            last_seq_no=seq_no,
            update_time=update_time,
            proof=proof,
        )

        result.update(request.operation)
        return result
