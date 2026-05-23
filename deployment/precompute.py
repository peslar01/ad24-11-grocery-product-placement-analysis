"""
precompute.py — Einmalig lokal ausführen, um alle voraggerierten Daten zu erzeugen
====================================================================================

Dieses Script lädt die rohen Instacart-CSVs (müssen lokal in data/ vorhanden sein)
und berechnet alle Aggregationen, die das Dashboard braucht. Die Ergebnisse werden
als kleine CSV/JSON-Dateien in deployment/data_precomputed/ gespeichert.

Diese voraggerierten Dateien werden ins Git committed (wenige MB statt 2.8 GB),
damit das Dashboard auf Streamlit Cloud ohne Rohdaten läuft.

Ausführung (vom Projekt-Root):
    uv run python deployment/precompute.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# deployment/ zum Python-Pfad hinzufügen, damit data_loaders importiert werden kann
sys.path.insert(0, str(Path(__file__).parent))

from data_loaders import (
    aisle_aggregates,
    aisle_enrichment,
    build_aisle_network_data,
    dept_pair_matrix,
    load_csv,
    product_stats,
    top_aisle_pairs,
    DATA_DIR,
)
from defs_aisle_network import compute_aisle_pairs

OUT = Path(__file__).parent / "data_precomputed"
OUT.mkdir(exist_ok=True)

print("=" * 60)
print("PODSV Precompute Script")
print("=" * 60)


# ── 1. Rohdaten laden ────────────────────────────────────────────────────────
print("\n[1/8] Lade Rohdaten …")
orders, products, products_full, order_products = load_csv()
print(f"      orders: {len(orders):,} Zeilen")
print(f"      order_products: {len(order_products):,} Zeilen")


# ── 2. KPI-Skalare (für kpi_overview.py) ────────────────────────────────────
print("\n[2/8] Berechne KPI-Skalare …")
total_orders     = int(orders["order_id"].nunique())
unique_products  = int(products["product_id"].nunique())
unique_customers = int(orders["user_id"].nunique())
overall_reorder  = float(order_products["reordered"].mean())
avg_basket_size  = float(order_products.groupby("order_id").size().mean())

dept_purchases = (
    order_products
    .merge(products_full[["product_id", "department"]], on="product_id")
    .groupby("department")
    .size()
)
dept_share     = dept_purchases / dept_purchases.sum()
top_department = str(dept_share.idxmax())
top_dept_share = float(dept_share.max())

peak_dh = orders.groupby(["order_dow", "order_hour_of_day"]).size().idxmax()

kpi = {
    "total_orders":             total_orders,
    "unique_products":          unique_products,
    "unique_customers":         unique_customers,
    "overall_reorder":          overall_reorder,
    "avg_orders_per_customer":  total_orders / unique_customers,
    "avg_basket_size":          avg_basket_size,
    "top_department":           top_department,
    "top_dept_share":           top_dept_share,
    "peak_dow":                 int(peak_dh[0]),
    "peak_hour":                int(peak_dh[1]),
}
(OUT / "kpi.json").write_text(json.dumps(kpi, indent=2))
print(f"      kpi.json gespeichert: {kpi}")

# Department-Anteile für das Mini-Chart in kpi_overview
dept_share_df = dept_share.reset_index()
dept_share_df.columns = ["department", "share"]
dept_share_df.to_csv(OUT / "dept_share.csv", index=False)
print(f"      dept_share.csv gespeichert ({len(dept_share_df)} Zeilen)")


# ── 3. Product Stats (für top_sellers, reorder_rate, hidden_gems) ────────────
print("\n[3/8] Berechne product_stats …")
ps = product_stats()
ps.to_csv(OUT / "product_stats.csv", index=False)
print(f"      product_stats.csv gespeichert ({len(ps):,} Zeilen)")


# ── 4. Aisle Aggregates (für department_sales + aisle_enrichment) ────────────
print("\n[4/8] Berechne aisle_aggregates …")
aa = aisle_aggregates()
# aisle_id hinzufügen (wird von aisle_enrichment() benötigt)
aid_map = products_full[["aisle_id", "aisle"]].drop_duplicates()
aa_with_id = aa.merge(aid_map, on="aisle")
aa_with_id.to_csv(OUT / "aisle_aggregates.csv", index=False)
print(f"      aisle_aggregates.csv gespeichert ({len(aa_with_id)} Zeilen, inkl. aisle_id)")


# ── 5. Aisle Co-Purchase Pairs (schwerer Schritt — ~30–60 s) ─────────────────
print("\n[5/8] Berechne Aisle Co-Purchase Pairs (dauert ~1 Minute) …")
pairs, count_a, n_orders, aid2name = compute_aisle_pairs(str(DATA_DIR))
print(f"      {len(pairs):,} Paare gefunden, {n_orders:,} Orders")

# Paare als JSON: Schlüssel "{a},{b}", Wert = count
pairs_json = {f"{a},{b}": int(c) for (a, b), c in pairs.items()}
(OUT / "aisle_pairs.json").write_text(json.dumps(pairs_json))
print(f"      aisle_pairs.json gespeichert ({len(pairs_json):,} Einträge)")

(OUT / "aisle_count_a.json").write_text(
    json.dumps({str(k): int(v) for k, v in count_a.items()})
)
(OUT / "aisle_n_orders.json").write_text(json.dumps(n_orders))
(OUT / "aid2name.json").write_text(
    json.dumps({str(k): v for k, v in aid2name.items()})
)
print("      aisle_count_a.json, aisle_n_orders.json, aid2name.json gespeichert")


# ── 6. Shopping Heatmaps (für shopping_time.py, 3 Varianten) ─────────────────
print("\n[6/8] Berechne Shopping Heatmaps …")
for label, mask in [
    ("all",    None),
    ("first",  orders["order_number"] == 1),
    ("repeat", orders["order_number"] > 1),
]:
    o = orders if mask is None else orders[mask]
    pivot = (
        o.groupby(["order_dow", "order_hour_of_day"])["order_id"]
        .count()
        .unstack(fill_value=0)
        .reindex(index=range(7), columns=range(24), fill_value=0)
    )
    pivot.to_csv(OUT / f"shopping_heatmap_{label}.csv")
    print(f"      shopping_heatmap_{label}.csv gespeichert "
          f"({int(o['order_id'].nunique()):,} Orders)")


# ── 7. Top Aisle Pairs und Dept-Matrix (aus Pairs-Cache) ─────────────────────
print("\n[7/8] Berechne top_aisle_pairs und dept_pair_matrix …")
tap = top_aisle_pairs()
tap.to_csv(OUT / "top_aisle_pairs.csv", index=False)
print(f"      top_aisle_pairs.csv gespeichert ({len(tap):,} Zeilen)")

dpm = dept_pair_matrix()
dpm.to_csv(OUT / "dept_pair_matrix.csv")
print(f"      dept_pair_matrix.csv gespeichert ({dpm.shape[0]}×{dpm.shape[1]})")


# ── 8. Zusammenfassung ───────────────────────────────────────────────────────
print("\n[8/8] Fertig!")
total_size = sum(f.stat().st_size for f in OUT.iterdir()) / 1024 / 1024
print(f"\nAlle Dateien in: {OUT}")
print(f"Gesamtgrösse: {total_size:.1f} MB")
print("\nNächste Schritte:")
print("  git add deployment/data_precomputed/")
print("  git commit -m 'add precomputed data for Streamlit Cloud deployment'")
print("  git push")
