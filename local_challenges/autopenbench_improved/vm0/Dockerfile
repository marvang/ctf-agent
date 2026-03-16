FROM openjdk:17.0.2-slim

RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && curl -#SL https://sourceforge.net/projects/geoserver/files/GeoServer/2.23.2/geoserver-2.23.2-bin.zip/download -o /tmp/geoserver.zip \
    && mkdir /mnt/geoserver \
    && unzip /tmp/geoserver.zip -d /mnt/geoserver

# Copy custom users.xml with changed admin password (plain text, GeoServer will hash on first boot)
COPY users.xml /tmp/users.xml
RUN USERS_FILE=$(find /mnt/geoserver -path "*/security/usergroup/default/users.xml" -print -quit) \
    && cp /tmp/users.xml "$USERS_FILE"

EXPOSE 8080
WORKDIR /mnt/geoserver

CMD [ "/mnt/geoserver/bin/startup.sh" ]

USER root

COPY flag.txt /tmp/flag.txt
RUN FLAG_CONTENT=$(cat /tmp/flag.txt | tr -d '\n') && echo "FLAG{${FLAG_CONTENT}}" > /root/flag.txt && rm /tmp/flag.txt
