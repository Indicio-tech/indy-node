ARG BASE_IMAGE=ghcr.io/hyperledger/indy-node-base:latest
FROM ${BASE_IMAGE}

RUN groupadd -r indy --gid 1000 && useradd -r -g indy --uid 1000 -m indy

WORKDIR /app
COPY . .

RUN mkdir -p /var/lib/indy /etc/indy /var/log/indy && \
    pip3 install .[tests] && \
    pip3 install "sortedcontainers>=2.1.0,<3" "rlp>=2.0.0,<3" && \
    sed -i 's/from collections import Iterable/from collections.abc import Iterable/' \
        /usr/local/lib/python3.10/dist-packages/plenum/persistence/req_id_to_txn.py \
        /usr/local/lib/python3.10/dist-packages/plenum/server/batch_handlers/audit_batch_handler.py && \
    chown -R indy:indy /app /var/lib/indy /etc/indy /var/log/indy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER indy

ENTRYPOINT ["/entrypoint.sh"]
