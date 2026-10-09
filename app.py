"""
Post-Marketing ICSR Donut Chart Generator
=========================================
Upload the AE tracking table + mapping table, pick a date range,
get a nested donut chart.
"""
import io
import re
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="ICSR Donut Chart", layout="centered", page_icon="📊")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_name(s):
    """Strip spaces / unify for sheet-name fuzzy matching."""
    return re.sub(r'\s+', '', str(s)).strip().lower()


def find_sheet_by_name(xl, target):
    """Fuzzy match sheet name (ignore spaces & case)."""
    norm_target = normalize_name(target)
    for name in xl.sheet_names:
        if normalize_name(name) == norm_target:
            return name
    # fallback: contains
    for name in xl.sheet_names:
        if norm_target in normalize_name(name):
            return name
    raise ValueError(f"Sheet '{target}' not found. Available: {xl.sheet_names}")


def detect_columns(df_header_row):
    """Return (date_col_idx, source_col_idx) by scanning header text."""
    date_col, source_col = None, None
    for idx, val in enumerate(df_header_row):
        s = str(val).lower()
        if source_col is None and '来源' in str(val):
            source_col = idx
        if date_col is None and ('获知日期' in str(val) or 'received date' in s):
            date_col = idx
    return date_col, source_col


def build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title_text, inside_thresh=8):
    """
    outer_labels: list of product names
    outer_vals:   list of totals
    inner_labels_map: {product: [category labels]}
    inner_vals_map:   {product: [category values]}
    """
    # Flatten inner in outer order
    flat_labels, flat_vals, flat_colors = [], [], []
    # color families — build a light-to-dark gradient per product
    base_colors = ['#E8792B', '#4A86C7', '#7FB069', '#9B7CC4', '#D46A6A', '#5FA8A0']
    def shade(hexcolor, factor):
        """Lighten (factor>1) or darken (factor<1) a hex color."""
        h = hexcolor.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f'#{r:02x}{g:02x}{b:02x}'

    for pi, prod in enumerate(outer_labels):
        base = base_colors[pi % len(base_colors)]
        cats = inner_labels_map[prod]
        vals = inner_vals_map[prod]
        n = len(cats)
        for ci, (c, v) in enumerate(zip(cats, vals)):
            flat_labels.append(f'{c}\n{v}')
            flat_vals.append(v)
            # gradient: first slice = base color, later slices progressively lighter
            if n == 1:
                factor = 1.0
            else:
                factor = 1.0 + 0.5 * ci / (n - 1)
            flat_colors.append(shade(base, factor))

    outer_colors = [base_colors[i % len(base_colors)] for i in range(len(outer_vals))]
    total = sum(outer_vals)

    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=200)
    ax.set_aspect('equal')

    outer_wedge = dict(width=0.30, edgecolor='white', linewidth=2)
    res_outer = ax.pie(outer_vals, radius=1.0, colors=outer_colors,
                       wedgeprops=outer_wedge, startangle=90, counterclock=False)

    inner_wedge = dict(width=0.30, edgecolor='white', linewidth=1.5)
    res_inner = ax.pie(flat_vals, radius=0.70, colors=flat_colors,
                       wedgeprops=inner_wedge, startangle=90, counterclock=False)

    ax.text(0, 0, f'Total {total}', ha='center', va='center',
            fontsize=18, fontweight='bold', color='#222222')

    # Outer labels inside the ring (no bold)
    for i, w in enumerate(res_outer[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        x = 0.85 * np.cos(np.deg2rad(ang))
        y = 0.85 * np.sin(np.deg2rad(ang))
        ax.text(x, y, f'{outer_labels[i]}\n{outer_vals[i]}',
                ha='center', va='center', fontsize=10, color='black')

    # Inner labels: slices >= threshold go inside; smaller slices get leader lines
    outside_items = []
    for i, w in enumerate(res_inner[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        size = (w.theta2 - w.theta1)
        r_in = 0.55
        if size >= inside_thresh:
            x = r_in * np.cos(np.deg2rad(ang))
            y = r_in * np.sin(np.deg2rad(ang))
            label = flat_labels[i]
            # wrap long labels
            if len(label.split('\n')[0]) > 12:
                parts = label.split('\n')
                words = parts[0].split()
                mid = len(words) // 2
                label = ' '.join(words[:mid]) + '\n' + ' '.join(words[mid:]) + '\n' + parts[1]
            ax.text(x, y, label, ha='center', va='center',
                    fontsize=7.5, color='black')
        else:
            outside_items.append((ang, flat_labels[i]))

    # small slices: clean short leader lines, no bold, spread out
    if outside_items:
        right = [(a, l) for a, l in outside_items if np.cos(np.deg2rad(a)) > 0]
        left  = [(a, l) for a, l in outside_items if np.cos(np.deg2rad(a)) <= 0]
        for group, side in [(right, 'right'), (left, 'left')]:
            if not group:
                continue
            group.sort(key=lambda t: np.sin(np.deg2rad(t[0])))
            n = len(group)
            ys = np.linspace(-0.5, 0.5, n) if n > 1 else [np.sin(np.deg2rad(group[0][0]))]
            x_text = 1.12 if side == 'right' else -1.12
            ha = 'left' if side == 'right' else 'right'
            for (ang, label), yt in zip(group, ys):
                xa = 0.70 * np.cos(np.deg2rad(ang))
                ya = 0.70 * np.sin(np.deg2rad(ang))
                ax.annotate(label, xy=(xa, ya), xytext=(x_text, yt),
                            fontsize=7, color='black',
                            arrowprops=dict(arrowstyle='-', color='#999', lw=0.6),
                            ha=ha, va='center')

    ax.set_title(title_text, fontsize=13, color='#333', pad=18)
    fig.text(0.92, 0.04, '*NSADR = non-serious adverse drug reaction; SADR = serious',
             ha='right', fontsize=7, color='#555', style='italic')
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.title("Post-Marketing ICSR Donut Chart")
st.write("Upload the AE tracking table, optionally upload a mapping table, select date range, then generate.")

DEFAULT_MAP_PATH = r"C:\Users\liul3\Desktop\旭日图自动生成工具\map.xlsx"

f_tracking = st.file_uploader("Upload AE Tracking Table (.xlsx)", type=['xlsx'])
f_mapping = st.file_uploader("Upload Mapping Table (.xlsx) — leave empty to use default", type=['xlsx'])

col1, col2, col3 = st.columns(3)
with col1:
    start_date = st.date_input("Start date", value=pd.Timestamp("2026-04-01"))
with col2:
    end_date = st.date_input("End date", value=pd.Timestamp("2026-08-31"))
with col3:
    label_threshold = st.slider("Leader-line threshold (degrees)", 0, 20, 8,
                                help="Slices smaller than this angle get a leader line. Drag to 0 to put everything inside.")

if st.button("Generate Chart", type="primary"):
    if not f_tracking:
        st.error("Please upload the tracking table first.")
        st.stop()

    # --- Read mapping: uploaded file, else default path ---
    import os
    if f_mapping is not None:
        map_source = f_mapping
        st.write("**Using uploaded mapping table.**")
    else:
        if os.path.exists(DEFAULT_MAP_PATH):
            map_source = DEFAULT_MAP_PATH
            st.write(f"**Using default mapping:** `{DEFAULT_MAP_PATH}`")
        else:
            st.error(f"No mapping uploaded and default file not found:\n{DEFAULT_MAP_PATH}")
            st.stop()

    map_df = pd.read_excel(map_source, header=0)
    map_df.columns = [str(c).strip() for c in map_df.columns]
    st.write("**Mapping table preview:**")
    st.dataframe(map_df)

    # expected columns: 产品, 分类, 来源(sheet来源值), 使用sheet
    prod_col = map_df.columns[0]
    cat_col  = map_df.columns[1]
    src_col  = map_df.columns[2]
    sheet_col = map_df.columns[3]

    # forward-fill product & category
    map_df[prod_col] = map_df[prod_col].ffill()
    map_df[cat_col] = map_df[cat_col].ffill()

    # --- Open tracking workbook ---
    xl = pd.ExcelFile(f_tracking)

    # cache per-sheet parsed data
    sheet_cache = {}

    def get_sheet_counts(sheet_name, source_value, start, end):
        """Count rows in sheet where source col == source_value, within date range."""
        if sheet_name not in sheet_cache:
            actual = find_sheet_by_name(xl, sheet_name)
            df = pd.read_excel(xl, sheet_name=actual, header=None)
            header_row = df.iloc[1]
            date_idx, src_idx = detect_columns(header_row)
            if date_idx is None or src_idx is None:
                st.error(f"Could not auto-detect date/source column in sheet '{actual}'. "
                         f"Header row: {list(header_row.dropna())}")
                st.stop()
            data = df.iloc[2:].copy()
            dates = pd.to_datetime(data.iloc[:, date_idx], errors='coerce')
            sources = data.iloc[:, src_idx]
            sheet_cache[sheet_name] = (dates, sources)
        dates, sources = sheet_cache[sheet_name]
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
        sv = str(source_value).strip()
        return int(((sources.astype(str).str.strip() == sv) & mask).sum())

    # --- Aggregate ---
    # product -> category -> count
    agg = {}
    product_order = []
    category_order = {}  # product -> [categories in order]

    for _, row in map_df.iterrows():
        prod = str(row[prod_col]).strip()
        cat = str(row[cat_col]).strip()
        src_val = row[src_col]
        sheet = str(row[sheet_col]).strip()

        if pd.isna(src_val):
            continue
        cnt = get_sheet_counts(sheet, src_val, start_date, end_date)

        if prod not in agg:
            agg[prod] = {}
            product_order.append(prod)
            category_order[prod] = []
        if cat not in agg[prod]:
            agg[prod][cat] = 0
            category_order[prod].append(cat)
        agg[prod][cat] += cnt

    # --- Build chart data ---
    outer_labels = product_order
    outer_vals = [sum(agg[p].values()) for p in product_order]
    inner_labels_map = {}
    inner_vals_map = {}
    for p in product_order:
        inner_labels_map[p] = list(agg[p].keys())
        inner_vals_map[p] = list(agg[p].values())

    # Show aggregated table
    st.write("**Aggregated counts:**")
    rows = []
    for p in product_order:
        for c in category_order[p]:
            rows.append({"Product": p, "Category": c, "Count": agg[p][c]})
    rows.append({"Product": "TOTAL", "Category": "", "Count": sum(outer_vals)})
    st.dataframe(pd.DataFrame(rows))

    # --- Generate chart ---
    title = f"Post-Marketing ICSR ({start_date.strftime('%Y.%m.%d')}–{end_date.strftime('%Y.%m.%d')})"
    fig = build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title,
                      inside_thresh=label_threshold)

    st.pyplot(fig)

    # Download PNG + SVG (SVG is editable in Illustrator/Inkscape)
    buf_png = io.BytesIO()
    fig.savefig(buf_png, format='png', dpi=200, bbox_inches='tight', facecolor='white')
    buf_png.seek(0)

    buf_svg = io.BytesIO()
    fig.savefig(buf_svg, format='svg', bbox_inches='tight', facecolor='white')
    buf_svg.seek(0)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download PNG", buf_png, file_name="ICSR_donut.png", mime="image/png")
    with c2:
        st.download_button("Download SVG (editable)", buf_svg, file_name="ICSR_donut.svg", mime="image/svg+xml")
#（注：内容由AI生成）
