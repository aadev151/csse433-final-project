#!/usr/bin/env bash

set -euo pipefail

container=cassandra

container_pid() { sudo docker inspect -f '{{.State.Pid}}' "$container"; }
in_container_net() { sudo nsenter -t "$(container_pid)" -n "$@"; }
default_iface() { in_container_net ip route show default | awk '{print $5; exit}'; }

case "${1:-}" in
  delay)  in_container_net tc qdisc replace dev "$(default_iface)" root netem delay "${2:-100ms}" ;;
  loss)   in_container_net tc qdisc replace dev "$(default_iface)" root netem loss "${2:-10%}" ;;
  clear)  in_container_net tc qdisc del dev "$(default_iface)" root 2>/dev/null || true ;;
  status) in_container_net tc qdisc show dev "$(default_iface)" ;;
  down)   sudo docker stop "$container" ;;
  up)     sudo docker start "$container" ;;
  skew)   sudo timedatectl set-ntp false && sudo date -s "${2:-+2 seconds}" ;;
  unskew) sudo timedatectl set-ntp true ;;
  *) echo "usage: $0 delay [100ms] | loss [10%] | clear | status | down | up | skew [+2 seconds] | unskew"; exit 1 ;;
esac