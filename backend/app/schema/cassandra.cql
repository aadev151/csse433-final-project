CREATE KEYSPACE IF NOT EXISTS app
  WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 3};

CREATE TABLE IF NOT EXISTS app.records (
  record_type text,
  id text,
  version int,
  body text,
  PRIMARY KEY ((record_type), id)
);