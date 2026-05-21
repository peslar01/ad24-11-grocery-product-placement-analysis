"""Department Sales — bar charts at department and aisle granularity + treemap."""

import plotly.express as px
import streamlit as st

from data_loaders import aisle_aggregates, dept_color_map


def render():
    # Cached pre-aggregate at (department, aisle) granularity (~134 rows).
    agg = aisle_aggregates()
    n_depts  = agg["department"].nunique()
    n_aisles = agg["aisle"].nunique()

    st.title("Sales by Department & Aisle")
    st.markdown(
        f"Compares total purchase volume across product categories. "
        f"Switch between the **Department** view ({n_depts} broad categories) and the "
        f"**Aisle** view ({n_aisles} finer-grained aisles) to see exactly which sub-categories "
        "drive sales — e.g. *produce* splits into *fresh fruits*, *fresh vegetables*, "
        "*fresh herbs*, *packaged produce* and *packaged vegetables fruits*."
    )

    view = st.radio(
        "View",
        ["Department", "Aisle"],
        horizontal=True,
        help=f"Department = {n_depts} broad categories. Aisle = {n_aisles} sub-categories.",
    )

    if view == "Department":
        _render_department_view(agg)
    else:
        _render_aisle_view(agg)

    _render_treemap(agg)


def _render_department_view(agg):
    dept_agg = (
        agg.groupby("department")
        .agg(
            count=("count", "sum"),
            reorder_sum=("reorder_sum", "sum"),
            share_pct=("share_pct", "sum"),
        )
        .reset_index()
    )
    dept_agg["reorder_rate"] = dept_agg["reorder_sum"] / dept_agg["count"]
    dept_agg = dept_agg.sort_values("count", ascending=True)

    fig = px.bar(
        dept_agg,
        x="count",
        y="department",
        orientation="h",
        color="reorder_rate",
        color_continuous_scale="Oranges",
        custom_data=["share_pct", "reorder_rate"],
        labels={"count": "Number of Purchases", "department": "",
                "reorder_rate": "Reorder rate"},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Purchases: %{x:,}<br>"
            "Share: %{customdata[0]:.1f}%<br>"
            "Reorder rate: %{customdata[1]:.0%}"
            "<extra></extra>"
        )
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=dept_agg["department"].tolist(),
    )
    fig.update_layout(
        height=550,
        coloraxis_colorbar=dict(title="Reorder<br>rate", tickformat=".0%"),
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width='stretch')

    # Dynamic insight from the actual aggregates
    top      = dept_agg.sort_values("count", ascending=False)
    top1     = top.iloc[0]
    top2     = top.iloc[1]
    most_loyal = dept_agg.sort_values("reorder_rate", ascending=False).iloc[0]

    st.info(
        f"**{top1['department'].title()}** is the most purchased department with "
        f"**{int(top1['count']):,}** purchases ({top1['share_pct']:.1f}% of all), "
        f"followed by **{top2['department'].title()}** ({top2['share_pct']:.1f}%). "
        f"The highest reorder rate is in **{most_loyal['department']}** "
        f"({most_loyal['reorder_rate']:.0%}) — its customers are the most habitual, "
        "regardless of total volume. Colour intensity in the chart encodes the "
        "reorder rate so loyalty leaders stand out from volume leaders."
    )


def _render_aisle_view(agg):
    dept_options = ["All departments"] + sorted(agg["department"].unique())
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        dept_filter = st.selectbox(
            "Filter by department",
            dept_options,
            help="Narrow down to the aisles inside a single department (e.g. produce).",
        )
    with col_f2:
        top_n = st.slider("Top N aisles", 5, 50, 20, step=5)

    filtered = agg if dept_filter == "All departments" else agg[agg["department"] == dept_filter]

    aisle_counts = (
        filtered.sort_values("count", ascending=False)
        .head(top_n)
        .sort_values("count", ascending=True)
    )

    if aisle_counts.empty:
        st.warning("No aisles match the current filter.")
        return

    fig = px.bar(
        aisle_counts,
        x="count",
        y="aisle",
        orientation="h",
        color="department",
        color_discrete_map=dept_color_map(),
        custom_data=["share_pct", "reorder_rate", "department"],
        labels={"count": "Number of Purchases", "aisle": "",
                "department": "Department"},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Department: %{customdata[2]}<br>"
            "Purchases: %{x:,}<br>"
            "Share: %{customdata[0]:.2f}%<br>"
            "Reorder rate: %{customdata[1]:.0%}"
            "<extra></extra>"
        )
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=aisle_counts["aisle"].tolist(),
    )
    fig.update_layout(
        height=max(400, len(aisle_counts) * 25),
        legend_title_text="Department",
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width='stretch')

    top_aisle  = aisle_counts.iloc[-1]
    high_reord = aisle_counts.sort_values("reorder_rate", ascending=False).iloc[0]

    if dept_filter == "All departments":
        st.info(
            f"The top aisle is **{top_aisle['aisle']}** "
            f"(*{top_aisle['department']}*) with "
            f"{int(top_aisle['count']):,} purchases "
            f"({top_aisle['share_pct']:.2f}% of all) and a reorder rate of "
            f"**{top_aisle['reorder_rate']:.0%}**. "
            f"Highest reorder rate in this view: **{high_reord['aisle']}** "
            f"({high_reord['reorder_rate']:.0%}) — strongest loyalty signal."
        )
    else:
        st.info(
            f"Within **{dept_filter}**, the leading aisle is "
            f"**{top_aisle['aisle']}** with {int(top_aisle['count']):,} purchases "
            f"({top_aisle['share_pct']:.2f}% of all platform purchases) and a "
            f"reorder rate of **{top_aisle['reorder_rate']:.0%}**. "
            f"Highest reorder in this filter: **{high_reord['aisle']}** "
            f"({high_reord['reorder_rate']:.0%})."
        )


def _render_treemap(agg):
    st.divider()
    st.subheader("Hierarchy: Department → Aisle")
    st.caption(
        "Each large block is a department; the smaller blocks inside are its aisles. "
        "Block size = number of purchases · Labels show share-% · Hover for reorder rate."
    )

    tree_fig = px.treemap(
        agg,
        path=["department", "aisle"],
        values="count",
        color="department",
        color_discrete_map=dept_color_map(),
        custom_data=["share_pct", "reorder_rate", "count"],
    )
    tree_fig.update_traces(
        root_color="lightgrey",
        texttemplate="<b>%{label}</b><br>%{customdata[0]:.1f}%",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Purchases: %{value:,}<br>"
            "Share: %{customdata[0]:.2f}%<br>"
            "Reorder rate: %{customdata[1]:.0%}"
            "<extra></extra>"
        ),
    )
    tree_fig.update_layout(
        height=650,
        margin=dict(t=20, l=10, r=10, b=10),
    )
    st.plotly_chart(tree_fig, width='stretch')
