"""Daily order feed batches, with the problems real feeds develop over time."""
from __future__ import annotations

import numpy as np
import pandas as pd

ISSUES = {
    "2025-11-03": "5% of rows missing customer_id (upstream join bug)",
    "2025-11-05": "column 'amount' renamed to 'order_amount' (unannounced schema change)",
    "2025-11-06": "amounts sent in cents instead of dollars",
    "2025-11-07": "the batch was appended twice (duplicate order_ids)",
}


def daily_batch(day: str, n: int = 5000, seed: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed if seed is not None else int(day.replace("-", "")))
    start = int(day.replace("-", "")[2:]) * 100_000
    df = pd.DataFrame({
        "order_id": np.arange(start, start + n),
        "customer_id": pd.array(rng.integers(1, 200_000, n), dtype="Int64"),
        "order_ts": pd.Timestamp(day) + pd.to_timedelta(rng.integers(0, 86_400, n), unit="s"),
        "status": rng.choice(["placed", "paid", "shipped", "cancelled"], n, p=[0.2, 0.5, 0.25, 0.05]),
        "channel": rng.choice(["web", "app", "store"], n, p=[0.5, 0.35, 0.15]),
        "amount": rng.gamma(2.0, 45.0, n).round(2),
    })
    if day == "2025-11-03":
        df.loc[rng.random(n) < 0.05, "customer_id"] = pd.NA
    if day == "2025-11-05":
        df = df.rename(columns={"amount": "order_amount"})
    if day == "2025-11-06":
        df["amount"] = (df["amount"] * 100).round(0)
    if day == "2025-11-07":
        df = pd.concat([df, df], ignore_index=True)
    return df


def week() -> dict[str, pd.DataFrame]:
    days = pd.date_range("2025-11-01", "2025-11-07").strftime("%Y-%m-%d")
    return {d: daily_batch(d) for d in days}
