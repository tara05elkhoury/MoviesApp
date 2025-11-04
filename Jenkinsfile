pipeline {
  agent any

  triggers { pollSCM('H/2 * * * *') }

  environment {
    NS            = 'default'
    APP           = 'mydjangoapp'
    DEPLOY        = 'django-deployment'
    CTR           = 'django-container'
    DOCKER_CTX    = '.'
    MANIFEST_DIR  = '.'

    MK_ROOT       = '/var/jenkins_home/minikube/ps2'
    MINIKUBE_HOME = "${MK_ROOT}/.minikube"
    KUBECONFIG    = "${MK_ROOT}/.kube/config"

    MK_DOCKER_NET = 'minikube-net'
    MK_SUBNET     = '10.123.0.0/16'
    MINIKUBE_IN_A_CONTAINER = 'true'
  }

  options { timestamps() }

  stages {
    stage('Checkout') {
      steps {
        cleanWs()
        git branch: 'main', url: 'https://github.com/tara05elkhoury/MoviesApp'
      }
    }

    stage('Install CLIs (once)') {
      steps {
        sh '''
          set -euo pipefail
          if ! command -v minikube >/dev/null 2>&1; then
            curl -fsSL https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 -o /usr/local/bin/minikube
            chmod +x /usr/local/bin/minikube
          fi
          if ! command -v kubectl >/dev/null 2>&1; then
            KVER="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
            curl -fsSL "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl
            chmod +x /usr/local/bin/kubectl
          fi
          apt-get update -y
          apt-get install -y --no-install-recommends iproute2 socat curl ca-certificates
          mkdir -p "${MINIKUBE_HOME}" "$(dirname "${KUBECONFIG}")"
        '''
      }
    }

    stage('Prepare dedicated Docker network for Minikube') {
      steps {
        sh '''
          set -euo pipefail
          if ! docker network inspect "${MK_DOCKER_NET}" >/dev/null 2>&1; then
            docker network create --driver=bridge --subnet="${MK_SUBNET}" "${MK_DOCKER_NET}"
          fi

          JENKINS_ID="$(hostname)"
          if docker inspect "${JENKINS_ID}" >/dev/null 2>&1; then
            if ! docker network inspect "${MK_DOCKER_NET}" --format "{{range \\$id,\\$cfg := .Containers}}{{if eq \\$id \\"${JENKINS_ID}\\"}}attached{{end}}{{end}}" | grep -q attached; then
              echo "Attaching Jenkins container ${JENKINS_ID} to ${MK_DOCKER_NET} (alias: jenkins)"
              docker network connect --alias jenkins "${MK_DOCKER_NET}" "${JENKINS_ID}" || true
            fi
          else
            echo "WARN: Unable to inspect Jenkins container (${JENKINS_ID}); skipping network attach."
          fi
        '''
      }
    }

    stage('Start or Re-use Minikube (race-free bridge, POSIX)') {
      steps {
        sh '''
          set -euo pipefail
          export NO_PROXY="127.0.0.1,localhost,.local,.svc,cluster.local,10.96.0.0/12,10.244.0.0/16,10.123.0.0/16"
          export no_proxy="${NO_PROXY}"
          unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy || true

          # --- background bridge loop (POSIX) ---
          cat > /tmp/minikube_port_bridge.sh <<'EOSH'
#!/usr/bin/env sh
set -eu
parse_host_port() { awk -F':' '{print $NF}'; }
while :; do
  PORT_MAPS="$(docker port minikube 2>/dev/null || true)"
  if [ -n "${PORT_MAPS}" ]; then
    echo "${PORT_MAPS}" | while IFS= read -r line; do
      [ -z "${line}" ] && continue
      HOST_PORT="$(echo "${line}" | parse_host_port)"
      case "${HOST_PORT}" in ''|[!0-9]) continue;; esac
      if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${HOST_PORT}\$"; then
        nohup socat TCP-LISTEN:${HOST_PORT},fork,reuseaddr TCP:host.docker.internal:${HOST_PORT} >/dev/null 2>&1 &
        echo "[BRIDGE] Forwarding container localhost:${HOST_PORT} -> host.docker.internal:${HOST_PORT}"
      fi
    done
  fi
  sleep 1
done
EOSH
          chmod +x /tmp/minikube_port_bridge.sh
          nohup /tmp/minikube_port_bridge.sh >/tmp/port-bridge.log 2>&1 &
          sleep 1

          # --- reuse or start cluster ---
          if minikube status -p minikube | grep -q Running; then
            echo "Reusing existing, running Minikube cluster."
            minikube -p minikube update-context
          else
            echo "Starting Minikube…"
            if ! minikube start -p minikube \
              --driver=docker \
              --container-runtime=containerd \
              --kubernetes-version=v1.30.0 \
              --cpus=2 --memory=4096 \
              --network="${MK_DOCKER_NET}" \
              --wait=all \
              --force \
              -v=3 --alsologtostderr; then
              echo "Start failed; deleting profile then retrying…"
              minikube delete -p minikube || true
              minikube start -p minikube \
                --driver=docker \
                --container-runtime=containerd \
                --kubernetes-version=v1.30.0 \
                --cpus=2 --memory=4096 \
                --network="${MK_DOCKER_NET}" \
                --wait=all \
                --force \
                -v=3 --alsologtostderr
            fi
          fi

          # --- explicit apiserver bridge + POSIX wait using socat as probe ---
          API_HOST_PORT="$(docker port minikube 8443/tcp | awk -F':' '{print $NF}' | tail -n1 || true)"
          case "${API_HOST_PORT}" in
            ''|[!0-9])
              echo "[APISERVER] Could not determine host port from 'docker port minikube 8443/tcp'"
              docker port minikube || true
              ;;
            *)
              echo "[APISERVER] Host port is ${API_HOST_PORT}"
              if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${API_HOST_PORT}\$"; then
                nohup socat TCP-LISTEN:${API_HOST_PORT},fork,reuseaddr TCP:host.docker.internal:${API_HOST_PORT} >/dev/null 2>&1 &
                echo "[APISERVER] Dedicated forward started on :${API_HOST_PORT}"
              fi

              printf "[APISERVER] Waiting for localhost:%s " "${API_HOST_PORT}"
              i=0
              while ! socat - TCP:127.0.0.1:${API_HOST_PORT},connect-timeout=1 </dev/null >/dev/null 2>&1; do
                i=$((i+1)); [ "${i}" -ge 90 ] && { echo "TIMEOUT"; tail -n 100 /tmp/port-bridge.log || true; exit 1; }
                printf "."
                sleep 1
              done
              echo "OK"
              ;;
          esac

          echo "Verifying cluster connectivity..."
          kubectl config current-context
          kubectl get nodes -o wide
        '''
      }
    }

    stage('Compute Tag') {
      steps {
        script {
          env.TAG   = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
          env.IMAGE = "${env.APP}:${env.TAG}"
          echo "IMAGE=${env.IMAGE}"
        }
      }
    }

    stage('Build Docker Image (local)') {
      steps {
        dir(env.DOCKER_CTX) {
          sh 'docker build -t "${IMAGE}" .'
        }
      }
    }

    stage('Load Image into Minikube') {
      steps { sh 'minikube -p minikube image load "${IMAGE}"' }
    }

    stage('Apply Manifests & Rollout') {
      steps {
        sh """
          set -euo pipefail
          kubectl -n ${NS} apply -f ${MANIFEST_DIR}/deployment.yaml
          kubectl -n ${NS} apply -f ${MANIFEST_DIR}/service.yaml
          # ensure the deployment uses the fresh image
          kubectl -n ${NS} set image deploy/${DEPLOY} ${CTR}=${IMAGE}
          kubectl -n ${NS} rollout status deploy/${DEPLOY} --timeout=180s
          kubectl -n ${NS} get deploy,pods,svc -o wide
        """
      }
    }

    stage('Pods Snapshot & Debug') {
      steps {
        sh '''
          set -euo pipefail
          echo "== Context =="; kubectl config current-context || true
          echo "== All namespaces =="; kubectl get pods -A -o wide || true
          echo "== App namespace (${NS}) =="; kubectl -n ${NS} get deploy,po,svc,ep -o wide || true

          not_ready="$(kubectl -n ${NS} get pods --no-headers | awk '$2 != "1/1" || $3 != "Running" {print $1}')"
          if [ -n "${not_ready}" ]; then
            for p in ${not_ready}; do
              echo "---- describe $p ----"
              kubectl -n ${NS} describe pod "$p" || true
              echo "---- logs (all containers) $p ----"
              kubectl -n ${NS} logs --all-containers=true --prefix "$p" || true
            done
          fi
        '''
      }
    }

    stage('Make Interactive Access Easy (wrappers + helpers)') {
      steps {
        sh '''
          set -euo pipefail
          mkdir -p "${MINIKUBE_HOME}" "$(dirname "${KUBECONFIG}")"

          # kube-ps2
          cat > /usr/local/bin/kube-ps2 <<'EOS'
#!/usr/bin/env sh
export MK_ROOT="/var/jenkins_home/minikube/ps2"
export MINIKUBE_HOME="${MK_ROOT}/.minikube"
export KUBECONFIG="${MK_ROOT}/.kube/config"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
export NO_PROXY='127.0.0.1,localhost,.local,.svc,cluster.local,10.96.0.0/12,10.244.0.0/16,10.123.0.0/16'
export no_proxy="${NO_PROXY}"
exec kubectl "$@"
EOS
          chmod +x /usr/local/bin/kube-ps2

          # mk-ps2
          cat > /usr/local/bin/mk-ps2 <<'EOS'
#!/usr/bin/env sh
export MK_ROOT="/var/jenkins_home/minikube/ps2"
export MINIKUBE_HOME="${MK_ROOT}/.minikube"
export KUBECONFIG="${MK_ROOT}/.kube/config"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
export NO_PROXY='127.0.0.1,localhost,.local,.svc,cluster.local,10.96.0.0/12,10.244.0.0/16,10.123.0.0/16'
export no_proxy="${NO_PROXY}"
exec minikube -p minikube "$@"
EOS
          chmod +x /usr/local/bin/mk-ps2

          # start-ps2-bridge
          cat > /usr/local/bin/start-ps2-bridge <<'EOS'
#!/usr/bin/env sh
set -eu
if ! pgrep -f minikube_port_bridge.sh >/dev/null 2>&1; then
  nohup /tmp/minikube_port_bridge.sh >/tmp/port-bridge.log 2>&1 &
fi
API_HOST_PORT="$(docker port minikube 8443/tcp | awk -F':' '{print $NF}' | tail -n1 || true)"
case "${API_HOST_PORT}" in
  ''|[!0-9]) echo "Could not determine API host port"; docker port minikube || true; exit 0 ;;
  *)
    if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${API_HOST_PORT}\$"; then
      nohup socat TCP-LISTEN:${API_HOST_PORT},fork,reuseaddr TCP:host.docker.internal:${API_HOST_PORT} >/dev/null 2>&1 &
    fi
    i=0; while ! socat - TCP:127.0.0.1:${API_HOST_PORT},connect-timeout=1 </dev/null >/dev/null 2>&1; do
      i=$((i+1)); [ "$i" -ge 60 ] && break; sleep 1
    done
    echo "Bridge ready on :${API_HOST_PORT}"
    ;;
esac
EOS
          chmod +x /usr/local/bin/start-ps2-bridge

          # stop-ps2-bridge
          cat > /usr/local/bin/stop-ps2-bridge <<'EOS'
#!/usr/bin/env sh
pkill -f minikube_port_bridge.sh >/dev/null 2>&1 || true
pkill -f "socat TCP-LISTEN" >/dev/null 2>&1 || true
echo "Bridge stopped"
EOS
          chmod +x /usr/local/bin/stop-ps2-bridge

          # expose-django-service (robust forwarding to Windows)
          cat > /usr/local/bin/expose-django-service <<'EOS'
#!/usr/bin/env sh
set -eu
NS="${1:-default}"
SVC="${2:-django-service}"
MODE="${3:-service-url-only}"
JENKINS_DEFAULT_ALIAS="jenkins"
MK_NET="${MK_DOCKER_NET:-minikube-net}"

fail() { echo "ERROR: $*" >&2; exit 1; }
add_success() {
  WIN_URL="$1"
  DETAIL="$2"
  SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  if [ -z "${WINDOWS_URLS}" ]; then
    WINDOWS_URLS="${WIN_URL}"
  else
    WINDOWS_URLS="${WINDOWS_URLS}
${WIN_URL}"
  fi
  if [ -z "${SUCCESS_DETAILS}" ]; then
    SUCCESS_DETAILS="${WIN_URL}    ${DETAIL}"
  else
    SUCCESS_DETAILS="${SUCCESS_DETAILS}
${WIN_URL}    ${DETAIL}"
  fi
}

# Ensure the Kubernetes service exists before proceeding.
kube-ps2 -n "${NS}" get svc "${SVC}" >/dev/null 2>&1 || fail "Service ${NS}/${SVC} not found"

SUCCESS_COUNT=0
WINDOWS_URLS=""
SUCCESS_DETAILS=""

DO_NODEPORT=1
DO_SERVICE=1
case "${MODE}" in
  ""|all) ;;
  service-url-only|--service-url-only)
    DO_NODEPORT=0
    ;;
  nodeport-only|--nodeport-only)
    DO_SERVICE=0
    ;;
  *)
    echo "WARN: Unrecognized mode '${MODE}'. Expected 'all', '--service-url-only', or '--nodeport-only'." >&2
    ;;
esac

# Determine useful aliases for the Jenkins container so helper proxies can reach it.
JENKINS_ID="$(hostname)"
JENKINS_HOST_TARGETS="${JENKINS_DEFAULT_ALIAS}"
if docker inspect "${JENKINS_ID}" >/dev/null 2>&1; then
  JENKINS_NAME="$(docker inspect -f '{{.Name}}' "${JENKINS_ID}" 2>/dev/null | sed 's#^/##')" || JENKINS_NAME=""
  if [ -n "${JENKINS_NAME}" ]; then
    JENKINS_HOST_TARGETS="${JENKINS_HOST_TARGETS} ${JENKINS_NAME}"
  fi
  JENKINS_HOST_TARGETS="${JENKINS_HOST_TARGETS} ${JENKINS_ID}"
fi

# Helper to publish a port from Windows -> Docker host -> Minikube/Jenkins.
publish_and_verify() {
  HOST_PORT_ARG="$1"    # Desired Windows-facing host port (blank for dynamic)
  TARGET_HOSTS="$2"     # Space-delimited list of reachable hosts (aliases/IPs)
  TARGET_PORT="$3"      # Target port inside Docker network
  PROXY_NAME="$4"       # Name of the long-lived proxy container
  PROXY_NETWORK="$5"    # Network where the proxy should live

  docker rm -f "${PROXY_NAME}" >/dev/null 2>&1 || true

  PUB_ARG="-p 127.0.0.1:${HOST_PORT_ARG}:${TARGET_PORT}"
  if [ -z "${HOST_PORT_ARG}" ]; then
    PUB_ARG="-p 127.0.0.1::${TARGET_PORT}"
  fi

  CONTAINER_STARTED=0
  LAST_TARGET=""
  LAST_CID=""
  for TARGET_HOST in ${TARGET_HOSTS}; do
    [ -z "${TARGET_HOST}" ] && continue
    echo "Starting proxy '${PROXY_NAME}' on ${PROXY_NETWORK} targeting ${TARGET_HOST}:${TARGET_PORT}..." >&2
    if CID="$(docker run -d --name "${PROXY_NAME}" --restart unless-stopped \
         --network "${PROXY_NETWORK}" ${PUB_ARG} \
         alpine/socat \
         TCP-LISTEN:${TARGET_PORT},fork,reuseaddr,bind=0.0.0.0 tcp:${TARGET_HOST}:${TARGET_PORT} 2>&1)"; then
      CID="$(printf '%s' "${CID}" | tail -n1)"
      CONTAINER_STARTED=1
      LAST_TARGET="${TARGET_HOST}"
      LAST_CID="${CID}"
      break
    fi
    echo "${CID}" >&2
    echo "WARN: Proxy '${PROXY_NAME}' could not reach ${TARGET_HOST}:${TARGET_PORT}. Retrying with next candidate..." >&2
  done

  [ "${CONTAINER_STARTED}" -eq 1 ] || fail "Proxy container '${PROXY_NAME}' failed to start on any host (${TARGET_HOSTS})."

  EFFECTIVE_HOST_PORT="$(docker port "${PROXY_NAME}" "${TARGET_PORT}/tcp" | awk -F':' '{print $NF}' | tail -n1)"
  [ -n "${EFFECTIVE_HOST_PORT}" ] || fail "Could not determine published host port for ${PROXY_NAME}"

  echo "Proxy '${PROXY_NAME}' is running (container ${LAST_CID}) (Windows -> 127.0.0.1:${EFFECTIVE_HOST_PORT} -> ${LAST_TARGET}:${TARGET_PORT})." >&2
  echo "Verifying reachability from a clean container namespace..." >&2
  if docker run --rm --network bridge alpine/curl -sS --max-time 5 "http://host.docker.internal:${EFFECTIVE_HOST_PORT}/" >/dev/null 2>&1; then
    echo "Verification successful." >&2
    printf '%s\n' "${EFFECTIVE_HOST_PORT}"
    return 0
  fi

  echo "WARN: Verification via host.docker.internal:${EFFECTIVE_HOST_PORT} failed. The port may still be accessible from Windows." >&2
  printf '%s\n' "${EFFECTIVE_HOST_PORT}"
  return 1
}

# --- Method B (Preferred): expose the NodePort directly through Docker Desktop ---
if [ "${DO_NODEPORT}" -eq 1 ]; then
  echo "Attempting Method B: Exposing via NodePort..."
  NODE_PORT="$(kube-ps2 -n "${NS}" get svc "${SVC}" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || true)"
  MINIKUBE_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' minikube 2>/dev/null || true)"

  if [ -n "${NODE_PORT}" ] && [ -n "${MINIKUBE_IP}" ]; then
    echo "Found NodePort ${NODE_PORT} and Minikube IP ${MINIKUBE_IP}"
    set +e
    HOST_PORT="$(publish_and_verify "${NODE_PORT}" "minikube ${MINIKUBE_IP}" "${NODE_PORT}" "expose-${SVC}-via-nodeport" "${MK_NET}")"
    STATUS=$?
    set -e
    if [ -n "${HOST_PORT}" ]; then
      add_success "http://127.0.0.1:${HOST_PORT}" "NodePort bridge -> minikube:${NODE_PORT}"
      if [ "${STATUS}" -ne 0 ]; then
        echo "WARN: Automatic verification of NodePort forwarding had warnings. Try the URL manually."
      fi
    fi
  else
    echo "Could not determine NodePort or Minikube IP. Skipping Method B."
  fi
else
  echo "Skipping NodePort exposure (mode=${MODE})."
fi

# --- Method A: run a port-forward (service-url style) and surface the tunnel ---
if [ "${DO_SERVICE}" -eq 1 ]; then
  echo ""
  echo "Attempting Method A: Exposing via 'kubectl port-forward' (service-url style)..."
  SERVICE_PORT="$(kube-ps2 -n "${NS}" get svc "${SVC}" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || true)"

  if [ -z "${SERVICE_PORT}" ]; then
    echo "WARN: Could not determine service port for ${NS}/${SVC}. Skipping Method A."
  else
    PF_LOG="/tmp/${SVC}.port-forward.log"; : > "${PF_LOG}"
    pkill -f "port-forward.*svc/${SVC}" >/dev/null 2>&1 || true

    echo "Starting kubectl port-forward to svc/${SVC}:${SERVICE_PORT} (bind 0.0.0.0)..."
    # Bind to all interfaces so other containers on minikube-net can reach the tunnel.
    nohup kube-ps2 -n "${NS}" port-forward --address 0.0.0.0 "svc/${SVC}" ":${SERVICE_PORT}" > "${PF_LOG}" 2>&1 &

    LOCAL_PORT=""
    printf "Waiting for port-forward readiness "
    for i in $(seq 1 60); do
      # Look for either IPv4 or IPv6 forward messages.
      LINE="$(grep -Eo 'Forwarding from [^ ]+:[0-9]+' "${PF_LOG}" | tail -n1 || true)"
      if [ -n "${LINE}" ]; then
        LOCAL_PORT="$(printf '%s\n' "${LINE}" | awk -F: '{print $NF}')"
        [ -n "${LOCAL_PORT}" ] || LOCAL_PORT=""
      fi
      if [ -n "${LOCAL_PORT}" ]; then
        echo "OK (port ${LOCAL_PORT})"
        break
      fi
      printf "."; sleep 1
    done

    if [ -z "${LOCAL_PORT}" ]; then
      echo "TIMEOUT waiting for port-forward. Recent log output:"
      tail -n 20 "${PF_LOG}" || true
      echo "WARN: Port-forward never became ready."
      pkill -f "port-forward.*svc/${SVC}" >/dev/null 2>&1 || true
    else
      # Allow a brief moment for the port to settle.
      sleep 1
      set +e
      HOST_PORT="$(publish_and_verify "${LOCAL_PORT}" "${JENKINS_HOST_TARGETS}" "${LOCAL_PORT}" "expose-${SVC}-via-url-${LOCAL_PORT}" "${MK_NET}")"
      STATUS=$?
      set -e

      if [ -n "${HOST_PORT}" ]; then
        add_success "http://127.0.0.1:${HOST_PORT}" "kubectl port-forward svc/${SVC}:${SERVICE_PORT} -> pod"
        if [ "${STATUS}" -ne 0 ]; then
          echo "WARN: host.docker.internal check for ${HOST_PORT} failed. Try the URL manually."
        fi
      fi
    fi
  fi
else
  echo "Skipping service-url exposure (mode=${MODE})."
fi

if [ "${SUCCESS_COUNT}" -gt 0 ]; then
  echo ""
  echo "--- WINDOWS URLS (copy/paste) ---"
  printf '%s\n' "${WINDOWS_URLS}"
  echo ""
  echo "--- Details ---"
  printf '%s\n' "${SUCCESS_DETAILS}"
  echo "-------------------------------"
  exit 0
fi

echo ""
echo "--- FAILURE ---"
echo "No exposure strategies produced an accessible Windows URL."
echo "Please inspect Docker networking, firewall settings, or pod logs."
exit 1
EOS
          chmod +x /usr/local/bin/expose-django-service

          echo "Installed: kube-ps2, mk-ps2, start-ps2-bridge, stop-ps2-bridge, expose-django-service"
        '''
      }
    }

    // Optional: print the Windows-friendly URL
    stage('Expose Django URL (print for Windows)') {
      steps {
        sh '''
          set -euo pipefail
          start-ps2-bridge
          echo "Discovering a Windows-friendly URL for django-service..."
          expose-django-service default django-service || true
        '''
      }
    }

    stage('Archive K8s Snapshot') {
      steps {
        sh '''
          set -euo pipefail
          mkdir -p k8s-dump
          kubectl config view --minify > k8s-dump/kubeconfig-view.txt || true
          kubectl -n ${NS} get deploy,po,rs,svc,ep -o wide > k8s-dump/resources.txt || true
          kubectl -n ${NS} get events --sort-by=.lastTimestamp > k8s-dump/events.txt || true
        '''
        archiveArtifacts artifacts: 'k8s-dump/', allowEmptyArchive: true
      }
    }
  }

  post {
    always {
      echo 'Pipeline finished.'
    }
    failure {
      echo 'Collecting Minikube & network logs for debugging…'
      sh 'minikube -p minikube logs --file=logs.txt || true'
      archiveArtifacts artifacts: 'logs.txt', allowEmptyArchive: true
      sh 'docker network ls || true'
      sh 'docker network inspect "${MK_DOCKER_NET}" || true'
      sh 'echo "[BRIDGE LOGS]"; tail -n 200 /tmp/port-bridge.log || true'
    }
  }
}
