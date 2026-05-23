"""Reorder Rate — top products by reorder rate, coloured by department."""

import plotly.express as px
import streamlit as st

from data_loaders import dept_color_map, product_stats


def render():
    st.title("Top Products by Reorder Rate")
    st.markdown(
        "The reorder rate is the share of a product's purchases that come from "
        "customers who had ordered it before. A high reorder rate indicates a "
        "loyal, habitual customer base, strong candidates for subscription "
        "offers, auto-reorder reminders, or staple-shelf placement."
    )

    stats = product_stats()

    # ── Controls ────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_purchases = st.slider(
            "Minimum number of purchases", 100, 2000, 500, step=100,
            help="Filter out niche products so the ranking is driven by "
                 "loyalty, not by tiny sample sizes.",
        )
    with col_f2:
        n = st.slider("Number of products", 5, 40, 20)

    eligible_count = int((stats["count"] >= min_purchases).sum())

    top_reorder = (
        stats[stats["count"] >= min_purchases]
        .sort_values("reorder_rate", ascending=False)
        .head(n)
        .sort_values("reorder_rate")  # ascending → top bar at top of chart
    )

    if top_reorder.empty:
        st.warning(
            "No products meet the current threshold. "
            "Try lowering the minimum number of purchases."
        )
        return

    st.caption(
        f"**{eligible_count:,}** products meet the threshold of "
        f"≥ {min_purchases:,} purchases, showing the top {len(top_reorder)} "
        "by reorder rate."
    )

    fig = px.bar(
        top_reorder,
        x="reorder_rate",
        y="product_name",
        orientation="h",
        color="department",
        color_discrete_map=dept_color_map(),
        custom_data=["department", "aisle", "count", "reorder_rate"],
        labels={"reorder_rate": "Reorder Rate", "product_name": "",
                "department": "Department"},
        range_x=[0, 1],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Department: %{customdata[0]}<br>"
            "Aisle: %{customdata[1]}<br>"
            "Purchases: %{customdata[2]:,}<br>"
            "Reorder rate: %{customdata[3]:.0%}"
            "<extra></extra>"
        )
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=top_reorder["product_name"].tolist(),
    )
    fig.update_layout(
        height=max(400, n * 22),
        legend_title_text="Department",
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width='stretch')

    # ── Dynamic insight from the actual top-3 of the current view ──
    top3       = top_reorder.sort_values("reorder_rate", ascending=False).head(3)
    top1       = top3.iloc[0]
    dom_dept   = top_reorder["department"].value_counts()
    dom_name   = dom_dept.index[0]
    dom_count  = int(dom_dept.iloc[0])
    high_share = (top_reorder["reorder_rate"] >= 0.8).sum()

    runners_up = ", ".join(
        f"*{r['product_name']}* ({r['reorder_rate']:.0%})"
        for _, r in top3.iloc[1:].iterrows()
    )

    st.info(
        f"The most-reordered product in this view is "
        f"**{top1['product_name']}** with a reorder rate of "
        f"**{top1['reorder_rate']:.0%}** "
        f"({int(top1['count']):,} purchases, *{top1['department']}*), "
        f"followed by {runners_up}. "
        f"Of the top {len(top_reorder)} products, **{dom_count}** come from "
        f"the *{dom_name}* department, and **{high_share}** have a reorder "
        "rate above **0.8**, the threshold above which products tend to "
        "be everyday staples and become strong candidates for "
        "**subscription models** or **auto-reorder reminders**."
    )
