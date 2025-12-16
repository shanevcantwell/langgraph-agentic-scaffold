# proxy/Dockerfile
# Local squid proxy build - no Docker Hub credentials required

FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends squid && \
    rm -rf /var/lib/apt/lists/*

# Squid config will be mounted at runtime
EXPOSE 3128

CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
