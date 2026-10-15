FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb


WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Sanctioned python:*-slim-bookworm base (Debian bookworm under the hood; ships
# python3 + pip). gprolog is the agent's runtime; the wrapper consults
# /app/src/stratdl.pl and calls run/2. tmux/asciinema/util-linux are required by
# the terminus-2 harness. pytest is baked here because allow_internet=false at
# run time. Acquire::Retries survives transient apt mirror blips on a fresh build.
RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y -o Acquire::Retries=5 --no-install-recommends \
        gprolog \
        tmux \
        asciinema \
        util-linux \
        bash \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY app/ /app/

RUN chmod +x /app/stratdl

# Verify the gprolog toolchain is functional.
RUN command -v gprolog >/dev/null && \
    echo ':- halt.' > /tmp/sanity.pl && \
    gprolog --consult-file /tmp/sanity.pl 2>&1 | tail -1 && \
    rm /tmp/sanity.pl

ENV PATH="/app:/usr/local/bin:/usr/bin:/bin"

CMD ["bash"]
