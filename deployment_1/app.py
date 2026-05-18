"""
Instacart Product Placement Dashboard — deployment_1 (modular version)
======================================================================

This is a parallel copy of ../deployment/app.py.  Every page is identical
EXCEPT  "Product Development → Products Bought Together", which has been
rebuilt as an **aisle-level** market basket analysis, and the Customer
Retention pages, which have been upgraded for visual consistency and
analytical depth.

Architecture
------------
- app.py                     : sidebar, CSV guard, and router (this file)
- data_loaders.py            : every @st.cache_data function lives here
- defs_aisle_network.py      : network maths (community detection, layout, …)
- views/                     : one module per dashboard page; each exposes
                               a single `render()` function

Why this split?
- *Separation of Concerns*: data loading, network maths, and per-page UI
  each live in their own file.  Each file is now short enough to read in
  one sitting.
- *DRY (Don't Repeat Yourself)*: the per-product aggregation that used to
  appear in three places now lives once in `data_loaders.product_stats()`
  and is imported wherever it's needed.

Run it:
    uv run streamlit run deployment_1/app.py
"""

import streamlit as st

from data_loaders import CSV_FILES, DATA_DIR
from views import (
    department_sales,
    hidden_gems,
    kpi_overview,
    products_bought_together,
    reorder_rate,
    shopping_time,
    top_sellers,
)

st.set_page_config(
    page_title="Instacart EDA — aisle-level",
    page_icon="🛒",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("Instacart Product Placement Analysis")
st.sidebar.caption("deployment_1 · aisle-level co-purchase update")

section = st.sidebar.radio(
    "Section",
    ["KPI Overview", "Product Development", "Customer Retention"],
)

sub_page = None
if section == "Product Development":
    st.sidebar.divider()
    sub_page = st.sidebar.radio(
        "Product Development",
        ["Top Sellers", "Department Sales", "Products Bought Together"],
    )
elif section == "Customer Retention":
    st.sidebar.divider()
    sub_page = st.sidebar.radio(
        "Customer Retention",
        ["Reorder Rate", "Hidden Gems", "Shopping Time Heatmap"],
    )

# ── Guard: missing CSV files ──────────────────────────────────────────────────
missing_csv = [f for f in CSV_FILES if not (DATA_DIR / f).exists()]
if missing_csv:
    st.error(
        f"Missing CSV files in `{DATA_DIR}`: {', '.join(missing_csv)}\n\n"
        "Please run the **data_acquisition** notebook first."
    )
    st.stop()

# ── Router ────────────────────────────────────────────────────────────────────
# Each view module exposes a single `render()` function — the rest of the file
# is just a dispatch table.
_ROUTES = {
    ("KPI Overview", None):                                  kpi_overview.render,
    ("Product Development", "Top Sellers"):                  top_sellers.render,
    ("Product Development", "Department Sales"):             department_sales.render,
    ("Product Development", "Products Bought Together"):     products_bought_together.render,
    ("Customer Retention", "Reorder Rate"):                  reorder_rate.render,
    ("Customer Retention", "Hidden Gems"):                   hidden_gems.render,
    ("Customer Retention", "Shopping Time Heatmap"):         shopping_time.render,
}

route = _ROUTES.get((section, sub_page))
if route is not None:
    route()
