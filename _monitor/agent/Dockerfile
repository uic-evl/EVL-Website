# EVL monitor agent. Built on each host by _monitor/ansible (no registry).
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/uic-evl/EVL-Website" \
      org.opencontainers.image.description="EVL server monitor agent"

# libnss-sss lets pwd.getpwuid ask the host's sssd (UIC AD accounts) through its socket
RUN apt-get update \
 && apt-get install -y --no-install-recommends libnss-sss \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && python -m compileall -q /usr/local/lib/python3.12/site-packages/evl_monitor

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin monitor \
 && mkdir -p /data /run/evl-monitor \
 && chown 10001:10001 /data /run/evl-monitor

# Last, after useradd: with "passwd: sss" only, the image's own accounts are invisible,
# so a host uid can never be named after an image account (host files come from /hostfs).
COPY nsswitch.conf /etc/nsswitch.conf

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 10001:10001
EXPOSE 9877
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-m", "evl_monitor.healthcheck"]
ENTRYPOINT ["python", "-m"]
CMD ["evl_monitor"]
