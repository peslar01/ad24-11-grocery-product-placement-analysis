"""
Cached data loaders for the Instacart dashboard
================================================

Single source of truth for everything that touches the CSVs.  All functions
here are decorated with `@st.cache_data`, so the heavy joins and aggregations
only run once per session and are reused across every view in `views/`.

This module also exposes the project-level constants (`DATA_DIR`, `CSV_FILES`)
so `app.py` can validate that the data folder is wired up correctly before
delegating to the views.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from defs_aisle_network import (
    compute_aisle_pairs, build_edges, giant_component,
    detect_communities, spring_layout,
)

# Data lives at the project root: PODSV_Project/data
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CSV_FILES = [
    "orders.csv", "products.csv", "aisles.csv",
    "departments.csv", "order_products__prior.csv",
]


# Instacart bundles meat + seafood into a single "meat seafood" department.
# We split it back into two departments based on the aisle name so the
# dashboard treats them separately (more useful for product personas).
_MEAT_AISLES    = {"meat counter", "packaged meat", "packaged poultry",
                   "poultry counter", "hot dogs bacon sausage"}
_SEAFOOD_AISLES = {"packaged seafood", "seafood counter"}


@st.cache_data(show_spinner="Loading data …")
def load_csv():
    """Read every required CSV once and return the four canonical DataFrames.

    Returns
    -------
    (orders, products, products_full, order_products)
        - orders          : raw orders.csv
        - products        : raw products.csv
        - products_full   : products joined with aisles + departments, with
                            the meat/seafood split applied
        - order_products  : raw order_products__prior.csv
    """
    orders         = pd.read_csv(DATA_DIR / "orders.csv")
    products       = pd.read_csv(DATA_DIR / "products.csv")
    aisles         = pd.read_csv(DATA_DIR / "aisles.csv")
    departments    = pd.read_csv(DATA_DIR / "departments.csv")
    order_products = pd.read_csv(DATA_DIR / "order_products__prior.csv")

    products_full = products.merge(aisles, on="aisle_id").merge(departments, on="department_id")

    # Split "meat seafood" → "meat" / "seafood" so the two are reported separately
    # everywhere downstream. Applies to a single column so all aggregates inherit it.
    ms_mask = products_full["department"] == "meat seafood"
    products_full.loc[ms_mask & products_full["aisle"].isin(_MEAT_AISLES),
                      "department"] = "meat"
    products_full.loc[ms_mask & products_full["aisle"].isin(_SEAFOOD_AISLES),
                      "department"] = "seafood"

    return orders, products, products_full, order_products


@st.cache_data
def dept_color_map():
    """Map each department to a fixed colour from a 26-colour qualitative palette.

    Cached so the same colours are used in every chart, produce is always
    teal, snacks always orange, etc. across Top Sellers, Aisle view, and
    the Treemap.
    """
    _, _, products_full, _ = load_csv()
    dept_list = sorted(products_full["department"].unique())
    palette = px.colors.qualitative.Alphabet  # 26 distinct colours
    return {d: palette[i % len(palette)] for i, d in enumerate(dept_list)}


@st.cache_data(show_spinner="Aggregating purchases by aisle …")
def aisle_aggregates():
    """Pre-aggregate purchase count + reorder stats per (department, aisle).

    Used by all Department Sales views, computed once, then reused. Returns a
    small DataFrame (134 rows) instead of repeatedly merging a 32M-row table.
    """
    _, _, products_full, order_products = load_csv()
    op = order_products.merge(
        products_full[["product_id", "department", "aisle"]],
        on="product_id",
    )
    df = (
        op.groupby(["department", "aisle"])
        .agg(
            count=("product_id", "size"),
            reorder_sum=("reordered", "sum"),
        )
        .reset_index()
    )
    df["reorder_rate"] = df["reorder_sum"] / df["count"]
    df["share_pct"] = df["count"] / df["count"].sum() * 100
    return df


@st.cache_data(show_spinner="Computing per-product stats …")
def product_stats():
    """Per-product purchase count, reorder rate, and enrichment.

    Single source of truth for "how often is product X bought, and how loyal
    are its customers?", used by Top Sellers, Reorder Rate and Hidden Gems.
    Returns a DataFrame with columns:
        product_id, count, reorder_rate, share_pct,
        product_name, department, aisle
    """
    _, _, products_full, order_products = load_csv()
    stats = (
        order_products.groupby("product_id")
        .agg(count=("product_id", "size"),
             reorder_rate=("reordered", "mean"))
        .reset_index()
    )
    stats["share_pct"] = stats["count"] / stats["count"].sum() * 100
    return stats.merge(
        products_full[["product_id", "product_name", "department", "aisle"]],
        on="product_id",
    )


@st.cache_data(show_spinner="Counting aisle co-purchases — one-time, ~30–60 s …")
def load_aisle_pairs():
    """Heavy step: count how often each pair of aisles is bought together."""
    return compute_aisle_pairs(str(DATA_DIR))


@st.cache_data
def aisle_enrichment():
    """Return {aisle_id: {name, department, share_pct, reorder_rate}}.

    Joins the cached (department, aisle) aggregate with the aisle IDs used
    by the co-purchase network. Used to enrich node hovers and to power
    cluster naming.
    """
    _, _, products_full, _ = load_csv()
    agg = aisle_aggregates()
    aid_map = products_full[["aisle_id", "aisle"]].drop_duplicates()
    merged = agg.merge(aid_map, on="aisle")
    out = {}
    for _, row in merged.iterrows():
        out[int(row["aisle_id"])] = {
            "name":         row["aisle"],
            "department":   row["department"],
            "share_pct":    float(row["share_pct"]),
            "reorder_rate": float(row["reorder_rate"]),
        }
    return out


@st.cache_data(show_spinner="Ranking aisle co-purchase pairs …")
def top_aisle_pairs(min_count: int = 1000, min_lift: float = 1.3):
    """Return a DataFrame of aisle pairs with lift, count, share, and dept info.

    Filters out the 'missing' and 'other' departments so the ranking shows
    meaningful, actionable pairs. Sorted by lift (highest first).
    """
    pairs, count_a, n_orders, aid2name = load_aisle_pairs()
    info = aisle_enrichment()

    rows = []
    for (a, b), c in pairs.items():
        if c < min_count:
            continue
        ia, ib = info.get(int(a)), info.get(int(b))
        if not ia or not ib:
            continue
        if ia["department"] in ("missing", "other") or ib["department"] in ("missing", "other"):
            continue
        lift = c * n_orders / (count_a[a] * count_a[b])
        if lift < min_lift:
            continue
        rows.append({
            "aisle_a":         aid2name[a],
            "department_a":    ia["department"],
            "aisle_b":         aid2name[b],
            "department_b":    ib["department"],
            "co_orders":       int(c),
            "share_of_orders": c / n_orders * 100,
            "lift":            float(lift),
        })
    df = pd.DataFrame(rows).sort_values("lift", ascending=False).reset_index(drop=True)
    return df


@st.cache_data(show_spinner="Aggregating department co-purchases …")
def dept_pair_matrix():
    """Aggregate aisle pairs to a department × department co-occurrence matrix.

    Returns a square pandas DataFrame indexed by department, values are the
    summed co-occurrence counts of all aisle pairs that span the two
    departments. Used by the heatmap view.
    """
    pairs, count_a, n_orders, aid2name = load_aisle_pairs()
    info = aisle_enrichment()

    departments = sorted({
        v["department"] for v in info.values()
        if v["department"] not in ("missing", "other")
    })
    idx = {d: i for i, d in enumerate(departments)}
    n = len(departments)

    M = np.zeros((n, n), dtype=float)

    for (a, b), c in pairs.items():
        ia, ib = info.get(int(a)), info.get(int(b))
        if not ia or not ib:
            continue
        da, db = ia["department"], ib["department"]
        if da not in idx or db not in idx:
            continue
        M[idx[da], idx[db]] += c
        if da != db:
            M[idx[db], idx[da]] += c  # mirror to keep matrix symmetric

    return pd.DataFrame(M, index=departments, columns=departments)


@st.cache_data(show_spinner="Building the aisle network …")
def build_aisle_network_data(min_count: int, min_lift: float, dim: int = 2):
    """Heavy step, cached so slider/focus changes don't rerun it.

    Returns the raw network data plus a layout (2D or 3D) so rendering the
    figure stays cheap.
    """
    pairs, count_a, n_orders, aid2name = load_aisle_pairs()
    edges = build_edges(pairs, count_a, n_orders, aid2name,
                        min_count=min_count, min_lift=min_lift)
    giant, edges = giant_component(edges)
    nodes = sorted(giant)
    node_comm = detect_communities(nodes, edges)
    pos = spring_layout(nodes, edges, node_comm, dim=dim)
    return nodes, edges, node_comm, pos, count_a, aid2name
