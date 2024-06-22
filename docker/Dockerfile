# syntax=docker/dockerfile:latest

################################################################################
# el3xir-runner
################################################################################
FROM ubuntu:22.04 as el3xir

ENV DEBIAN_FRONTEND=noninteractive

# Enable APT package caching
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt update && apt install -y --no-install-recommends \
      vim \
      bc \
      libncurses-dev \
      git \
      gcc \
      g++ \
      g++-aarch64-linux-gnu \
      clang-format \
      openssh-client \
      make \
      unzip \
      wget \
      libblkid-dev \
      python2 \
      tar \
      curl \
      virtualenv \
      python-is-python3 \
      python3-dev \
      python-setuptools \
      python3-poetry \
      cmake \
      gdb-multiarch \
      ninja-build \
      pkg-config \
      libglib2.0-dev \
      meson \
      libpixman-1-dev \
      python3.10-venv \
      tzdata \
      qemu-utils

# install rehosting-framework
RUN --mount=type=bind,source=./src,target=/src,rw \
   --mount=type=bind,source=./.git,target=/.git,ro \
   cd /src/rehosting-framework && poetry install

# install avatar2 cfg file
WORKDIR /root/
RUN mkdir .avatar2
COPY ./docker/settings.cfg /root/.avatar2/

# build afl-fuzz, afl-showmap, afl-qemu-system-trace, and qemu-afl binaries
# install these binaries to the image
RUN --mount=type=bind,source=./src,target=/src,rw \
   --mount=type=bind,source=./.git,target=/.git,rw \
   cd /src/aflvatarplusplus && \
   chown -R root:root ./ && \
   make afl-fuzz afl-showmap && \
   cd /src/aflvatarplusplus/utils/qemu_persistent_hook && \
   make && \
   cd /src/aflvatarplusplus/qemu_mode && \
   ./build_qemu_support.sh && \
   cd /src/aflvatarplusplus && \
   make install && \
   cd /src/aflvatarplusplus/qemu_mode/qemuafl/build && \
   make install && \
   cd /src/aflvatarplusplus && \
   install -m 755 afl-qemu-system-trace /usr/local/bin/afl-qemu-system-trace

# install dependencies of plotting scripts
RUN --mount=type=bind,source=./src,target=/src,rw \
   --mount=type=bind,source=./.git,target=/.git,rw \
    cd /src/plotting && pip install -r requirements.txt

WORKDIR /src/


################################################################################
# el3xir-synthesis
################################################################################
FROM ubuntu:22.04 as el3xir_synthesis

ENV DEBIAN_FRONTEND=noninteractive

# Enable APT package caching
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
    
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt update && apt install -y --no-install-recommends \
      vim \
      bc \
      libncurses-dev \
      git \
      gcc \
      g++ \
      g++-aarch64-linux-gnu \
      clang-format \
      openssh-client \
      make \
      xz-utils \
      unzip \
      wget \
      libblkid-dev \
      python2 \
      tar \
      zip \
      curl \
      gdb \
      tcl \
      virtualenv \
      python-is-python3 \
      python3-dev \
      python-setuptools \
      python3-poetry \
      cmake \
      python3.10-venv \
      zlib1g-dev \
      build-essential \
      libssl-dev \
      libpcre2-dev \
      pip \
      flex \
      bison \
      file
      
WORKDIR /root/

# install GCC toolchains and WLLVM
# AARCH64
RUN wget https://developer.arm.com/-/media/Files/downloads/gnu-a/10.3-2021.07/binrel/gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu.tar.xz

RUN tar -xvf gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu.tar.xz

ENV PATH=/root/gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu/bin:$PATH

# ARM
RUN wget https://developer.arm.com/-/media/Files/downloads/gnu-a/10.3-2021.07/binrel/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf.tar.xz

RUN tar -xvf gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf.tar.xz

ENV PATH=/root/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin:$PATH

# WLLVM
RUN git clone https://github.com/travitch/whole-program-llvm.git

WORKDIR /root/whole-program-llvm/

RUN git checkout bc3875d59bab1a139416b8a8647dd897d185ee22

RUN pip install -e .

ENV PATH=/src/svf/Release-build/bin:$PATH

WORKDIR /src/svf
