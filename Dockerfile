# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ARG OFFLINE=0
ARG INSTALL_AGENTX=0
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY ucm_accept ./ucm_accept
COPY wheelhouse ./wheelhouse

RUN if [ "${OFFLINE}" = "1" ]; then \
      pip install --no-index --find-links=/build/wheelhouse /build "evalscope[perf,service]>=1.15,<2"; \
      if [ "${INSTALL_AGENTX}" = "1" ]; then \
        pip install --no-index --find-links=/build/wheelhouse "evalscope[agentx]>=1.15,<2"; \
      fi; \
    else \
      pip install /build "evalscope[perf,service]>=1.15,<2"; \
      if [ "${INSTALL_AGENTX}" = "1" ]; then \
        pip install "evalscope[agentx]>=1.15,<2"; \
      fi; \
    fi

FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}" \
    EVALSCOPE_CACHE=/opt/ucm-accept/assets/evalscope-cache \
    MODELSCOPE_CACHE=/opt/ucm-accept/assets/modelscope-cache \
    UCM_CONFIG=/etc/ucm-accept/config.yaml \
    UCM_OUTPUTS=/data/outputs \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --home-dir /data --shell /bin/bash ucm \
    && mkdir -p /opt/ucm-accept /etc/ucm-accept /data/outputs \
    && chown -R ucm:ucm /data

COPY --from=builder /opt/venv /opt/venv
COPY assets/ /opt/ucm-accept/assets/
COPY packaging/config.offline.yaml /etc/ucm-accept/config.yaml
COPY packaging/entrypoint.sh /usr/local/bin/ucm-accept-entrypoint
RUN chmod +x /usr/local/bin/ucm-accept-entrypoint \
    && chown -R ucm:ucm /opt/ucm-accept

USER ucm
WORKDIR /data
VOLUME ["/data"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ucm-accept-entrypoint"]
