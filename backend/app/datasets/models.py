from datetime import date
from typing import Literal

from pydantic import BaseModel

SYMBOLS = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DATASET_KIND = Literal["trades", "quotes"]


class DatasetImportInput(BaseModel):
    symbol: SYMBOLS
    kind: DATASET_KIND
    # start and end are inclusive days (YYYY-MM-DD), same as the frontend sends
    start: date
    end: date
