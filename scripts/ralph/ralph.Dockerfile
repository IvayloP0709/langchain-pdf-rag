# Sandbox image for scripts/ralph/ralph.sh — runs Claude Code headlessly and
# unsupervised, so this container exists to contain the blast radius of a
# bad autonomous iteration to a disposable filesystem instead of the host.
#
# Build:  docker build -f scripts/ralph/ralph.Dockerfile -t ralph-sandbox .
# Run:    see the docker run command in scripts/ralph/ralph-docker.sh.

FROM node:20-slim

# --- OS-level tools -----------------------------------------------------
# git: ralph-prompt.md commits inside the container.
# curl/gnupg/ca-certificates: needed to add GitHub's apt source for `gh`.
# python3/pip/venv: this is a Python project; tests and the code itself need it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    gnupg \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI -----------------------------------------------------------
# `gh` isn't in Debian's default repos, so pull it from GitHub's own apt source.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# --- Claude Code CLI --------------------------------------------------------
RUN npm install -g @anthropic-ai/claude-code

# --- Project setup ----------------------------------------------------------
WORKDIR /workspace

# Copy the whole repo in and install it. At `docker run` time this gets
# overlaid by a bind mount of your actual working tree (see
# scripts/ralph/ralph.sh), so this COPY is really just to make the image
# buildable/self-contained — the code Ralph actually edits is the mounted
# copy, not this one.
COPY . .

# Debian 12's system Python refuses plain `pip install` outside a venv
# (PEP 668, "externally managed environment") — --break-system-packages
# overrides that. Fine here since the container is disposable anyway.
RUN pip install --break-system-packages -e ".[dev]"

ENTRYPOINT ["scripts/ralph/ralph.sh"]
