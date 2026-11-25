"""Run the gate over a week of batches: load, load with a warning, or quarantine."""
import logging
import shutil
import warnings
from pathlib import Path

from orders_gx.feed import ISSUES, week
from orders_gx.suite import OrdersGate

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
shutil.rmtree(".gx_run", ignore_errors=True)
gate = OrdersGate()
loaded, quarantine = [], Path("quarantine")
shutil.rmtree(quarantine, ignore_errors=True)

for day, df in week().items():
    r = gate.check(day, df)
    print(f"{day}  {r.decision:18s} {ISSUES.get(day, '')}")
    for sev, exp, detail in r.failed:
        print(f"            [{sev:8s}] {exp}: {detail}")
    if r.decision == "quarantine":
        quarantine.mkdir(exist_ok=True)
        df.to_csv(quarantine / f"orders_{day}.csv", index=False)
    else:
        loaded.append(day)

print(f"\nloaded {len(loaded)} of 7 batches; quarantined: {sorted(p.stem for p in quarantine.glob('*.csv'))}")
print(f"Data Docs: {gate.docs_index()}")
