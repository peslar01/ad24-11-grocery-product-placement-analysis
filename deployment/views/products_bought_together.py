"""Products Bought Together — top-pairs table, dept × dept heatmap, network."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from data_loaders import (
    aisle_enrichment, build_aisle_network_data, dept_pair_matrix, top_aisle_pairs,
)
from defs_aisle_network import build_figure, cluster_summary, name_clusters


def render():
    st.title("Aisles Bought Together")

    st.markdown(
        "Three views of the same question, *what is bought with what?*, "
        "from concrete to conceptual:\n\n"
        "1. **Top Co-Purchase Pairs**, a ranked table of the strongest aisle pairs (the answer most personas want)\n"
        "2. **Department Heatmap**, a bird's-eye view of which categories overlap in orders\n"
        "3. **Advanced**, the full aisle-level co-purchase network, with clusters and a focus selector"
    )

    _render_lift_explainer()
    _render_top_pairs()
    _render_dept_heatmap()
    _render_advanced_network()


def _render_lift_explainer():
    with st.expander("What is lift, and how do I read this?"):
        st.markdown(
            """
For every pair of aisles, we count how many orders contain **both**, then
compute the **lift**, how much more often they are bought together than
random chance would predict.

| Lift value | Meaning |
|---|---|
| **= 1.0** | No association, co-occurrence is pure coincidence |
| **> 1.0** | Positive association, bought together more than expected |
| **> 2.0** | Strong association, a good cross-sell candidate |
| **> 3.0** | Very strong, nearly always purchased together |

> Example: Lift of 2.5 for *fresh fruits + yogurt* means orders contain both
> **2.5× more often** than chance would predict.

