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