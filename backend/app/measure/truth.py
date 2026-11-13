from bisect import bisect_right
from itertools import accumulate

from app.measure.signals import quote_value, trade_value


class TruthBook:
    """Exact signal values computed from the raw Binance file"""

    def __init__(self, trades, quotes):
        self.trade_us = [t[0] for t in trades]
        self.trade_price = [t[2] for t in trades]
        self.trade_qty = [t[3] for t in trades]
        self.quote_us = [q[0] for q in quotes]
        self.quote_bid = [q[2] for q in quotes]
        self.quote_ask = [q[4] for q in quotes]
        self._prefix = {}

    def _prefix_sums(self, field):
        if field not in self._prefix:
            values = (trade_value(field, p, q) for p, q in zip(self.trade_price, self.trade_qty))
            self._prefix[field] = [0.0, *accumulate(values)]  # prefix[i] = sum of first i trades
        return self._prefix[field]

    def evaluate(self, spec, at_us):
        if spec.kind == "quote":
            i = bisect_right(self.quote_us, at_us) - 1
            if i < 0:
                return None
            return quote_value(spec.field, self.quote_bid[i], self.quote_ask[i]), self.quote_us[i]

        i = bisect_right(self.trade_us, at_us) - 1
        if i < 0:
            return None

        if spec.kind == "last_trade":
            return trade_value(spec.field, self.trade_price[i], self.trade_qty[i]), self.trade_us[i]

        if spec.kind == "trade_total":
            lo = bisect_right(self.trade_us, at_us - spec.window_us)
            prefix = self._prefix_sums(spec.field)
            newest = self.trade_us[i] if i >= lo else None
            return prefix[i + 1] - prefix[lo], newest
