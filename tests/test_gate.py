import warnings

import pandas as pd
import pytest

from orders_gx.feed import daily_batch
from orders_gx.suite import OrdersGate

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def gate(tmp_path_factory):
    return OrdersGate(tmp_path_factory.mktemp("gx"))


def test_clean_batch_loads(gate):
    assert gate.check("clean", daily_batch("2025-11-01")).decision == "load"


def test_some_missing_customers_is_only_a_warning(gate):
    r = gate.check("nulls", daily_batch("2025-11-03"))
    assert r.decision == "load_with_warning"
    assert [e for _, e, _ in r.failed] == ["expect_column_values_to_not_be_null"]


@pytest.mark.parametrize("day,expectation", [
    ("2025-11-05", "expect_table_columns_to_match_ordered_list"),
    ("2025-11-07", "expect_column_values_to_be_unique"),
])
def test_breaking_problems_are_quarantined(gate, day, expectation):
    r = gate.check(day, daily_batch(day))
    assert r.decision == "quarantine"
    assert (("critical", expectation) in [(s, e) for s, e, _ in r.failed])


def test_unit_change_caught_by_distribution_even_when_rows_look_valid(gate):
    # cents instead of dollars, but only small orders: every row stays under the 20,000 cap
    df = daily_batch("2025-11-02")
    df["amount"] = (df["amount"].clip(upper=150) * 100).round(0)
    r = gate.check("cents_small", df)
    failed = [e for _, e, _ in r.failed]
    assert "expect_column_values_to_be_between" not in failed       # row-level check is fooled
    assert "expect_column_mean_to_be_between" in failed             # batch-level check is not
    assert r.decision == "quarantine"
