FROM eclipse-temurin:21-jdk-jammy@sha256:55fb9bf738f5d9b4a6c01b39337e3070d3e27370dd3c478fd1d5d3cd2233c6d8

RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        python3 \
        python3-pip \
        python3-setuptools \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir pytest==8.1.1 || pip3 install --no-cache-dir --break-system-packages pytest==8.1.1

WORKDIR /app

COPY app/ /app/

RUN mkdir -p /app/output && \
    javac -d /app/classes src/EventAggregator.java

CMD ["/bin/bash"]