**How to use the results.** A high-lift pair is a cross-sell candidate
("Customers who buy from A also buy from B"). The **department heatmap**
shows the same story at a coarser, more business-friendly level. The
**network view** in the Advanced section reveals natural shopping baskets
(clusters) and is best when you want to explore.
            """
        )


def _render_top_pairs():
    st.subheader("1 · Top Co-Purchase Pairs")
    st.caption(
        "The strongest aisle-pair associations in the dataset. "
        "**Lift > 1** means the pair is bought together more often than "
        "chance would predict. Higher = stronger. Sort the table by any column."
    )

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        pairs_min_count = st.slider(
            "Pairs · min co-orders", 500, 20000, 2000, step=500,
            help="Drop aisle pairs that share fewer than this many orders.",
        )
    with col_p2:
        pairs_min_lift = st.slider(
            "Pairs · min lift", 1.0, 3.0, 1.3, step=0.1,
            help="Drop pairs with weaker association than this.",
        )
    with col_p3:
        pairs_top_n = st.slider("Show top N pairs", 5, 50, 15, step=5)

    pairs_df = top_aisle_pairs(pairs_min_count, pairs_min_lift)
    if pairs_df.empty:
        st.warning("No pairs match the current thresholds. Lower min co-orders or min lift.")
        return

    top = pairs_df.head(pairs_top_n).copy()
    top.index = range(1, len(top) + 1)
    top = top.rename(columns={
        "aisle_a":         "Aisle A",
        "department_a":    "Dept A",
        "aisle_b":         "Aisle B",
        "department_b":    "Dept B",
        "co_orders":       "Co-orders",
        "share_of_orders": "Share of orders",
        "lift":            "Lift",
    })
    st.dataframe(
        top,
        column_config={
            "Co-orders": st.column_config.NumberColumn(format="%d"),
            "Share of orders": st.column_config.NumberColumn(
                format="%.2f %%",
                help="Percent of all orders containing both aisles.",
            ),
            "Lift": st.column_config.NumberColumn(format="%.2f"),
        },
        width='stretch',
        height=min(400, 38 * (len(top) + 1) + 40),
    )

    row = pairs_df.iloc[0]
    st.info(
        f"Strongest pair in the dataset: **{row['aisle_a']}** + "
        f"**{row['aisle_b']}** with lift **{row['lift']:.2f}**, bought together "
        f"in {row['co_orders']:,} orders ({row['share_of_orders']:.2f}% of all). "
        "Strong-lift cross-department pairs (different *Dept A* and *Dept B*) "
        "are the most actionable cross-sell opportunities."
    )


def _render_dept_heatmap():
    st.divider()
    st.subheader("2 · Department × Department Heatmap")
    st.caption(
        "Bird's-eye view, how strongly each department co-occurs with every other "
        "in shared orders. Brighter = more aisle-pair co-purchases. "
        "The diagonal (a department with itself) is usually brightest: multiple "
        "aisles inside the same department naturally co-occur."
    )

    M = dept_pair_matrix()
    # Order departments by total off-diagonal interaction so big hitters cluster.
    off_diag_sum = M.sum(axis=1) - pd.Series({d: M.loc[d, d] for d in M.index})
    order = off_diag_sum.sort_values(ascending=False).index.tolist()
    M_sorted = M.loc[order, order]

    # Log-scale the colour so low/medium values become readable alongside the
    # huge produce ↔ dairy cell. Hover still shows raw counts via customdata.
    log_M = np.log1p(M_sorted.values)

    heat = px.imshow(
        log_M,
        x=M_sorted.columns.tolist(),
        y=M_sorted.index.tolist(),
        color_continuous_scale="YlOrRd",
        aspect="equal",
        labels=dict(x="Department B", y="Department A",
                    color="Co-occurrences (log scale)"),
    )
    heat.update_traces(
        customdata=M_sorted.values,
        hovertemplate=(
            "<b>%{y}</b> ↔ <b>%{x}</b><br>"
            "Aisle-pair co-occurrences: %{customdata:,.0f}"
            "<extra></extra>"
        ),
    )
    heat.update_layout(
        height=600, margin=dict(t=20, l=10, r=10, b=10),
        coloraxis_colorbar=dict(
            title="Co-occurrences<br>(log scale)",
            tickvals=[np.log1p(v) for v in (1e3, 1e4, 1e5, 1e6, 1e7)],
            ticktext=["1K", "10K", "100K", "1M", "10M"],
        ),
    )
    st.plotly_chart(heat, width='stretch')

    # Find brightest off-diagonal cell for a story-style takeaway
    M_off = M_sorted.copy()
    for d in M_off.index:
        M_off.loc[d, d] = 0
    max_val = M_off.values.max()
    max_idx = M_off.stack().idxmax()
    st.info(
        f"The strongest cross-department co-purchase pairing is "
        f"**{max_idx[0]} ↔ {max_idx[1]}** ({int(max_val):,} aisle-pair "
        "co-occurrences). Patterns to look for: produce ↔ dairy eggs ↔ meat "
        "(the *cooking* cluster), and beverages ↔ snacks ↔ frozen "
        "(the *convenience* cluster)."
    )


def _render_advanced_network():
    st.divider()
    with st.expander("3 · Advanced — exploratory aisle co-purchase network"):
        st.info(
            "**Why this is an exploratory view, not the primary one.** "
            "Force-directed networks look impressive but their node positions "
            "carry no semantic meaning, they're a layout artefact (seed-dependent), "
            "not data. For *static* communication of the same information, the "
            "**Top Pairs table** and the **Department Heatmap** above are the "
            "stronger choices: their position and colour encodings map directly "
            "to data values. We've also deliberately left out a 3D variant, the "
            "third dimension would add visual complexity without carrying any "
            "additional information, and 3D screenshots are unusable in static "
            "reports."
        )

        st.markdown(
            "That said, the network is useful for *exploration*: rotating clusters, "
            "spotting communities, and tracing one aisle's 1-hop neighbourhood. "
            "Edges are thicker when the lift is higher. Communities are detected "
            "with weighted greedy modularity. Use **Focus on aisle** in the "
            "sidebar to highlight one aisle's connections."
        )

        label_top_n = st.slider(
            "Show labels for top N aisles",
            5, 60, 20, step=5,
            help="Only the largest aisles get a visible label so the chart "
                 "stays readable. Other aisles still appear as markers, "
                 "hover them for details.",
        )

        with st.sidebar:
            st.divider()
            st.subheader("Network parameters")
            min_count = st.slider("Network · min co-orders",
                                  500, 20000, 1500, step=500)
            min_lift  = st.slider("Network · min lift", 1.0, 3.0, 1.3, step=0.1)

        nodes, edges, node_comm, pos, count_a, aid2name = build_aisle_network_data(
            min_count, min_lift, dim=2,
        )
        aisle_info    = aisle_enrichment()
        cluster_names = name_clusters(nodes, node_comm, aisle_info)

        with st.sidebar:
            focus_options = ["— none —"] + [
                aid2name[nd] for nd in sorted(nodes, key=lambda nd: aid2name[nd])
            ]
            focus_label = st.selectbox(
                "Focus on aisle",
                focus_options,
                help="Highlight one aisle's 1-hop neighbourhood; everything else fades.",
            )
        focus_aisle_id = None
        if focus_label != "— none —":
            for nd in nodes:
                if aid2name[nd] == focus_label:
                    focus_aisle_id = nd
                    break

        fig = build_figure(
            nodes, edges, node_comm, pos, count_a, aid2name,
            aisle_info=aisle_info,
            cluster_names=cluster_names,
            focus_aisle_id=focus_aisle_id,
            label_top_n=label_top_n,
        )
        summary = cluster_summary(
            nodes, node_comm, count_a, aid2name,
            aisle_info=aisle_info,
            cluster_names=cluster_names,
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("Aisles (nodes)", len(nodes))
        col2.metric("Co-purchase links", len(edges))
        col3.metric("Clusters found", len(summary))

        st.plotly_chart(fig, width='stretch')

        st.subheader("Clusters in this view")
        for c in summary:
            st.markdown(
                f"<span style='display:inline-block;width:12px;height:12px;"
                f"border-radius:50%;background:{c['colour']};margin-right:8px'></span>"
                f"**Cluster {c['cluster']} — {c['name']}** · {c['size']} aisles",
                unsafe_allow_html=True,
            )
            for dept, aisle_names in c["by_department"]:
                st.caption(f"*{dept}* — {', '.join(aisle_names)}")
