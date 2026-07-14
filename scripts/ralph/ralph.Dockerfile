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

# Copy only the dependency manifest first, and stub in an empty src/ dir so
# setuptools' package discovery (see pyproject.toml's
# [tool.setuptools.packages.find]) has something to find. This keeps the pip
# install below cached across source-only edits — copying the whole repo
# before installing (the old order) invalidated every layer after it on ANY
# file change, forcing a full ~2GB PyTorch/sentence-transformers reinstall on
# every single Ralph run. The stub's actual content doesn't matter: at
# `docker run` time /workspace gets entirely overlaid by a bind mount of the
# real working tree (see scripts/ralph/ralph-docker.sh), so this COPY/install
# is purely to warm the image's dependency layer at build time.
COPY pyproject.toml .
RUN mkdir -p src && touch src/__init__.py

# Debian 12's system Python refuses plain `pip install` outside a venv
# (PEP 668, "externally managed environment") — --break-system-packages
# overrides that. Fine here since the container is disposable anyway.
RUN pip install --break-system-packages -e ".[dev]"

# Now bring in the real source. This only invalidates the cache from here
# down — the dependency install above stays cached as long as pyproject.toml
# itself doesn't change, instead of busting on every source edit.
COPY . .

ENTRYPOINT ["scripts/ralph/ralph.sh"]
