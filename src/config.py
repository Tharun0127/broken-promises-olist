"""Single source of truth for paths and analysis parameters.

Every number that defines the analysis (windows, cutoffs, bandwidth grid)
lives here. SQL reads them from the `params` table that build_model creates.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "warehouse.duckdb"
SQL_DIR = ROOT / "sql"
OUTPUTS = ROOT / "outputs"
DOCS = ROOT / "docs"
POWERBI = ROOT / "powerbi"
NOTEBOOKS = ROOT / "notebooks"

# Raw CSV name -> raw view name used by the staging SQL.
RAW_FILES = {
    "raw_orders": "olist_orders_dataset.csv",
    "raw_order_items": "olist_order_items_dataset.csv",
    "raw_customers": "olist_customers_dataset.csv",
    "raw_order_reviews": "olist_order_reviews_dataset.csv",
    "raw_order_payments": "olist_order_payments_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_sellers": "olist_sellers_dataset.csv",
    "raw_geolocation": "olist_geolocation_dataset.csv",
    "raw_category_translation": "product_category_name_translation.csv",
    "raw_mql": "olist_marketing_qualified_leads_dataset.csv",
    "raw_closed_deals": "olist_closed_deals_dataset.csv",
}

# Analysis parameters (see docs/DECISIONS.md for the reasoning).
REPEAT_WINDOW_DAYS = 180       # repeat purchase outcome window
SELLER_ACTIVE_DAYS = 90        # "still selling" window in the seller funnel
COHORT_START = "2017-01-01"    # 2016 is too sparse for monthly cohorts

# Regression discontinuity.
# Running variable = delivered date minus estimated date, in whole days.
# Day 0 = delivered on the promised day (on time). Day 1 = first late day.
RD_FIRST_LATE_DAY = 1
RD_BANDWIDTH_GRID = list(range(3, 22))   # candidate bandwidths (days per side)
RD_CV_WINDOW = 7                         # days per side used to score the CV
RD_DESCRIPTIVE_RANGE = (-30, 30)         # range shown on the descriptive curve
ALPHA = 0.05

# Experiment design.
POWER = 0.80
EXPERIMENT_MDE_RELATIVE = 0.10   # detect a 10% relative drop in the primary metric
