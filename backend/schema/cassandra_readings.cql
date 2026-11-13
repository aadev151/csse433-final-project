CREATE KEYSPACE IF NOT EXISTS market
  WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 3};

CREATE TABLE IF NOT EXISTS market.readings (
    run_id text,
    signal_id text,
    symbol text,
    t_us bigint,
    market_us bigint,
    value double,
    truth double,
    staleness_ms double,
    latency_ms double,
    PRIMARY KEY ((run_id, signal_id, symbol), t_us)
);