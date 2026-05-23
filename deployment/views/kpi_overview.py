"""KPI Overview — landing page with headline metrics and a top-5 dept chart."""

import plotly.express as px
import streamlit as st

from data_loaders import _RAW_AVAILABLE, load_csv, load_kpi


def render():
    st.title("Instacart Market Basket — Dashboard Overview")

    st.markdown(
        "This dashboard explores the **Instacart Online Grocery** dataset, "
        "covering over 3 million grocery orders placed by more than 200'000 customers. "
        "Start with **Product Development** to see what sells, then continue with "
        "**Customer Retention** to understand who keeps coming back."
    )

    if _RAW_AVAILABLE:
        # ── Raw-Data-Modus: direkt aus CSVs berechnen ────────────────────────
        orders, products, products_full, order_products = load_csv()

        total_orders     = orders["order_id"].nunique()
        unique_products  = products["product_id"].nunique()
        unique_customers = orders["user_id"].nunique()

        overall_reorder         = order_products["reordered"].mean()
        avg_orders_per_customer = total_orders / unique_customers
        avg_basket_size         = order_products.groupby("order_id").size().mean()

        dept_purchases = (
            order_products
            .merge(products_full[["product_id", "department"]], on="product_id")
            .groupby("department")
            .size()
        )
        dept_share     = dept_purchases / dept_purchases.sum()
        top_department = dept_share.idxmax()
        top_dept_share = dept_share.max()

        peak_dh = orders.groupby(["order_dow", "order_hour_of_day"]).size().idxmax()

    else:
        # ── Precomputed-Modus: voraggerierte Dateien laden ───────────────────
        kpi, dept_share = load_kpi()

        total_orders            = kpi["total_orders"]
        unique_products         = kpi["unique_products"]
        unique_customers        = kpi["unique_customers"]
        overall_reorder         = kpi["overall_reorder"]
        avg_orders_per_customer = kpi["avg_orders_per_customer"]
        avg_basket_size         = kpi["avg_basket_size"]
        top_department          = kpi["top_department"]
        top_dept_share          = kpi["top_dept_share"]
        peak_dh                 = (kpi["peak_dow"], kpi["peak_hour"])

    # ── Peak-Label (gemeinsam für beide Modi) ─────────────────────────────────
    day_names  = ["Sunday", "Monday", "Tuesday", "Wednesday",
                  "Thursday", "Friday", "Saturday"]
    peak_label = f"{day_names[peak_dh[0]]}, {peak_dh[1]:02d}:00"

    # ── Metric grid ──────────────────────────────────────────────────────────
    # Verwendet st.markdown statt st.metric für bessere Versionskompatibilität
    def kpi_card(col, label, value):
        col.markdown(
            f"<div style='background:#1e2130;padding:16px 20px;border-radius:8px;"
            f"border-left:4px solid #4a7c59;margin-bottom:8px'>"
            f"<div style='color:#9ba8b5;font-size:0.82em;margin-bottom:4px'>{label}</div>"
            f"<div style='font-size:1.6em;font-weight:700;color:#ffffff'>{value}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns(3)
    kpi_card(col1, "Total Orders",     f"{total_orders:,}")
    kpi_card(col2, "Unique Products",  f"{unique_products:,}")
    kpi_card(col3, "Unique Customers", f"{unique_customers:,}")

    col4, col5, col6 = st.columns(3)
    kpi_card(col4, "Overall Reorder Rate",   f"{overall_reorder:.1%}")
    kpi_card(col5, "Avg Orders / Customer",  f"{avg_orders_per_customer:.1f}")
    kpi_card(col6, "Avg Products / Order",   f"{avg_basket_size:.1f}")

    col7, col8 = st.columns(2)
    kpi_card(col7, "Top Department", f"{top_department.title()} ({top_dept_share:.0%})")
    kpi_card(col8, "Peak Shopping Time", peak_label)

    # ── Mini chart: top 5 departments by share ───────────────────────────────
    st.divider()
    st.subheader("Sales share — top 5 departments")
    top5 = (
        dept_share.sort_values(ascending=False)
        .head(5)
        .reset_index()
    )
    top5.columns = ["department", "share"]
    top5["share_pct"] = (top5["share"] * 100).round(1)
    top5 = top5.sort_values("share_pct")

    fig = px.bar(
        top5,
        x="share_pct",
        y="department",
        orientation="h",
        text="share_pct",
        labels={"share_pct": "Share of all purchases (%)", "department": ""},
        color="share_pct",
        color_continuous_scale="Oranges",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(
        coloraxis_showscale=False,
        height=290,
        margin=dict(t=10, l=10, r=40, b=10),
        xaxis=dict(range=[0, top5["share_pct"].max() * 1.15]),
    )
    st.plotly_chart(fig, width='stretch')

    st.info(
        "The dataset spans over 200'000 customers and more than 49'000 unique products. "
        "**Produce** alone accounts for almost a third of all purchases, and most shopping "
        "happens on Sunday and Monday mornings. With an average of "
        f"**{avg_orders_per_customer:.0f} orders per customer** and a reorder rate of "
        f"**{overall_reorder:.0%}**, the platform shows a highly habitual customer base, "
        "ideal conditions for loyalty-driven product strategies."
    )
