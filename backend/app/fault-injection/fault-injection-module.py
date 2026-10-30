from app.runs.models import RunConfig
from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster
import subprocess

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
            
    def insert_network_delay():
        ...

    def insert_packet_loss():
        ...

    def insert_clock_skew():
        ...

    def insert_node_outage():
        ...

    def applyFaultInjection():
        ...

    
