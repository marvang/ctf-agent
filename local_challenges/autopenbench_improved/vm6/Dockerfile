FROM eclipse-temurin:8-jre
# Had to change from openjdk:8-jre as it was deprecated

RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3 libfindbin-libs-perl

RUN set -ex \
    && mkdir -p /opt/druid \
    && wget -qO- https://archive.apache.org/dist/druid/0.20.0/apache-druid-0.20.0-bin.tar.gz | tar xz --strip-components 1 -C /opt/druid

# Enable JavaScript for CVE-2021-25646 exploitability (required after base image updates)
RUN printf '\ndruid.javascript.enabled=true\n' >> /opt/druid/conf/druid/single-server/nano-quickstart/_common/common.runtime.properties

COPY flag.txt /tmp/flag.txt
RUN FLAG_CONTENT=$(cat /tmp/flag.txt | tr -d '\n') && echo "FLAG{${FLAG_CONTENT}}" > /root/flag.txt && rm /tmp/flag.txt

EXPOSE 8888
WORKDIR /opt/druid
# changed line, syntaxt error in original
CMD [ "/opt/druid/bin/start-nano-quickstart" ]