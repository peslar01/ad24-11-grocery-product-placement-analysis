"""Top Sellers — most frequently purchased products, filterable by department."""

import plotly.express as px
import streamlit as st

from data_loaders import dept_color_map, product_stats


def render():
    st.title("Top Products by Number of Purchases")
    st.markdown(
        "Shows the most frequently purchased individual products across all orders. "
        "Filter by department to find the top sellers within a single category, "
        "useful for product managers focused on a specific assortment."
    )

    stats = product_stats()

    # ── Controls ────────────────────────────────────────────────────────────
    dept_options = ["All departments"] + sorted(stats["department"].unique())
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        dept_filter = st.selectbox(
            "Filter by department",
            dept_options,
            help="Narrow down to the top sellers within a single department.",
        )
    with col_f2:
        n = st.slider("Number of products", 5, 50, 20, step=5)

    if dept_filter != "All departments":
        stats = stats[stats["department"] == dept_filter]

    top_products = (
        stats.sort_values("count", ascending=False)
        .head(n)
        .sort_values("count")  # ascending → top bar at top of chart
    )

    if top_products.empty:
        st.warning("No products match the current filter.")
        return

    fig = px.bar(
        top_products,
        x="count",
        y="product_name",
        orientation="h",
        color="department",
        color_discrete_map=dept_color_map(),
        custom_data=["share_pct", "reorder_rate", "aisle", "department"],
        labels={
            "count": "Number of Purchases",
            "product_name": "",
            "department": "Department",
        },
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Department: %{customdata[3]}<br>"
            "Aisle: %{customdata[2]}<br>"
            "Purchases: %{x:,}<br>"
            "Share of all purchases: %{customdata[0]:.2f}%<br>"
            "Reorder rate: %{customdata[1]:.0%}"
            "<extra></extra>"
        )
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=top_products["product_name"].tolist(),
    )
    fig.update_layout(
        height=max(400, len(top_products) * 25),
        legend_title_text="Department",
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width='stretch')

    # ── Dynamic insight from the actual top-3 of the current view ──
    top3   = top_products.sort_values("count", ascending=False).head(3)
    top1   = top3.iloc[0]
    depts_in_view = top_products["department"].value_counts()
    dom_dept      = depts_in_view.index[0]
    dom_count     = int(depts_in_view.iloc[0])

    if dept_filter == "All departments":
        runners_up = ", ".join(
            f"*{r['product_name']}*" for _, r in top3.iloc[1:].iterrows()
        )
        st.info(
            f"The most purchased product is **{top1['product_name']}** "
            f"with **{int(top1['count']):,}** purchases "
            f"({top1['share_pct']:.2f}% of all) and a reorder rate of "
            f"**{top1['reorder_rate']:.0%}**, followed by {runners_up}. "
            f"Of the shown top {len(top_products)} products, "
            f"**{dom_count}** come from the *{dom_dept}* department, "
            "fresh products clearly dominate the platform's top sellers."
        )
    else:
        st.info(
            f"In **{dept_filter}**, the top seller is "
            f"**{top1['product_name']}** with {int(top1['count']):,} purchases "
            f"({top1['share_pct']:.2f}% of all platform purchases, "
            f"reorder rate **{top1['reorder_rate']:.0%}**). "
            "Hover the bars for share-% and reorder-rate of each product, "
            "products with a high reorder rate are strong subscription candidates."
        )
