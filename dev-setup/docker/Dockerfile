ARG ROCKSDB_VERSION=v6.25.3
# ARG USER_VERSION = 
#===========================================ursa===========================================
# TODO: use github version tag for ursa
FROM rust:latest as ursa-builder
WORKDIR /usr/src/
RUN git clone https://github.com/hyperledger/ursa.git 
WORKDIR /usr/src/ursa/libursa
RUN  cargo build --release

#===========================================indy===========================================
FROM python:3.8-slim-buster  as indy-ursa
COPY --from=ursa-builder /usr/src/ursa/libursa/target/release/libursa.so /usr/lib/
WORKDIR /home/
# TODO: use github version tag for libindy
FROM rust:latest as libindy-builder
# addopted from https://github.com/hyperledger/indy-sdk/blob/master/docs/build-guides/ubuntu-build.md
WORKDIR /usr/src/
RUN git clone https://github.com/hyperledger/indy-sdk.git && cd indy-sdk && git checkout f85afd2f94959eb59522e5dda160d2c7fdd1a4ba
WORKDIR /usr/src/indy-sdk/libindy
RUN apt-get update && apt-get install -y libsodium-dev libzmq3-dev
RUN  cargo build --release

#===========================================indy-node===========================================
FROM python:3.8-slim-buster as node-plenum
COPY --from=libindy-builder /usr/src/indy-sdk/libindy/target/release/libindy.so /usr/lib/
COPY --from=ursa-builder /usr/src/ursa/libursa/target/release/libursa.so /usr/lib/

# Install git and make
# Upgrade your gcc to version at least 4.7 to get C++11 support.
# Install gflags snappy zlib bzip2
RUN apt-get update && apt-get install -y git \
    make \
    build-essential \
    cmake \
    libgflags-dev \
    libsnappy-dev \
    zlib1g-dev \
    libbz2-dev

WORKDIR /home/
# Clone rocksdb #TODO: figure out if we need to clone a particular release
RUN git clone https://github.com/facebook/rocksdb.git 
WORKDIR /home/rocksdb
#https://github.com/twmht/python-rocksdb/issues/22#issuecomment-464369559
RUN make shared_lib
RUN make install-shared INSTALL_PATH=/usr


RUN apt-get update && apt-get install -y libsodium-dev libzmq3-dev liblz4-dev cython3
#RUN apt-get update && apt-get install -y software-properties-common
# TODO: use version tags for indy-node/plenum

WORKDIR /home
RUN git clone https://github.com/hyperledger/indy-node.git
RUN git clone https://github.com/hyperledger/indy-plenum.git
WORKDIR /home/indy-plenum/
RUN pip3 install -e .[tests]
WORKDIR /home/indy-node/
RUN pip3 install -e .[tests]
WORKDIR /home/indy-node/indy_node
# lie about container version name
#RUN sed -i 's/Debian/Debian Ubuntu/g' /etc/os-release
#RUN pytest .
#WORKDIR /home/indy-plenum/
#RUN pytest .
#===========================================indy-node===========================================

#RUN add-apt-repository "deb https://repo.sovrin.org/sdk/deb xenial master" \
#    && apt-get update && apt-get install -y \
#        libindy-crypto=0.4.5 \
#        libindy=1.13.0~1420 \
#        libsovtoken=1.0.2~92 \
#    && rm -rf /var/lib/apt/lists/*

#RUN mkdir -p /etc/indy && echo "ENABLED_PLUGINS = ['sovtoken', 'sovtokenfees']" > /etc/indy/indy_config.py \
#    && pip3 install -U pipenv zipp==1.2.0

# TODO workaround (suggested by http://click.pocoo.org/5/python3/)
# to use pipenv's dependency 'click' (http://click.pocoo.org)
# check for alternatives
#ENV LC_ALL=C.UTF-8
#ENV LANG=C.UTF-8

#RUN if [ "$u_id" != "0" ]; then \
#        useradd -ms /bin/bash -u $u_id $u_name; \
#    fi
#USER $u_id

# TODO CMD ENTRYPOINT ...
#ENV CI_ENV_VERSION=0.21.0