ARG BASE_IMAGE=indy-node-base:latest
FROM ${BASE_IMAGE}

RUN groupadd -r indy --gid 1000 && useradd -r -g indy --uid 1000 -m indy

WORKDIR /app
COPY . .

RUN mkdir -p /var/lib/indy /etc/indy /var/log/indy && \
    pip3 install .[tests] && \
    pip3 install "sortedcontainers>=2.1.0,<3" "rlp>=2.0.0,<3" && \
    chown -R indy:indy /app /var/lib/indy /etc/indy /var/log/indy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER indy

ENTRYPOINT ["/entrypoint.sh"]
