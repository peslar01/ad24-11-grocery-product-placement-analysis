"""Hidden Gems — niche, high-loyalty products outside the top departments."""

import plotly.express as px
import streamlit as st

from data_loaders import dept_color_map, product_stats


def render():
    st.title("Hidden Gems — Niche Products with Loyal Customers")
    st.markdown(
        "Hidden Gems are products that sit **outside the top-selling departments** "
        "and inside a chosen **purchase-volume range** (so we focus on the long tail, "
        "not blockbusters), yet still achieve exceptionally high reorder rates. "
        "They surface niche categories with small but devoted customer bases, "
        "the strongest candidates for targeted promotions, category newsletters, "
        "and subscription offers."
    )

    stats = product_stats()

    # ── Controls ────────────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        top_n_depts = st.slider(
            "Exclude top N departments by sales", 1, 10, 5,
            help="The N highest-volume departments are removed before ranking. "
                 "Increase this to dig deeper into the long tail.",
        )
    with col_f2:
        purchase_range = st.slider(
            "Purchase-count range (long-tail window)",
            min_value=100, max_value=10000, value=(300, 3000), step=100,
            help="Restrict to products bought within this range. The upper bound "
                 "keeps the focus on niche products, not blockbusters that just "
                 "happened to sit outside the top departments.",
        )
    with col_f3:
        n_products = st.slider("Number of products to show", 5, 40, 20)

    min_purchases, max_purchases = purchase_range

    # ── Identify top-selling departments to exclude ─────────────────────────
    dept_sales = (
        stats.groupby("department")["count"].sum()
        .sort_values(ascending=False)
    )
    top_depts = list(dept_sales.head(top_n_depts).index)

    # Make the exclusion transparent — the user picked "top N" but never
    # got told *which* N. Showing this up-front is critical for reading the result.
    st.caption(
        f"**Excluded departments** (top {top_n_depts} by sales): "
        + ", ".join(f"*{d}*" for d in top_depts)
    )

    # ── Filter to long-tail products outside the top departments ────────────
    in_window = stats[
        (~stats["department"].isin(top_depts)) &
        (stats["count"] >= min_purchases) &
        (stats["count"] <= max_purchases)
    ]
    eligible_count = len(in_window)

    hidden_gems = (
        in_window
        .sort_values("reorder_rate", ascending=False)
        .head(n_products)
        .sort_values("reorder_rate")  # ascending → top bar at top of chart
    )

    if hidden_gems.empty:
        st.warning(
            "No products meet the current filters. "
            "Try widening the purchase-count range or excluding more top departments."
        )
        return

    st.caption(
        f"**{eligible_count:,}** products fall inside the long-tail window "
        f"({min_purchases:,}–{max_purchases:,} purchases) and outside the "
        f"excluded departments, showing the top {len(hidden_gems)} by reorder rate."
    )

    fig = px.bar(
        hidden_gems,
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
        categoryarray=hidden_gems["product_name"].tolist(),
    )
    fig.update_layout(
        height=max(400, n_products * 22),
        legend_title_text="Department",
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width='stretch')

    # ── Dynamic insight from the actual top-3 of the current view ──
    top3      = hidden_gems.sort_values("reorder_rate", ascending=False).head(3)
    top1      = top3.iloc[0]
    dept_mix  = hidden_gems["department"].value_counts()
    dept_count = len(dept_mix)
    dom_dept  = dept_mix.index[0]
    dom_n     = int(dept_mix.iloc[0])

    runners_up = ", ".join(
        f"*{r['product_name']}* ({r['reorder_rate']:.0%}, *{r['department']}*)"
        for _, r in top3.iloc[1:].iterrows()
    )

    st.info(
        f"The top hidden gem in this view is **{top1['product_name']}** "
        f"({top1['reorder_rate']:.0%} reorder rate, "
        f"{int(top1['count']):,} purchases, *{top1['department']}*), "
        f"followed by {runners_up}. "
        f"The top {len(hidden_gems)} gems span **{dept_count}** departments, "
        f"with **{dom_n}** products from *{dom_dept}* — that's the niche "
        "category most worth a closer look (targeted newsletter, category "
        "landing page, or subscription bundle)."
    )
