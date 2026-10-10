"""
工具①：双层环形图 Donut
========================
上传 AE 追踪表 + 映射表(map.xlsx)，选日期范围，生成双层环形图。
这个文件完全独立，改它不影响别的工具。
"""
import io
import re
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# SVG 导出时保留文字为可编辑文本（不要转成轮廓路径）
plt.rcParams["svg.fonttype"] = "none"


def normalize_name(s):
    return re.sub(r"\s+", "", str(s)).strip().lower()


def find_sheet_by_name(xl, target):
    nt = normalize_name(target)
    for name in xl.sheet_names:
        if normalize_name(name) == nt:
            return name
    for name in xl.sheet_names:
        if nt in normalize_name(name):
            return name
    raise ValueError(f"Sheet '{target}' 没找到。现有 sheet：{xl.sheet_names}")


def detect_columns(header_row):
    date_col, source_col, mah_col = None, None, None
    for idx, val in enumerate(header_row):
        s = str(val).lower()
        if source_col is None and "来源" in str(val):
            source_col = idx
        if date_col is None and ("获知日期" in str(val) or "received date" in s):
            date_col = idx
        if mah_col is None and ("mah" in s or "递交编码" in str(val) or "递交编号" in str(val)):
            mah_col = idx
    return date_col, source_col, mah_col


