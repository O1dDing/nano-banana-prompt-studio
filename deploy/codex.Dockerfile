# 独立镜像，不向 Web 镜像或宿主日常 Codex 安装写任何文件。
FROM node:22-bookworm-slim AS cli
ARG CODEX_VERSION=0.155.1
RUN npm install --global @openai/codex@${CODEX_VERSION} && npm cache clean --force

FROM python:3.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CODEX_HOME=/var/lib/nano-codex HOME=/home/nano-codex \
    CODEX_WORK_DIR=/run/nano-codex CODEX_PROTOCOL_FILE=/app/codex-protocol.json \
    CODEX_BRIDGE_TOKEN_FILE=/run/secrets/codex-bridge-token \
    CODEX_WORKERS=4 CODEX_MAX_PENDING=32 CODEX_RESULT_TTL=120 \
    XDG_CACHE_HOME=/run/nano-codex/cache
WORKDIR /app
COPY --from=cli /usr/local/bin/node /usr/local/bin/node
COPY --from=cli /usr/local/lib/node_modules/ /usr/local/lib/node_modules/
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY tools/verify_codex_protocol.py /app/tools/verify_codex_protocol.py

# Bridge 使用普通安装而不是 editable 安装，避免运行时依赖源码 .pth/挂载状态。
# 构建阶段必须真实导入 Bridge；缺包时镜像构建直接失败，不允许进入部署阶段。
RUN test -f /app/src/nano_banana/codex_bridge/server.py \
    && test -f /app/src/nano_banana/codex_bridge/runtime.py \
    && pip install --no-cache-dir . \
    && python -c "import nano_banana.codex_bridge.server as s; import nano_banana.codex_bridge.runtime as r; print('Codex bridge import OK:', s.__name__, r.__name__)" \
    && python /app/tools/verify_codex_protocol.py \
    && groupadd --gid 10001 nano-codex \
    && useradd --uid 10001 --gid 10001 --create-home nano-codex \
    && mkdir -p /var/lib/nano-codex /run/nano-codex \
    && chown 10001:10001 /var/lib/nano-codex /run/nano-codex

USER 10001:10001
EXPOSE 8787
CMD ["python", "-m", "nano_banana.codex_bridge.server"]
