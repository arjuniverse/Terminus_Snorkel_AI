FROM python:3.11.15-trixie@sha256:58a54fbf1d5320af4f6761f9c6721329320a46ea086b5504640f19d1b7467d6a

# Install or copy over any environment dependencies here.

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*   

RUN pip install pytest==8.1.1   

RUN mkdir -p /app