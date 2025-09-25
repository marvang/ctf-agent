# Use Kali Linux base image
FROM kalilinux/kali-rolling

# Set working directory
WORKDIR /app

# Environment settings
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Update and install a Kali metapackage (ignore failures, keep going)
RUN apt-get update && \
    apt-get -y --fix-missing full-upgrade || true && \
    apt-get install -y --no-install-recommends \
        kali-linux-headless \
        # kali-linux-default \
        # kali-linux-large \
    || true && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Default command: drop into shell
CMD ["/bin/bash"]
