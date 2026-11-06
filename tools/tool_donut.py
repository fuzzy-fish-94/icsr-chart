"""
工具①：双层环形图 Donut
========================
上传 AE 追踪表（主表 + 可选 128SADR 独立表）+ 映射表(map.xlsx)，选日期范围，生成双层环形图。
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
    date_col, source_col, mah_col, case_col = None, None, None, None
    for idx, val in enumerate(header_row):
        s = str(val).lower()
        if source_col is None and "来源" in str(val):
            source_col = idx
        if date_col is None and ("获知日期" in str(val) or "received date" in s):
            date_col = idx
        if mah_col is None and ("mah" in s or "递交编码" in str(val) or "递交编号" in str(val)):
            mah_col = idx
        if case_col is None and "case" in s:
            case_col = idx
    return date_col, source_col, mah_col, case_col


PALETTES = {
    "经典": ["#E8792B", "#4A86C7", "#7FB069", "#9B7CC4", "#D46A6A", "#5FA8A0"],
    "马卡龙": ["#F5A8A8", "#A8D5BA", "#B8A9D9", "#F2D388", "#8FB8D9", "#E8A87C"],
    "莫兰迪": ["#C9A9A6", "#A8B5A0", "#A6A9B8", "#D4C5A9", "#9FB6C2", "#C2A88F"],
    "清新果色": ["#F4A261", "#E9C46A", "#8AB17D", "#577590", "#B5838D", "#6D6875"],
    "北欧灰粉": ["#E8B4B8", "#BFD3C1", "#C8B8DB", "#F0E2B6", "#A8C6D9", "#D9B38C"],
    "高饱和": ["#E63946", "#2A9D8F", "#E9C46A", "#457B9D", "#9B5DE5", "#F4A261"],
}

def build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title_text, inside_thresh=8, palette=None):
    if palette is None:
        palette = PALETTES["马卡龙"]
    flat_labels, flat_vals, flat_colors = [], [], []
    base_colors = palette

    def lighten(hexcolor, t):
        h = hexcolor.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = int(r + (255 - r) * t); g = int(g + (255 - g) * t); b = int(b + (255 - b) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    UNMATCHED = "未映射"
    for pi, prod in enumerate(outer_labels):
        if prod == UNMATCHED:
            base = "#b9b9b9"
        else:
            base = base_colors[pi % len(base_colors)]
        cats = inner_labels_map[prod]; vals = inner_vals_map[prod]; n = len(cats)
        for ci, (cc, v) in enumerate(zip(cats, vals)):
            flat_labels.append(f"{cc}\n{v}"); flat_vals.append(v)
            if prod == UNMATCHED:
                flat_colors.append("#cfcfcf")
            else:
                t = 0.0 if n == 1 else 0.75 * ci / (n - 1)
                flat_colors.append(lighten(base, t))

    outer_colors = [
        ("#b9b9b9" if outer_labels[i] == UNMATCHED else base_colors[i % len(base_colors)])
        for i in range(len(outer_vals))
    ]
    total = sum(outer_vals)
    fig, ax = plt.subplots(figsize=(9, 7.5), dpi=200); ax.set_aspect("equal")
    # 环层：外圈=分类，中圈=产品，中心=Total（已按需求调换：产品在中间，分类在最外）
    res_outer = ax.pie(flat_vals, radius=1.0, colors=flat_colors,
                       wedgeprops=dict(width=0.30, edgecolor="white", linewidth=2), startangle=90, counterclock=False)
    res_mid = ax.pie(outer_vals, radius=0.70, colors=outer_colors,
                     wedgeprops=dict(width=0.30, edgecolor="white", linewidth=1.5), startangle=90, counterclock=False)
    ax.text(0, 0, f"Total {total}", ha="center", va="center", fontsize=18, fontweight="bold", color="#222")

    # 外圈：分类名 + 例数；大块文字在扇区内部，小块被引线引出时文字水平摆平（贴着自己色块）
    for i, w in enumerate(res_outer[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        size = (w.theta2 - w.theta1)
        lbl = flat_labels[i]                      # 形如 "分类名\n数字"
        name, num = lbl.rsplit("\n", 1)           # 分类名过长时只在名字内折行，数字保持单独一行
        if len(name) > 14:
            words = name.split(); mid = len(words) // 2
            name = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
            lbl = name + "\n" + num
        if size >= inside_thresh:
            # 大块：文字画在扇区内部（径向，左半边翻转180°保证正读）
            x, y = 0.85 * np.cos(np.deg2rad(ang)), 0.85 * np.sin(np.deg2rad(ang))
            rot = ang
            if ang > 90:
                rot -= 180
            elif ang < -90:
                rot += 180
            ax.text(x, y, lbl, ha="center", va="center", fontsize=7.0,
                    rotation=rot, rotation_mode="anchor")
        else:
            # 小块：文字水平摆平；肘形引线 = 色块边缘 → 径向短段 → 水平段 → 文字（文字在水平末端，不穿字）
            cos_a = np.cos(np.deg2rad(ang)); sin_a = np.sin(np.deg2rad(ang))
            sign = 1 if cos_a >= 0 else -1
            ha = "left" if sign > 0 else "right"
            bx, by = 1.0 * cos_a, 1.0 * sin_a      # 色块外边缘
            mx, my = 1.05 * cos_a, 1.05 * sin_a    # 折弯点（径向外移一小段）
            tx = mx + sign * 0.12                  # 文字紧贴折弯点外侧一小段，引线短
            ty = my                                # 与折弯点同一水平线
            ax.plot([bx, mx], [by, my], color="#999", lw=0.6)   # 径向短段
            ax.plot([mx, tx], [my, ty], color="#999", lw=0.6)   # 水平段（不穿字）
            ax.text(tx, ty, lbl, ha=ha, va="center", fontsize=6.5,
                    rotation=0, multialignment="center")

    # 中圈：产品名 + 例数
    for i, w in enumerate(res_mid[0]):
        ang = (w.theta2 + w.theta1) / 2.0
        x = 0.55 * np.cos(np.deg2rad(ang)); y = 0.55 * np.sin(np.deg2rad(ang))
        ax.text(x, y, f"{outer_labels[i]}\n{outer_vals[i]}",
                ha="center", va="center", fontsize=10, color="black")

    ax.set_title(title_text, fontsize=13, color="#333", pad=18)
    fig.text(0.92, 0.04, "*IIT=Investigator Initiated Trial, PMK=Post-MarKeting, HA=Health Authority", ha="right", fontsize=7, color="#555", style="italic")
    plt.tight_layout()
    return fig


# ---------------- UI ----------------
st.title("🍩 Post-Marketing ICSR Donut Chart")
st.write("上传 AE 追踪表 + 映射表，选日期范围，生成双层环形图。")

DEFAULT_MAP_PATH = "map.xlsx"
f_tracking = st.file_uploader("① 主 AE Tracking Table (.xlsx)", type=["xlsx"])
f_split = st.file_uploader("② 128SADR 独立追踪表 (.xlsx) —— 已从主表拆出就上传；没有可留空", type=["xlsx"])
f_mapping = st.file_uploader("上传 Mapping Table (.xlsx) —— 留空则用默认 map.xlsx", type=["xlsx"])

c1, c2, c3 = st.columns(3)
with c1:
    start_date = st.date_input("开始日期", value=pd.Timestamp("2026-04-01"))
with c2:
    end_date = st.date_input("结束日期", value=pd.Timestamp("2026-08-31"))
with c3:
    label_threshold = st.slider("引线阈值(角度)", 0, 20, 8)
palette_name = st.selectbox("配色", list(PALETTES.keys()), index=0)

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

    # 每个 sheet 里"被规则接住"的来源集合（用于识别未映射来源）
    sheet_source_map = {}
    for _, row in map_df.iterrows():
        sv = row[src_col]; sh = str(row[sheet_col]).strip()
        if pd.isna(sv):
            continue
        sheet_source_map.setdefault(normalize_name(sh), set()).add(str(sv).strip())

    # 全表所有 map 来源（独立表不隶属单一 sheet，未映射判定用并集）
    all_map_sources = set()
    for _, row in map_df.iterrows():
        sv = row[src_col]
        if not pd.isna(sv):
            all_map_sources.add(str(sv).strip())

    # 数据源：主表（必填）+ 128SADR 独立表（可选）。同一套 map 规则对两个文件分别统计后相加，
    # 不做跨文件去重；主表里仍然残留的"已拆出来源"会自动剔除，避免两边各算一次。
    SOURCES = [("主表", f_tracking)]
    if f_split is not None:
        SOURCES.append(("128SADR", f_split))
    xls = {name: pd.ExcelFile(f) for name, f in SOURCES}

    cache = {}
    sheet_stats = {}
    sheet_details = {}   # 调试：每个 文件·sheet 最终筛完去重后的明细行
    warn_msgs = []

    # 拆出文件里出现过的"来源"取值（归一化），用于把主表里的同一批记录剔掉
    split_sources = set()
    if f_split is not None:
        for sname in xls["128SADR"].sheet_names:
            probe = pd.read_excel(xls["128SADR"], sheet_name=sname, header=None, nrows=2)
            if len(probe) < 2:
                continue
            _, pscol, _, _ = detect_columns(probe.iloc[1])
            if pscol is None:
                continue
            body = pd.read_excel(xls["128SADR"], sheet_name=sname, header=None).iloc[2:]
            vals = body.iloc[:, pscol].apply(lambda v: "" if pd.isna(v) else normalize_name(v))
            split_sources |= {v for v in vals if v}

    def _find_sheet(xl, target):
        """先按 sheet 名匹配；被拆出来的单 sheet 文件（常叫 Sheet1）按表头特征兜底认领。"""
        try:
            return find_sheet_by_name(xl, target)
        except ValueError:
            if len(xl.sheet_names) == 1:
                only = xl.sheet_names[0]
                probe = pd.read_excel(xl, sheet_name=only, header=None, nrows=2)
                if len(probe) >= 2:
                    dcol, scol, _, _ = detect_columns(probe.iloc[1])
                    if dcol is not None and scol is not None:
                        return only
            raise

    # MAH 编码视为“无效”的取值（空、NA、占位符）
    BAD_MAH = {"", "nan", "na", "n/a", "none", "-", "--", "/", "null", "无", "/无/"}

    def _load_sheet(src_name, sheet_name):
        """读取一个 文件·sheet：日期筛选 → 主表剔除已拆出来源 → 删无MAH → 按MAH去重，
        并顺带统计该 sheet 未映射的来源。结果按 (文件, sheet) 缓存。"""
        xl = xls[src_name]
        actual = _find_sheet(xl, sheet_name)
        key = (src_name, actual)
        if key in cache:
            return cache[key]
        df = pd.read_excel(xl, sheet_name=actual, header=None)
        dcol, scol, mcol, casecol = detect_columns(df.iloc[1])
        if dcol is None or scol is None:
            st.error(f"sheet '{actual}' 里没识别到日期/来源列。表头：{list(df.iloc[1].dropna())}"); st.stop()
        data = df.iloc[2:].copy()
        # MAH 列统一转字符串、去首尾空格；无 MAH 列就当全空
        if mcol is None:
            mah_series = pd.Series([""] * len(data))
        else:
            mah_series = data.iloc[:, mcol].apply(
                lambda v: "" if pd.isna(v) else str(v).strip()
            )
        # 调试用：case NO. 按表头自动识别（不再写死第2列，避免把"报告获知日期"当 case NO.）
        if casecol is None:
            case_series = pd.Series([""] * len(data))
        else:
            case_series = data.iloc[:, casecol].apply(
                lambda v: "" if pd.isna(v) else str(v).strip()
            )
        dates_raw = pd.to_datetime(data.iloc[:, dcol], errors="coerce")
        sources_raw = data.iloc[:, scol].apply(lambda v: "" if pd.isna(v) else str(v).strip())

        # 1) 日期筛选（end 含当天 23:59:59）
        dmask = (dates_raw >= pd.Timestamp(start_date)) & \
                (dates_raw <= pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
        n_date = int(dmask.sum())
        d = dates_raw[dmask].reset_index(drop=True)
        s = sources_raw[dmask].reset_index(drop=True)
        m = mah_series[dmask].reset_index(drop=True)
        c = case_series[dmask].reset_index(drop=True)

        # 1.5) 主表里剔除已经拆到 128SADR 独立文件的来源（否则两个文件各算一次会虚高）
        n_excluded = 0
        if src_name == "主表" and split_sources:
            ex = s.str.lower().isin(split_sources)
            n_excluded = int(ex.sum())
            d = d[~ex].reset_index(drop=True)
            s = s[~ex].reset_index(drop=True)
            m = m[~ex].reset_index(drop=True)
            c = c[~ex].reset_index(drop=True)

        # 2) 删掉 MAH 为空 / NA / 占位符
        valid_mask = ~m.str.lower().isin(BAD_MAH)
        d = d[valid_mask].reset_index(drop=True)
        s = s[valid_mask].reset_index(drop=True)
        m = m[valid_mask].reset_index(drop=True)
        c = c[valid_mask].reset_index(drop=True)
        n_valid = len(s)

        # 3) 在该区间内按 MAH 编码去重
        keep_mask = ~m.duplicated(keep="first")
        d = d[keep_mask].reset_index(drop=True)
        s = s[keep_mask].reset_index(drop=True)
        m = m[keep_mask].reset_index(drop=True)
        c = c[keep_mask].reset_index(drop=True)
        n_final = len(s)

        label = f"{src_name}·{actual}"
        excl_note = f"，已剔除拆出记录 {n_excluded} 行" if n_excluded else ""
        sheet_stats[label] = f"日期内 {n_date} 行{excl_note} → 有MAH编码 {n_valid} 行 → 去重后 {n_final} 行"
        # 缓存明细，供下面调试面板展示
        sheet_details[label] = pd.DataFrame({
            "日期": d.dt.strftime("%Y-%m-%d"),
            "来源": s,
            "MAH递交编码": m,
            "case NO.": c,
        })

        # 4) 未映射：本 sheet 去重后、来源不在 map 规则集合里的行
        #    主表按 map 里该 sheet 的规则判定；独立表按全表 map 来源并集判定（它不隶属某个 sheet）
        if src_name == "主表":
            srcset = sheet_source_map.get(normalize_name(sheet_name), set())
        else:
            srcset = all_map_sources
        un = s[~s.isin(srcset)].value_counts().to_dict()

        cache[key] = {"actual": actual, "label": label, "sources": s,
                      "unmatched": un, "n_excluded": n_excluded}
        return cache[key]

    def get_counts(sheet_name, source_value, start=None, end=None):
        """按规则统计：该来源值在各文件对应 sheet 去重后出现的次数之和（不跨文件去重）。"""
        target = str(source_value).strip()
        total = 0
        for src_name, _f in SOURCES:
            try:
                rec = _load_sheet(src_name, sheet_name)
            except ValueError:
                if src_name == "主表":
                    st.error(f"map 里的使用sheet「{sheet_name}」在主表里没找到。主表 sheet：{xls['主表'].sheet_names}")
                    st.stop()
                msg = (f"map 里的使用sheet「{sheet_name}」在 {src_name} 表里没找到"
                       f"（该表 sheet：{xls[src_name].sheet_names}），这条规则不计该文件。")
                if msg not in warn_msgs:
                    warn_msgs.append(msg)
                continue
            total += int((rec["sources"] == target).sum())
        return total

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

    # 汇总未映射来源（跨所有被 mapping 引用的 sheet）
    unmatched_total = 0
    unmatched_rows = []
    for rec in cache.values():
        for src, cnt in rec["unmatched"].items():
            src = str(src).strip()
            if not src or src.lower() == "nan":
                continue
            unmatched_rows.append((rec["label"], src, int(cnt)))
            unmatched_total += int(cnt)
    unmatched_rows.sort(key=lambda t: t[2], reverse=True)

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

    with st.expander(f"数据源校验（本次读取 {len(SOURCES)} 个文件）"):
        st.write("**读取的文件：** " + "；".join(n for n, _ in SOURCES))
        if f_split is not None:
            st.write(f"**128SADR 表识别到的来源：** {sorted(split_sources) if split_sources else '无'}")
            ex_total = sum(r.get("n_excluded", 0) for r in cache.values())
            if ex_total:
                st.warning(f"主表里仍有 {ex_total} 条属于 128SADR 的记录，已自动剔除（否则会和独立表重复计数）。建议后续把主表这部分清理掉。")
            else:
                st.success("主表已无 128SADR 记录，两个文件数据无重叠。")
        else:
            st.info("未上传 128SADR 独立表，按单文件统计。")
        for m_ in warn_msgs:
            st.warning(m_)

    # 未映射来源：只在页面以列表展示，不画进图（图上 Total = 已映射数）
    rows = []
    for p in outer_labels:
        for c, v in zip(inner_labels_map[p], inner_vals_map[p]):
            rows.append({"Product": p, "Category": c, "Count": v})
    rows.append({"Product": "TOTAL", "Category": "", "Count": sum(outer_vals)})
    st.write("**汇总行数：**"); st.dataframe(pd.DataFrame(rows))
    with st.expander(f"未映射来源（未被任何规则归类 · 共 {unmatched_total} 条，仅列表展示）"):
        mapped = sum(outer_vals)
        st.write(f"去重后有效 **{mapped + unmatched_total}** ＝ 图上已映射 **{mapped}** ＋ 未映射 **{unmatched_total}**")
        if unmatched_rows:
            st.dataframe(pd.DataFrame(unmatched_rows, columns=["文件·Sheet", "来源", "数量"]),
                         use_container_width=True)
            st.info("这些来源没匹配到 mapping 里的任何规则，所以没被归到分类（图上灰色『未映射』块）。"
                    "在 map.xlsx 里补一行对应规则即可：产品、分类、来源关键词、使用sheet。")
        else:
            st.success("所有来源都已匹配到规则，无未映射。")
    with st.expander("数据清洗明细（MAH筛选+去重）"):
        for s, t in sheet_stats.items():
            st.write(f"- **{s}**：{t}")
        st.markdown("---")
        st.write("**每个 sheet 最终计入的明细行**（日期筛完 → 删无MAH → 去重后）：")
        for sheet_name, df_detail in sheet_details.items():
            st.write(f"📄 **{sheet_name}**（共 {len(df_detail)} 行）")
            st.dataframe(df_detail, use_container_width=True, height=200)

    title = f"Post-Marketing ICSR ({start_date.strftime('%Y.%m.%d')}–{end_date.strftime('%Y.%m.%d')})"
    fig = build_chart(outer_labels, outer_vals, inner_labels_map, inner_vals_map, title, label_threshold, palette=PALETTES[palette_name])
    st.pyplot(fig)

    b_png = io.BytesIO(); fig.savefig(b_png, format="png", dpi=200, bbox_inches="tight", facecolor="white"); b_png.seek(0)
    b_svg = io.BytesIO(); fig.savefig(b_svg, format="svg", bbox_inches="tight", facecolor="white"); b_svg.seek(0)
    x1, x2 = st.columns(2)
    x1.download_button("下载 PNG", b_png, file_name="ICSR_donut.png", mime="image/png")
    x2.download_button("下载 SVG(可编辑)", b_svg, file_name="ICSR_donut.svg", mime="image/svg+xml")
#（注：内容由AI生成）
