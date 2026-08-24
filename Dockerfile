ARG BASE_IMAGE=indy-node-base:latest
FROM ${BASE_IMAGE}

RUN groupadd -r indy --gid 1000 && useradd -r -g indy --uid 1000 -m indy

WORKDIR /app
COPY . .

RUN mkdir -p /var/lib/indy /etc/indy /var/log/indy && \
    pip3 install --no-deps . && \
    pip3 install --no-deps .[tests] && \
    chown -R indy:indy /app /var/lib/indy /etc/indy /var/log/indy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER indy

ENTRYPOINT ["/entrypoint.sh"]
