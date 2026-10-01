# ==============================================================================
# AeroHarness: Automated Cyber Reasoning System for Embedded Firmware Fuzzing
# Dockerfile for One-Command Reproducibility and Artifact Evaluation
# ==============================================================================

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system toolchains: Clang-16, LLVM, AFL++, Python 3.10+, Bear, Git
RUN apt-get update && apt-get install -y \
    clang-16 \
    clang-tools-16 \
    llvm-16 \
    libclang-dev \
    afl++ \
    cmake \
    make \
    git \
    python3 \
    python3-pip \
    python3-venv \
    bear \
    && rm -rf /var/lib/apt/lists/*

# Configure default clang alternatives
RUN update-alternatives --install /usr/bin/clang clang /usr/bin/clang-16 100 \
    && update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-16 100

WORKDIR /workspace/aeroharness

# Copy dependency definition and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy complete project code
COPY . .

# Run validation tests on build
RUN python3 -m pytest tests/ -v

ENTRYPOINT ["python3", "run.py"]
CMD ["--help"]
