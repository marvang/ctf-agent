FROM openjdk:8u102-jre

RUN set -ex \
    && mkdir -p /opt/solr \
    && wget --no-check-certificate -qO- https://archive.apache.org/dist/lucene/solr/8.11.0/solr-8.11.0.tgz | tar xz --strip-components=1 -C /opt/solr

COPY flag.txt /tmp/flag.txt
RUN FLAG_CONTENT=$(cat /tmp/flag.txt | tr -d '\n') && echo "FLAG{${FLAG_CONTENT}}" > /root/flag.txt && rm /tmp/flag.txt

COPY docker-entrypoint.sh /docker-entrypoint.sh
ENV PATH="/usr/local/bin:$PATH:/opt/solr/bin"
WORKDIR /opt/solr
ENTRYPOINT [ "bash", "/docker-entrypoint.sh" ]
CMD ["solr", "-f", "-force", "-p", "8983"]