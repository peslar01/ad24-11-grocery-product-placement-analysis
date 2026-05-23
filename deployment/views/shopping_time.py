"""Shopping Time Heatmap — order density by day × hour, with side marginals."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_loaders import _RAW_AVAILABLE, load_csv, load_shopping_heatmap


_DAY_NAMES = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]


def render():
    st.title("Order Frequency by Day and Time")
    st.markdown(
        "Shows when customers place orders across the week. "
        "Darker cells mean more orders. The bars at the top sum each hour "
        "across all days; the bars on the right sum each day across all hours. "
        "Switch the **Customer type** toggle to compare *first-time* customers "
        "(new arrivals) with *repeat* customers (returners), the two groups "
        "often shop at different times."
    )
    st.caption(
        "*Methodology note*: `order_dow = 0` is Sunday in the Instacart dataset, "
        "so the week starts on Sunday here. Times are local to each customer."
    )

    # ── Customer-type toggle (analytical depth) ─────────────────────────────
    customer_type = st.radio(
        "Customer type",
        ["All orders", "First-time customers", "Repeat customers"],
        horizontal=True,
        help=(
            "First-time = the user's very first order (order_number = 1). "
            "Repeat = any subsequent order. Useful for separating *acquisition* "
            "patterns from *retention* patterns."
        ),
    )

    if _RAW_AVAILABLE:
        # ── Raw-Data-Modus: direkt aus orders.csv berechnen ─────────────────
        orders, _, _, _ = load_csv()

        if customer_type == "First-time customers":
            orders_view = orders[orders["order_number"] == 1]
        elif customer_type == "Repeat customers":
            orders_view = orders[orders["order_number"] > 1]
        else:
            orders_view = orders

        heatmap_data = (
            orders_view.groupby(["order_dow", "order_hour_of_day"])["order_id"]
            .count()
            .unstack(fill_value=0)
            .reindex(index=range(7), columns=range(24), fill_value=0)
        )
        heatmap_data.index = _DAY_NAMES
        n_orders_in_view = int(orders_view["order_id"].nunique())

    else:
        # ── Precomputed-Modus: voraggerierter Pivot ──────────────────────────
        heatmap_data   = load_shopping_heatmap(customer_type)
        n_orders_in_view = int(heatmap_data.values.sum())

    fig = _build_figure(heatmap_data)
    st.plotly_chart(fig, width='stretch')

    _render_insight(heatmap_data, n_orders_in_view, customer_type)


def _build_figure(heatmap_data):
    """Assemble the 2×2 subplot grid: top bars · heatmap · right bars."""
    hour_totals = heatmap_data.sum(axis=0)
    day_totals  = heatmap_data.sum(axis=1)

    fig = make_subplots(
        rows=2, cols=2,
        column_widths=[0.85, 0.15],
        row_heights=[0.18, 0.82],
        horizontal_spacing=0.02,
        vertical_spacing=0.03,
        specs=[[{"type": "bar"}, None],
               [{"type": "heatmap"}, {"type": "bar"}]],
    )

    # Top: hour totals
    fig.add_trace(
        go.Bar(
            x=list(hour_totals.index),
            y=hour_totals.values,
            marker_color="#FB6A4A",
            hovertemplate="Hour %{x:02d}:00<br>Orders (all days): %{y:,}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # Center: the actual heatmap
    fig.add_trace(
        go.Heatmap(
            z=heatmap_data.values,
            x=list(heatmap_data.columns),
            y=list(heatmap_data.index),
            colorscale="YlOrRd",
            colorbar=dict(title="Orders", x=1.08, len=0.75, y=0.4),
            hovertemplate=(
                "<b>%{y}, %{x:02d}:00</b><br>"
                "Orders: %{z:,}"
                "<extra></extra>"
            ),
        ),
        row=2, col=1,
    )

    # Right: day totals (horizontal bars, aligned to the heatmap rows)
    fig.add_trace(
        go.Bar(
            y=list(day_totals.index),
            x=day_totals.values,
            orientation="h",
            marker_color="#FB6A4A",
            hovertemplate="%{y}<br>Orders (all hours): %{x:,}<extra></extra>",
            showlegend=False,
        ),
        row=2, col=2,
    )

    # Axes cosmetics
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=1, col=1, title_text="")
    fig.update_xaxes(title_text="Hour of Day", dtick=2, row=2, col=1)
    fig.update_yaxes(title_text="", autorange="reversed", row=2, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=2)
    fig.update_yaxes(showticklabels=False, autorange="reversed", row=2, col=2)

    fig.update_layout(
        height=520,
        margin=dict(t=20, l=10, r=10, b=10),
        bargap=0.1,
    )
    return fig


def _render_insight(heatmap_data, n_total, customer_type):
    """Compute peaks + concentration from the data and render the info box."""
    if heatmap_data.values.sum() == 0:
        st.warning("No orders match the current customer-type filter.")
        return

    hour_totals = heatmap_data.sum(axis=0)
    day_totals  = heatmap_data.sum(axis=1)

    # Peak day / hour / cell
    peak_day_name = day_totals.idxmax()
    peak_day_val  = int(day_totals.max())
    peak_hour     = int(hour_totals.idxmax())
    peak_hour_val = int(hour_totals.max())

    flat = heatmap_data.stack()
    peak_cell_day, peak_cell_hour = flat.idxmax()
    peak_cell_val = int(flat.max())

    # Concentration: how heavy is the busiest single hour-band?
    top6_hours = hour_totals.nlargest(6).sum()
    core_share = top6_hours / hour_totals.sum() * 100

    # Tailor the recommendation to the customer type so the text actually
    # changes — not just the numbers.
    if customer_type == "First-time customers":
        recommendation = (
            "First-time orders skew toward the *weekend*, these are people "
            "trying the service when they have time to set up an account. "
            "**Acquisition campaigns** targeting Saturday and early Sunday "
            "are likely to convert best."
        )
    elif customer_type == "Repeat customers":
        recommendation = (
            "Repeat orders cluster tightly around the weekly-grocery slot "
            ", habitual customers planning the week. "
            "**Retention campaigns** (reorder reminders, basket pre-fills) "
            "should land on Saturday evening, just before the planning peak."
        )
    else:
        recommendation = (
            "Promotional pushes on Saturday evening could capture early "
            "weekend planners before the Sunday peak, while reorder "
            "reminders are best timed to land just before the user's "
            "personal weekly slot."
        )

    st.info(
        f"In this view (**{customer_type.lower()}**, {n_total:,} orders), "
        f"the busiest day is **{peak_day_name}** ({peak_day_val:,} orders) "
        f"and the busiest hour is **{peak_hour:02d}:00** "
        f"({peak_hour_val:,} orders across all days). "
        f"The single hottest slot is **{peak_cell_day} {peak_cell_hour:02d}:00** "
        f"with {peak_cell_val:,} orders. "
        f"The top **6 hours** of the day absorb **{core_share:.0f}%** of all "
        "orders , shopping is highly concentrated. "
        + recommendation
    )
