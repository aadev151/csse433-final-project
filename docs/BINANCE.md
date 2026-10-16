# Getting Binance Trading Data

## Overview

Binance allows us to access trade data including both public market trades and individual account trades. Our application will retrive public market trade data via use of APIs

### What is a Trade

Any individual buy or sell order that has been matched and executed on the exchange. It is a single transaction. An `aggTrade` is a combined record of multiple trades at same price and similar timestamp to allow easier analysis of market activity. It is essentially multiple trade transactioned combined into an aggregated record.

### Historical Trade Data obtained from Binance Data Collection

The *Binance Data Collection* at data.binance.vision is the source of historical public market data that has been organised into daily and monthly files.

**An Update to a Daily File**: Made available each day after trading happens. Contains both trades and aggTrades.
**An update to a Monthly File**: Made available on the first Monday of each month. Contains both trades and aggTrades.

