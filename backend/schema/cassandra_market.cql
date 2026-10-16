CREATE TABLE IF NOT EXISTS market.trades (
    run_id text,
    symbol text,
    hour_bucket bigint,
    event_us bigint,
    trade_id bigint,
    price double,
    qty double,
    buyer_is_maker boolean,
    ingest_us bigint,
    PRIMARY KEY ((run_id, symbol, hour_bucket), event_us, trade_id)
);

CREATE TABLE IF NOT EXISTS market.quotes (
    run_id text,
    symbol text,
    hour_bucket bigint,
    event_us bigint,
    update_id bigint,
    bid_px double,
    bid_qty double,
    ask_px double,
    ask_qty double,
    ingest_us bigint,
    PRIMARY KEY ((run_id, symbol, hour_bucket), event_us, update_id)
);

CREATE TABLE IF NOT EXISTS market.latest_quote (
    run_id text,
    symbol text,
    event_us bigint,
    bid_px double,
    bid_qty double,
    ask_px double,
    ask_qty double,
    PRIMARY KEY ((run_id, symbol))
);
