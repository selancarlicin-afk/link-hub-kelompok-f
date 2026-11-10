# =====================================================================
#  Jenkins siap pakai untuk CI/CD Resource Link Hub
#  - Jenkins LTS + Docker CLI + Docker Compose plugin + Python 3
#  - Plugin terpasang otomatis, setup wizard dilewati
#  - Konfigurasi (admin, credential PAT, job pipeline) via JCasC
# =====================================================================
FROM jenkins/jenkins:lts-jdk17

USER root

# Docker CLI + Compose plugin (daemon memakai milik host lewat docker.sock)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg python3 \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# Plugin Jenkins
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Konfigurasi otomatis (Jenkins Configuration as Code)
COPY casc/ /var/jenkins_casc/
ENV CASC_JENKINS_CONFIG=/var/jenkins_casc/jenkins.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false"

# Catatan: kontainer dijalankan sebagai root (lihat docker-compose.yml) agar
# bisa mengakses /var/run/docker.sock di Docker Desktop. Cukup untuk lab/tugas,
# jangan dipakai begini di production.
