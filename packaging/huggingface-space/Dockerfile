# syntax=docker/dockerfile:1

FROM python:3.13-slim AS seed

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/ra2
COPY app/*.whl /tmp/ra2exp/
RUN python -m pip install /tmp/ra2exp/*.whl && rm -rf /tmp/ra2exp
COPY resources/default.ra2pack /tmp/default.ra2pack
RUN RA2_EXPLORER_DATA_DIR=/opt/ra2/runtime \
    ra2exp resource-pack import /tmp/default.ra2pack \
    && rm /tmp/default.ra2pack \
    && rm -rf /opt/ra2/runtime/RA2MD-Ext/imports \
    && rm -rf /opt/ra2/runtime/RA2MD-Ext/packages

FROM python:3.13-slim AS runtime

ENV HF_ENDPOINT=https://hf-mirror.com \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RA2_EXPLORER_DATA_DIR=/opt/ra2/runtime \
    RA2_EXPLORER_DERIVED_DIR=/opt/ra2/runtime/RA2MD-Ext \
    RA2_EXPLORER_FRONTEND_DIR=/opt/ra2/frontend \
    RA2_EXPLORER_HOSTED=1

WORKDIR /opt/ra2
COPY app/*.whl /tmp/ra2exp/
RUN python -m pip install /tmp/ra2exp/*.whl \
    && rm -rf /tmp/ra2exp \
    && groupadd --system ra2exp \
    && useradd --system --gid ra2exp --home-dir /opt/ra2 ra2exp
COPY --chown=ra2exp:ra2exp frontend/ /opt/ra2/frontend/
COPY --chown=ra2exp:ra2exp config/update-channel.json /opt/ra2/update-channel.json
COPY --from=seed --chown=ra2exp:ra2exp /opt/ra2/runtime /opt/ra2/runtime

USER ra2exp
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)"
CMD ["ra2exp", "serve", "--host", "0.0.0.0", "--port", "7860"]
