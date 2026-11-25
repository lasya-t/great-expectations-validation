"""The expectation suite for the order feed, and a gate that decides load / warn / quarantine.

Each expectation is tagged with a severity in its `meta`:
    critical - the batch must not be loaded (broken schema, duplicate keys, impossible values)
    warning  - load it, but tell someone (drift, small rates of missing data)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

COLUMNS = ["order_id", "customer_id", "order_ts", "status", "channel", "amount"]


def build_suite() -> gx.ExpectationSuite:
    crit, warn = {"severity": "critical"}, {"severity": "warning"}
    suite = gx.ExpectationSuite(name="orders_daily")
    for e in [
        gxe.ExpectTableColumnsToMatchOrderedList(column_list=COLUMNS, meta=crit),
        gxe.ExpectColumnValuesToBeUnique(column="order_id", meta=crit),
        gxe.ExpectColumnValuesToNotBeNull(column="order_id", meta=crit),
        gxe.ExpectColumnValuesToBeInSet(column="status", value_set=["placed", "paid", "shipped", "cancelled"], meta=crit),
        gxe.ExpectColumnValuesToBeBetween(column="amount", min_value=0, max_value=20_000, meta=crit),
        # a few missing customer ids happen (guest checkout); more than 1% means an upstream bug
        gxe.ExpectColumnValuesToNotBeNull(column="customer_id", mostly=0.99, meta=warn),
        # typical order is ~$90; a batch averaging far outside that means a unit or currency problem
        gxe.ExpectColumnMeanToBeBetween(column="amount", min_value=60, max_value=130, meta=warn),
        gxe.ExpectTableRowCountToBeBetween(min_value=3_000, max_value=8_000, meta=warn),
        gxe.ExpectColumnDistinctValuesToBeInSet(column="channel", value_set=["web", "app", "store"], meta=warn),
    ]:
        suite.add_expectation(e)
    return suite


@dataclass
class GateResult:
    batch: str
    decision: str                       # load | load_with_warning | quarantine
    failed: list[tuple[str, str, str]] = field(default_factory=list)   # (severity, expectation, detail)


def _describe(r) -> str:
    cfg = r.expectation_config
    res = r.result or {}
    col = cfg.kwargs.get("column", "table")
    if "unexpected_percent" in res and res.get("unexpected_count"):
        return f"{col}: {res['unexpected_count']:,} unexpected ({res['unexpected_percent']:.1f}%)"
    if "observed_value" in res:
        ov = res["observed_value"]
        ov = f"{ov:.2f}" if isinstance(ov, float) else ov
        return f"{col}: observed {ov}"
    if r.exception_info and r.exception_info.get("raised_exception"):
        return f"{col}: could not evaluate ({str(r.exception_info.get('exception_message', ''))[:60]})"
    return col


class OrdersGate:
    def __init__(self, root: str | Path = ".gx_run"):
        self.context = gx.get_context(mode="file", project_root_dir=str(root))
        ds = self.context.data_sources.add_or_update_pandas("orders_feed")
        self.asset = ds.add_dataframe_asset("daily_orders") if "daily_orders" not in [a.name for a in ds.assets] else ds.get_asset("daily_orders")
        self.batch_def = self.asset.add_batch_definition_whole_dataframe("whole") if not self.asset.batch_definitions \
            else self.asset.batch_definitions[0]
        self.suite = self.context.suites.add_or_update(build_suite())
        vd = gx.ValidationDefinition(data=self.batch_def, suite=self.suite, name="orders_daily_validation")
        self.validation = self.context.validation_definitions.add_or_update(vd)
        cp = gx.Checkpoint(name="orders_checkpoint", validation_definitions=[self.validation],
                           actions=[gx.checkpoint.UpdateDataDocsAction(name="docs")], result_format="SUMMARY")
        self.checkpoint = self.context.checkpoints.add_or_update(cp)

    def check(self, name: str, df: pd.DataFrame) -> GateResult:
        res = self.checkpoint.run(batch_parameters={"dataframe": df}, run_id=gx.core.run_identifier.RunIdentifier(run_name=name))
        vr = list(res.run_results.values())[0]
        failed = [(r.expectation_config.meta.get("severity", "critical"), r.expectation_config.type, _describe(r))
                  for r in vr.results if not r.success]
        if any(s == "critical" for s, _, _ in failed):
            decision = "quarantine"
        elif failed:
            decision = "load_with_warning"
        else:
            decision = "load"
        return GateResult(name, decision, failed)

    def docs_index(self) -> str:
        return str(Path(self.context.root_directory) / "uncommitted/data_docs/local_site/index.html")
