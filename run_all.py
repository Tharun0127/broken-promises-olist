"""Rebuild every output from the raw Kaggle files.

    python run_all.py                 full rebuild, checks and notebook
    python run_all.py --no-notebook   skip executing the walkthrough notebook

Raw CSVs must be in data/raw/ (see README). Nothing here is hardcoded: every
number in outputs/, docs/ and README.md is computed from those files.
"""
import argparse
import json
import sys
import time

from src import config


def step(name):
    print(f"[{time.strftime('%H:%M:%S')}] {name}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-notebook", action="store_true")
    args = ap.parse_args(argv)

    from src import (cohorts, dashboard, db, experiment, funnels, model, powerbi_export, powerbi_guide,
                     profile_data, promise_gap, report, sizing, verify)

    config.OUTPUTS.mkdir(parents=True, exist_ok=True)
    if config.DB_PATH.exists():          # always start from an empty warehouse
        config.DB_PATH.unlink()
    con = db.connect()

    step("1. Staging views and data profile")
    db.register_raw(con)
    db.write_params(con)
    db.run_layer(con, "staging")
    profile = profile_data.main(con)

    step("2. Clean model (intermediate and marts)")
    db.build(con, layers=["intermediate", "marts"])
    model.export_exclusions(con)

    m = {}
    m["data_start"] = str(con.execute("select min(purchased_at)::date from stg_orders").fetchone()[0])
    m["data_end"] = str(con.execute("select data_end from int_data_window").fetchone()[0])
    m["orders_raw"] = profile["orders"]
    m["delivered_orders"] = con.execute("select count(*) from int_delivered_orders").fetchone()[0]
    m["late_review_before_delivery_all"] = profile["late_review_before_delivery"]

    step("3. Funnels")
    m.update(funnels.main(con))
    step("4. Cohorts")
    m.update(cohorts.main(con))
    step("5. Promise gap (regression discontinuity)")
    m.update(promise_gap.main(con))
    step("6. Business sizing")
    m.update(sizing.main(con, m))
    step("7. Experiment design")
    m.update(experiment.main(con, m))

    m = {k: (v.item() if hasattr(v, "item") else v) for k, v in m.items()}
    (config.OUTPUTS / "metrics.json").write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")

    step("8. Power BI export and dashboard")
    powerbi_export.main(con)
    powerbi_guide.write(m)
    dashboard.main(m, report.answer_text(m), report.recommendation_text(m))

    step("9. README and memo")
    report.main(m)

    step("10. Verification")
    ok = verify.main(con)
    con.close()

    if not args.no_notebook:
        step("Executing notebook")
        from src import notebook
        notebook.main()

    step("Done" if ok else "Done, but verification FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