def build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title_text, inside_thresh=8):
    flat_labels, flat_vals, flat_colors = [], [], []
    base_colors = ["#E8792B", "#4A86C7", "#7FB069", "#9B7CC4", "#D46A6A", "#5FA8A0"]

    def lighten(hexcolor, t):
        h = hexcolor.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = int(r + (255 - r) * t); g = int(g + (255 - g) * t); b = int(b + (255 - b) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    for pi, prod in enumerate(outer_labels):
        base = base_colors[pi % len(base_colors)]
        cats = inner_labels_map[prod]; vals = inner_vals_map[prod]; n = len(cats)
        for ci, (cc, v) in enumerate(zip(cats, vals)):
            flat_labels.append(f"{cc} {v}"); flat_vals.append(v)
            t = 0.0 if n == 1 else 0.75 * ci / (n - 1)
            flat_colors.append(lighten(base, t))

    outer_colors = [base_colors[i % len(base_colors)] for i in range(len(outer_vals))]
    total = sum(outer_vals)
    fig, ax = plt.subplots(figsize=(9, 7.5), dpi=200); ax.set_aspect("equal")
    res_outer = ax.pie(outer_vals, radius=1.0, colors=outer_colors,
                       wedgeprops=dict(width=0.30, edgecolor="white", linewidth=2), startangle=90, counterclock=False)
    res_inner = ax.pie(flat_vals, radius=0.70, colors=flat_colors,
                       wedgeprops=dict(width=0.30, edgecolor="white", linewidth=1.5), startangle=90, counterclock=False)
    ax.text(0, 0, f"Total {total}", ha="center", va="center", fontsize=18, fontweight="bold", color="#222")

    # 外圈：产品名 + 例数
    for i, w in enumerate(res_outer[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        x = 0.85 * np.cos(np.deg2rad(ang)); y = 0.85 * np.sin(np.deg2rad(ang))
        ax.text(x, y, f"{outer_labels[i]}\n{outer_vals[i]}",
                ha="center", va="center", fontsize=10, color="black")

    outside_items = []
    for i, w in enumerate(res_inner[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        size = (w.theta2 - w.theta1)
        if size >= inside_thresh:
            x, y = 0.55 * np.cos(np.deg2rad(ang)), 0.55 * np.sin(np.deg2rad(ang))
            lbl = flat_labels[i]
            if len(lbl) > 14:
                words = lbl.split(); mid = len(words) // 2
                lbl = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
            # 内圈文字沿半径方向（径向），左半边翻转180°保证正读
            rot = ang
            if ang > 90:
                rot -= 180
            elif ang < -90:
                rot += 180
            ax.text(x, y, lbl, ha="center", va="center", fontsize=7.5,
                    rotation=rot, rotation_mode="anchor")
        else:
            outside_items.append((ang, flat_labels[i]))

    if outside_items:
        right = [(a, l) for a, l in outside_items if np.cos(np.deg2rad(a)) > 0]
        left = [(a, l) for a, l in outside_items if np.cos(np.deg2rad(a)) <= 0]
        for group, side in [(right, "right"), (left, "left")]:
            if not group:
                continue
            group.sort(key=lambda t: np.sin(np.deg2rad(t[0])))
            n = len(group)
            ys = np.linspace(-0.5, 0.5, n) if n > 1 else [np.sin(np.deg2rad(group[0][0]))]
            xt = 1.12 if side == "right" else -1.12
            ha = "left" if side == "right" else "right"
            for (ang, label), yt in zip(group, ys):
                ax.annotate(label, xy=(0.70 * np.cos(np.deg2rad(ang)), 0.70 * np.sin(np.deg2rad(ang))),
                            xytext=(xt, yt), fontsize=7, color="black",
                            arrowprops=dict(arrowstyle="-", color="#999", lw=0.6), ha=ha, va="center")

    ax.set_title(title_text, fontsize=13, color="#333", pad=18)
    fig.text(0.92, 0.04, "*NSADR = non-serious ADR; SADR = serious", ha="right", fontsize=7, color="#555", style="italic")
    plt.tight_layout()
    return fig


# ---------------- UI ----------------
st.title("🍩 Post-Marketing ICSR Donut Chart")
st.write("上传 AE 追踪表 + 映射表，选日期范围，生成双层环形图。")

DEFAULT_MAP_PATH = "map.xlsx"
f_tracking = st.file_uploader("上传 AE Tracking Table (.xlsx)", type=["xlsx"])
f_mapping = st.file_uploader("上传 Mapping Table (.xlsx) —— 留空则用默认 map.xlsx", type=["xlsx"])

c1, c2, c3 = st.columns(3)
with c1:
    start_date = st.date_input("开始日期", value=pd.Timestamp("2026-04-01"))
with c2:
    end_date = st.date_input("结束日期", value=pd.Timestamp("2026-08-31"))
with c3:
    label_threshold = st.slider("引线阈值(角度)", 0, 20, 8)

if st.button("生成环形图", type="primary"):
    if not f_tracking:
        st.error("请先上传追踪表。"); st.stop()
    if f_mapping is not None:
        map_source = f_mapping; st.write("**使用上传的映射表。**")
    else:
        if os.path.exists(DEFAULT_MAP_PATH):
            map_source = DEFAULT_MAP_PATH; st.write(f"**使用默认映射：** `{DEFAULT_MAP_PATH}`")
        else:
            st.error(f"未上传映射表，且找不到默认文件 {DEFAULT_MAP_PATH}"); st.stop()

    map_df = pd.read_excel(map_source, header=0)
    map_df.columns = [str(c).strip() for c in map_df.columns]
    st.write("**映射表预览：**"); st.dataframe(map_df)
    prod_col, cat_col, src_col, sheet_col = map_df.columns[0], map_df.columns[1], map_df.columns[2], map_df.columns[3]
    map_df[prod_col] = map_df[prod_col].ffill(); map_df[cat_col] = map_df[cat_col].ffill()

    xl = pd.ExcelFile(f_tracking)
    cache = {}
    sheet_stats = {}

    def get_counts(sheet_name, source_value, start, end):
        if sheet_name not in cache:
            actual = find_sheet_by_name(xl, sheet_name)
            df = pd.read_excel(xl, sheet_name=actual, header=None)
            dcol, scol, mcol = detect_columns(df.iloc[1])
            if dcol is None or scol is None:
                st.error(f"sheet '{actual}' 里没识别到日期/来源列。表头：{list(df.iloc[1].dropna())}"); st.stop()
            data = df.iloc[2:].copy()
            mah = data.iloc[:, mcol].astype(str).str.strip() if mcol is not None else pd.Series([""] * len(data))
            cache[sheet_name] = (
                actual,
                pd.to_datetime(data.iloc[:, dcol], errors="coerce"),
                data.iloc[:, scol].astype(str).str.strip(),
                mah,
            )
        actual, dates_raw, sources_raw, mah_raw = cache[sheet_name]
        # 1) 先按日期筛
        dmask = (dates_raw >= pd.Timestamp(start)) & (dates_raw <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
        n_date = int(dmask.sum())
        s = sources_raw[dmask].reset_index(drop=True)
        m = mah_raw[dmask].reset_index(drop=True)
        # 2) 再筛掉没有 MAH 编码的
        bad = {"", "nan", "na", "n/a", "none", "-", "/"}
        valid = ~m.str.lower().isin(bad)
        s = s[valid]; m = m[valid]
        n_valid = len(s)
        # 3) 在这段时间内按 MAH 编码去重（同编码多次出现只算第一条）
        s = s[~m.duplicated(keep="first")]
        n_final = len(s)
        sheet_stats[actual] = f"日期内 {n_date} 行 → 有MAH编码 {n_valid} 行 → 去重后 {n_final} 行"
        return int((s == str(source_value).strip()).sum())

    agg, product_order, category_order = {}, [], {}
    for _, row in map_df.iterrows():
        prod = str(row[prod_col]).strip(); cat = str(row[cat_col]).strip()
        src_val = row[src_col]; sheet = str(row[sheet_col]).strip()
        if pd.isna(src_val):
            continue
        cnt = get_counts(sheet, src_val, start_date, end_date)
        agg.setdefault(prod, {})
        if prod not in product_order:
            product_order.append(prod); category_order[prod] = []
        if cat not in agg[prod]:
            agg[prod][cat] = 0; category_order[prod].append(cat)
        agg[prod][cat] += cnt

    outer_labels = []
    outer_vals = []
    inner_labels_map = {}
    inner_vals_map = {}
    for p in product_order:
        # 丢掉 0 的分类
        cats = [(c, v) for c, v in agg[p].items() if v > 0]
        if not cats:
            continue  # 这个产品在本周期 0 例，不画
        cats.sort(key=lambda t: list(agg[p].keys()).index(t[0]))
        inner_labels_map[p] = [c for c, _ in cats]
        inner_vals_map[p] = [v for _, v in cats]
        outer_labels.append(p)
        outer_vals.append(sum(v for _, v in cats))

    rows = []
    for p in outer_labels:
        for c, v in zip(inner_labels_map[p], inner_vals_map[p]):
            rows.append({"Product": p, "Category": c, "Count": v})
    rows.append({"Product": "TOTAL", "Category": "", "Count": sum(outer_vals)})
    st.write("**汇总行数：**"); st.dataframe(pd.DataFrame(rows))
    with st.expander("数据清洗明细（MAH筛选+去重）"):
        for s, t in sheet_stats.items():
            st.write(f"- **{s}**：{t}")

    title = f"Post-Marketing ICSR ({start_date.strftime('%Y.%m.%d')}–{end_date.strftime('%Y.%m.%d')})"
    fig = build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title, label_threshold)
    st.pyplot(fig)

    b_png = io.BytesIO(); fig.savefig(b_png, format="png", dpi=200, bbox_inches="tight", facecolor="white"); b_png.seek(0)
    b_svg = io.BytesIO(); fig.savefig(b_svg, format="svg", bbox_inches="tight", facecolor="white"); b_svg.seek(0)
    x1, x2 = st.columns(2)
    x1.download_button("下载 PNG", b_png, file_name="ICSR_donut.png", mime="image/png")
    x2.download_button("下载 SVG(可编辑)", b_svg, file_name="ICSR_donut.svg", mime="image/svg+xml")
#（注：内容由AI生成）
