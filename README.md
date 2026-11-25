# Data Quality Gate with Great Expectations

A Great Expectations 1.x suite that checks every daily batch of an order feed **before** it loads, and decides: **load**, **load with a warning**, or **quarantine**. Each expectation carries a severity, so small, known issues don't block the pipeline while real breakage never reaches the warehouse.

## The suite

| Expectation | Severity | Catches |
|---|---|---|
| columns match the expected ordered list | critical | renamed or dropped columns |
| `order_id` unique and not null | critical | double loads, broken keys |
| `status` in the allowed set | critical | new or garbage status values |
| `amount` between 0 and 20,000 | critical | impossible values |
| **average `amount` between $60 and $130** | **critical** | unit or currency changes |
| `customer_id` not null for ≥ 99% of rows | warning | upstream join problems |
| row count 3,000–8,000 | warning | partial or duplicated extracts |
| `channel` values known | warning | new sales channels |

A Checkpoint runs the suite on each batch and rebuilds the **Data Docs** HTML site, so every run can be browsed afterwards.

## One week of batches, four injected problems

```
2025-11-01  load
2025-11-02  load
2025-11-03  load_with_warning  5% of rows missing customer_id (upstream join bug)
            [warning ] expect_column_values_to_not_be_null: customer_id: 242 unexpected (4.8%)
2025-11-04  load
2025-11-05  quarantine         column 'amount' renamed to 'order_amount' (unannounced schema change)
            [critical] expect_table_columns_to_match_ordered_list: observed [..., 'order_amount']
            [critical] expect_column_mean_to_be_between: amount: column missing, check could not run
2025-11-06  quarantine         amounts sent in cents instead of dollars
            [critical] expect_column_values_to_be_between: amount: 351 unexpected (7.0%)
            [critical] expect_column_mean_to_be_between: amount: observed 9111.22
2025-11-07  quarantine         the batch was appended twice (duplicate order_ids)
            [critical] expect_column_values_to_be_unique: order_id: 10,000 unexpected (100.0%)

loaded 4 of 7 batches; quarantined: orders_2025-11-05, orders_2025-11-06, orders_2025-11-07
```

## A design flaw the tests caught

The average-amount check started out as a **warning**. One test builds a cents-instead-of-dollars batch where every order is small, so every individual amount still sits under the 20,000 cap and **every row-level check passes**. The only alarm was the average-amount warning, so the batch would have **loaded** with 100× inflated revenue.

Row-level checks can't see a problem that's only visible across the whole batch. The average-amount check is now critical, and the test asserts the batch is quarantined (see the commit history).

The week run shows the same thing from the other side: on the real cents batch, the row-level cap only flagged the 7% of orders that happened to exceed 20,000.

## How to run

Great Expectations conflicts with PySpark in the same environment, so use a clean virtual environment:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python run_week.py      # prints decisions, writes quarantine/ and Data Docs
pytest
```

## Next steps
- Run the gate as an Airflow or Prefect task in front of the load step
- Learn the average-amount range from recent history instead of fixing it by hand
