from app.runs.models import RunConfig
from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster
import subprocess
import time

cluster = Cluster(['137.112.104.214', '137.112.104.212', '137.112.104.145'])
session = cluster.connect()

session.set_keyspace('market')

class FaultInjection:
    def __init__(self, run_config: RunConfig):
        self.consistency = run_config.consistency
        self.delay_ms = run_config.delay_ms
        self.packet_loss_pct = run_config.packet_loss_pct
        self.clock_skew_ms = run_config.clock_skew_ms
        self.node_outage = run_config.node_outage

    def set_appropriate_consistency(self):
        if self.consistency == "QUORUM":
            session.default_consistency_level = ConsistencyLevel.QUORUM
        elif self.consistency == "ONE":
            session.default_consistency_level = ConsistencyLevel.ONE
        else:
            session.default_consistency_level = ConsistencyLevel.ALL
            
    def insert_network_delay(self):
        subprocess.run(["/fault-injection.sh", "delay", f"{self.delay_ms}ms"])
        self.show_and_ping_helper()

    def insert_packet_loss(self):
        subprocess.run(["/fault-injection.sh", "loss", f"{self.packet_loss_pct}%"])
        self.show_and_ping_helper()

    def insert_clock_skew(self):
        subprocess.run(["/fault-injection.sh", "skew", f"{self.clock_skew_ms} seconds"])
        subprocess.run(["/fault-injection.sh", "status"])

    def insert_node_outage(self):
        if self.node_outage == "none":
            subprocess.run(["/fault-injection.sh", "up"])
        else:
            subprocess.run(["/fault-injection.sh", "down"])
        time.sleep(5)
        subprocess.run(["/fault-injection.sh", "status"])

    def show_and_ping_helper():
        subprocess.run["/fault-injection.sh", "show"]
        subprocess.run["/fault-injection.sh", "ping"]

    def applyFaultInjection(self):
        self.set_appropriate_consistency()
        self.insert_network_delay()
        self.insert_packet_loss()
        self.insert_clock_skew()
        self.insert_node_outage()

    
