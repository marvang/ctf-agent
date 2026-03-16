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
        kali-linux-headless \
        python3 \
        python3-pip \
        sshpass \
        iputils-ping \
        nmap \
        net-tools \
        libcap2-bin \
        openvpn \
        iproute2 \
        iptables \
        seclists \
        wordlists \
        sqlmap \
        gobuster \
        nikto \
        ffuf \
        wfuzz \
        dirb \
        wpscan \
        crackmapexec \
        evil-winrm \
        impacket-scripts \
        responder \
        feroxbuster \
        nuclei \
        masscan \
        tshark \
        exploitdb \
        netcat-traditional \
        chisel \
        proxychains4 \
        sslscan \
        sslyze \
        testssl.sh \
        dnsenum \
        dnsrecon \
        sublist3r \
        amass \
        fierce \
        whatweb \
        wafw00f \
        commix \
        linux-exploit-suggester \
        webshells \
        bloodhound.py \
        mitmproxy \
        john \
        hashcat \
        hydra \
        smbmap \
        enum4linux-ng \
        subfinder \
        # --- additions for broader coverage (copy-paste block) ---
        aircrack-ng \
        lynis \
        theharvester \
        tcpdump \
        gdb \
        gdb-multiarch \
        radare2 \
        python3-ropgadget \
        checksec \
        binwalk \
        metasploit-framework \
        ettercap-text-only \
        reaver \
        iw \
        wireless-tools \
        python3-pwntools \
        python3-dev \
        libssl-dev \
        libffi-dev \
        build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# Default command
CMD ["/bin/bash"]