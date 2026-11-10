// =====================================================================
//  Jenkinsfile - Resource Link Hub (Kelompok F)
//  Dipicu otomatis oleh GitHub Webhook setiap git push ke branch main.
//
//  Stage: Checkout -> Syntax Check -> Build Image -> Automated Deployment -> Health Check
//
//  Prasyarat agent Jenkins: Docker CLI + Docker Compose plugin dan akses ke
//  Docker daemon (/var/run/docker.sock). Lihat folder jenkins/ untuk image
//  Jenkins yang sudah siap pakai.
// =====================================================================
pipeline {
    agent any

    triggers {
        // Aktifkan "GitHub hook trigger for GITScm polling"
        githubPush()
    }

    options {
        disableConcurrentBuilds()
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    environment {
        COMPOSE_PROJECT_NAME = 'linkhub'
        IMAGE_NAME           = 'linkhub-backend'
        IMAGE_TAG            = "${env.BUILD_NUMBER}"
        BACKEND_CONTAINER    = 'linkhub-backend'
        FRONTEND_CONTAINER   = 'linkhub-frontend'
    }

    stages {

        // -------------------------------------------------------------
        stage('Checkout') {
            steps {
                // Memakai repo + credential (GitHub PAT, id: github-pat)
                // yang dikonfigurasi pada job "Pipeline script from SCM".
                checkout scm
                sh '''
                    echo "Commit terbaru:"
                    git log -1 --pretty=format:'  %h | %an | %s%n'
                    ls -la
                '''
            }
        }

        // -------------------------------------------------------------
        stage('Syntax Check') {
            steps {
                sh '''
                    set -e
                    echo "==> [1/4] Cek file wajib"
                    for f in backend/app.py backend/Dockerfile frontend/index.html nginx/default.conf docker-compose.yml Jenkinsfile; do
                        test -f "$f" || { echo "File wajib hilang: $f"; exit 1; }
                        echo "  OK  $f"
                    done

                    echo "==> [2/4] Python syntax check (backend/app.py)"
                    if command -v python3 >/dev/null 2>&1; then
                        python3 -m py_compile backend/app.py
                    else
                        docker run --rm -i python:3.12-slim \
                          python -c "import ast,sys; ast.parse(sys.stdin.read(), 'app.py')" < backend/app.py
                    fi
                    echo "  OK  app.py valid"

                    echo "==> [3/4] Validasi docker-compose.yml"
                    docker compose config --quiet
                    echo "  OK  docker-compose.yml valid"

                    echo "==> [4/4] Cek frontend memakai fetch() ke API"
                    grep -q "fetch(" frontend/index.html
                    echo "  OK  index.html memakai fetch()"
                '''
            }
        }

        // -------------------------------------------------------------
        stage('Build Image') {
            steps {
                sh '''
                    set -e
                    docker build \
                      --label "org.opencontainers.image.revision=$(git rev-parse --short HEAD)" \
                      --label "jenkins.build=${BUILD_NUMBER}" \
                      -t ${IMAGE_NAME}:${IMAGE_TAG} \
                      -t ${IMAGE_NAME}:latest \
                      backend
                    docker image ls ${IMAGE_NAME}
                '''
            }
        }

        // -------------------------------------------------------------
        stage('Automated Deployment') {
            steps {
                sh '''
                    set -e

                    # --- Tentukan path HOST untuk bind mount frontend -----------------
                    # Jika Jenkins berjalan di dalam kontainer (Docker Desktop / DooD),
                    # path workspace ($WORKSPACE) hanya ada di dalam kontainer Jenkins.
                    # Docker daemon butuh path di sisi host, jadi kita terjemahkan
                    # JENKINS_HOME -> sumber mount-nya di host.
                    HOST_PROJECT_DIR="$WORKSPACE"
                    if [ -f /.dockerenv ]; then
                        SELF_ID="$(hostname)"
                        HOST_JENKINS_HOME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "'"$JENKINS_HOME"'"}}{{.Source}}{{end}}{{end}}' "$SELF_ID" 2>/dev/null || true)"
                        if [ -n "$HOST_JENKINS_HOME" ]; then
                            HOST_PROJECT_DIR="$(echo "$WORKSPACE" | sed "s#^$JENKINS_HOME#$HOST_JENKINS_HOME#")"
                        fi
                    fi
                    export HOST_PROJECT_DIR
                    echo "Bind mount frontend dari host: $HOST_PROJECT_DIR/frontend"

                    # --- Stop & hapus kontainer lama ----------------------------------
                    # PENTING: tanpa flag -v  -> Named Volume link-hub-data TIDAK dihapus
                    docker compose down --remove-orphans || true
                    docker rm -f ${BACKEND_CONTAINER} ${FRONTEND_CONTAINER} 2>/dev/null || true

                    # --- Jalankan kontainer baru dengan image hasil build -------------
                    docker compose up -d --no-build

                    docker compose ps
                    echo "Named volume:"
                    docker volume inspect link-hub-data --format '  {{.Name}} -> {{.Mountpoint}}'
                    echo "Network:"
                    docker network inspect app-net --format '  {{.Name}} ({{.Driver}}) containers: {{range .Containers}}{{.Name}} {{end}}'
                '''
            }
        }

        // -------------------------------------------------------------
        stage('Health Check') {
            steps {
                sh '''
                    set -e
                    echo "==> Menunggu backend sehat..."
                    ok=0
                    for i in $(seq 1 20); do
                        # Dijalankan dari dalam kontainer frontend -> membuktikan DNS service name di app-net
                        if docker exec ${FRONTEND_CONTAINER} wget -qO- http://backend:8000/health > /tmp/health.json 2>/dev/null; then
                            ok=1; break
                        fi
                        echo "  percobaan $i/20 belum siap, tunggu 3 detik..."
                        sleep 3
                    done
                    [ "$ok" = "1" ] || { echo "Backend tidak sehat!"; exit 1; }
                    echo "  Backend  : $(cat /tmp/health.json | tr -d '\\n' | tr -s ' ')"

                    echo "==> Cek API lewat reverse proxy Nginx (/api/links)"
                    docker exec ${FRONTEND_CONTAINER} wget -qO- http://127.0.0.1/api/links | head -c 300; echo

                    echo "==> Cek UI (bind mount index.html tersaji)"
                    if ! docker exec ${FRONTEND_CONTAINER} wget -qO- http://127.0.0.1/ | grep -q "Resource Link Hub"; then
                        echo "index.html tidak tersaji - periksa bind mount HOST_PROJECT_DIR."
                        exit 1
                    fi
                    echo "  Frontend : OK"

                    echo "==> Versi yang berjalan"
                    docker inspect ${BACKEND_CONTAINER} --format '  image={{.Config.Image}} status={{.State.Health.Status}}'
                '''
            }
        }
    }

    post {
        success {
            echo "DEPLOY SUKSES - build #${env.BUILD_NUMBER}. UI: http://localhost:8081  |  API: http://localhost:8000/links"
        }
        failure {
            echo 'DEPLOY GAGAL - menampilkan log kontainer untuk debugging:'
            sh 'docker compose logs --tail=60 || true'
        }
        always {
            // Bersihkan image menggantung (dangling) dan sisakan 3 tag build terakhir
            sh '''
                docker image prune -f >/dev/null 2>&1 || true
                docker image ls ${IMAGE_NAME} --format '{{.Tag}}' \
                  | grep -E '^[0-9]+$' | sort -rn | tail -n +4 \
                  | xargs -r -I{} docker rmi ${IMAGE_NAME}:{} >/dev/null 2>&1 || true
            '''
        }
    }
}
