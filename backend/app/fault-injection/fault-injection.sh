#!/usr/bin/env bash

set -euo pipefail

# This line specified the cassandra container
container=cassandra

# These are some useful functions to identify the ip, host information for the container and cassandra cluster
container_pid() { sudo docker inspect -f '{{.State.Pid}}' "$container"; }
in_container_net() { sudo nsenter -t "$(container_pid)" -n "$@"; }
default_iface() { in_container_net ip route show default | awk '{print $5; exit}'; }

case "${1:-}" in
  #https://oneuptime.com/blog/post/2026-03-20-simulate-network-latency-tc-netem/view
  delay)  in_container_net tc qdisc replace dev "$(default_iface)" root netem delay "${2:-100ms}" ;;
  #https://oneuptime.com/blog/post/2026-03-20-simulate-network-latency-tc-netem/view
  show)   in_container_net tc qdisc show dev "$(default_iface)" ;;
  ping)   in_container_net ping -c 5 8.8.8.8 ;;
  
  # https://stackoverflow.com/questions/614795/simulate-delayed-and-dropped-packets-on-linux
  loss)   in_container_net tc qdisc replace dev "$(default_iface)" root netem loss "${2:-10%}" ;;

  
  clear)  in_container_net tc qdisc del dev "$(default_iface)" root 2>/dev/null || true ;;
  down)   sudo docker stop "$container" ;;
  up)     sudo docker start "$container" ;;

  # https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/system_administrators_guide/chap-configuring_the_date_and_time
  skew)   sudo timedatectl set-ntp false && sudo date -s "${2:-+2 seconds}" ;;
  unskew) sudo timedatectl set-ntp true ;;
  *) echo "usage: $0 delay [100ms] | loss [10%] | clear | status | down | up | skew [+2 seconds] | unskew"; exit 1 ;;
esac