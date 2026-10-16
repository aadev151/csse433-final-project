# Fault Injection Research
Done by Alex Anisimov

---

This document contains a very brief outline of how we as a team will be testing out different failure modes during our experiment. As part of this, I've also made a short shell script living in `scripts/fault-injection/initial.sh` and on VM-10 for the 10/16 demo.

Our proposal named three different failure modes: network delay, clock skew, and node failures. After doing some research, I found that it's pretty trivial to also simulate packet loss, and so this will be our extra failure mode that we'll be testing.

## Network Delay
`tc qdisc ... netem delay <delay>ms` adds latency to every packet leaving thru Linux traffic control

## Clock Skew
This one is the hardest of all to do. We can turn off time sync on the target VM with `sudo timedatectl set-ntp false`, manually shift the clock by `sudo date -s "+2 seconds"`, and do `session.use_client_timestamp = False` on the backend so we don't write with client's clock.

It's pretty messy so another option I will consider when implementing this is faking the skew by using `USING TIMESTAMP <now + offset>` in Cassandra queries. It is hacky and not a true skew but it might be easier and more flexible for the future

## Node Failures
`docker stop/start cassandra` on the particular VM we want to fail

## Packet Loss (bonus)
`tc qdisc ... netem loss <loss>%` drops the % of outgoing packets randomly


# Testing the script
The repo contains a script `scripts/fault-injection/initial.sh` that can be run on VM-10 to test out the above failure modes. Here is a sample order of the commands to run it:

```
./initial.sh

sudo nsenter -t $(sudo docker inspect -f '{{.State.Pid}}' cassandra) -n ping -c 3 137.112.104.212
./initial.sh delay 200ms
./initial.sh status
sudo nsenter -t $(sudo docker inspect -f '{{.State.Pid}}' cassandra) -n ping -c 3 137.112.104.212
./initial.sh clear

./initial.sh loss 30%
sudo nsenter -t $(sudo docker inspect -f '{{.State.Pid}}' cassandra) -n ping -c 20 137.112.104.212
./initial.sh clear
./initial.sh status

./initial.sh skew "+5 seconds"
date
./initial.sh unskew
timedatectl

./initial.sh down
sudo docker exec cassandra nodetool status
sudo docker exec cassandra cqlsh -e "CONSISTENCY QUORUM;
# On VM 11:
SELECT * FROM market.latest_quote WHERE run_id='demo1' AND symbol='BTCUSDT';"
sudo docker exec cassandra cqlsh -e "CONSISTENCY ALL; SELECT * FROM market.latest_quote WHERE run_id='demo1' AND symbol='BTCUSDT';"
# Back to VM 10:
./initial.sh up
sudo docker exec cassandra nodetool status

./initial.sh clear
./initial.sh unskew
exit
```