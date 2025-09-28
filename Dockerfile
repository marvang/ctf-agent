# Use Kali Linux base image
FROM kalilinux/kali-rolling

# Set working directory
WORKDIR /app

# Environment
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Ensure CA certs, set official HTTPS mirror, then install
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    printf 'deb https://kali.download/kali kali-rolling main non-free contrib\n' > /etc/apt/sources.list && \
    apt-get update --allow-releaseinfo-change && \
    apt-get -y --fix-missing full-upgrade && \
    apt-get install -y --no-install-recommends \
        # kali-linux-headless \
        kali-linux-default \
        # kali-linux-large \
        python3 \
        python3-pip \
        iputils-ping \
        nmap \
        net-tools \
        libcap2-bin \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Default command
CMD ["/bin/bash"]
