"""
工具②：个例小结（按报告来源分类）
==================================
口径全部来自 summary_map.xlsx（放本文件同目录）：
  Sheet1_图表口径  → 驱动 NSADR vs 其他 横条图
  Sheet2_文字口径  → 驱动文字小结的细拆
界面可上传 map 覆盖；不传就读同目录默认 summary_map.xlsx。
"""
import io
import re
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

DEFAULT_MAP = "summary_map.xlsx"


# ---------- 基础工具 ----------
def norm(s):
    return re.sub(r"\s+", "", str(s)).strip().lower()


def find_sheet(xl, target):
    nt = norm(target)
    for n in xl.sheet_names:
        if norm(n) == nt:
            return n
    for n in xl.sheet_names:
        if nt in norm(n):
            return n
    raise ValueError(f"sheet '{target}' 没找到。现有：{xl.sheet_names}")


def load_sheet(xl, sheet):
    """返回 (dates, sources)，自动识别日期列和来源列。"""
    actual = find_sheet(xl, sheet)
    df = pd.read_excel(xl, sheet_name=actual, header=None)
    dcol, scol = None, None
    for i, v in enumerate(df.iloc[1]):
        s = str(v)
        if scol is None and "来源" in s:
            scol = i
        if dcol is None and ("获知日期" in s or "received date" in s.lower()):
            dcol = i
    if dcol is None:
        raise ValueError(f"sheet '{actual}' 里没找到日期列。表头：{list(df.iloc[1].dropna())}")
    data = df.iloc[2:].copy()
    dates = pd.to_datetime(data.iloc[:, dcol], errors="coerce")
    sources = data.iloc[:, scol].astype(str).str.strip() if scol is not None else pd.Series([""] * len(data))
    return dates, sources


# ---------- 解析 map ----------
def parse_map(map_source):
    xl = pd.ExcelFile(map_source)

    # Sheet1：图表口径
    s1 = pd.read_excel(map_source, sheet_name=0, header=0)
    s1.columns = [str(c).strip() for c in s1.columns]
    s1.iloc[:, 0] = s1.iloc[:, 0].ffill()
    chart_cfg = {}
    for _, row in s1.iterrows():
        prod = str(row.iloc[0]).strip()
        if not prod or prod == "nan":
            continue
        chart_cfg.setdefault(prod, {"nsadr": ([], None), "other": []})
        ns_v, ns_sheet = row.iloc[1], row.iloc[2]
        ot_v, ot_sheet = row.iloc[3], row.iloc[4]
        if pd.notna(ns_v) and str(ns_v).strip():
            vals = [x.strip() for x in re.split(r"[；;]", str(ns_v)) if x.strip()]
            chart_cfg[prod]["nsadr"] = (vals, str(ns_sheet).strip())
        if pd.notna(ot_v) and str(ot_v).strip():
            v = str(ot_v).strip()
            sheet = str(ot_sheet).strip()
            if v == "所有":
                chart_cfg[prod]["other"].append(("所有", sheet))
            else:
                vals = [x.strip() for x in re.split(r"[；;]", v) if x.strip()]
                chart_cfg[prod]["other"].append((vals, sheet))

    # Sheet2：文字口径
    s2 = pd.read_excel(map_source, sheet_name=1, header=0)
    s2.columns = [str(c).strip() for c in s2.columns]
    text_cfg = {}
    for _, row in s2.iterrows():
        prod = str(row.iloc[0]).strip()
        if not prod or prod == "nan" or prod.startswith(("说明", "①", "②", "③")):
            continue
        sheet = str(row.iloc[1]).strip()
        src = str(row.iloc[2]).strip()
        big = str(row.iloc[3]).strip()
        sub = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ""
        text_cfg.setdefault(prod, []).append((sheet, src, big, sub))
    return chart_cfg, text_cfg


# ---------- 聚合 ----------
def agg_chart(chart_cfg, xl, start, end):
    cache = {}

    def counts(sheet, values):
        if sheet not in cache:
            cache[sheet] = load_sheet(xl, sheet)
        dates, sources = cache[sheet]
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
        if values == "所有":
            return int(mask.sum())
        return int((sources.isin(values) & mask).sum())

    out = {}
    for prod, cfg in chart_cfg.items():
        ns_vals, ns_sheet = cfg["nsadr"]
        ns = counts(ns_sheet, ns_vals) if ns_sheet else 0
        ot = sum(counts(sheet, vals) for vals, sheet in cfg["other"])
        out[prod] = (ns, ot)
    return out


def agg_text(text_cfg, xl, start, end):
    cache = {}
    out = {}
    for prod, rules in text_cfg.items():
        buckets = {}
        for sheet, src, big, sub in rules:
            if sheet not in cache:
                cache[sheet] = load_sheet(xl, sheet)
            dates, sources = cache[sheet]
            mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            c = int(((sources == src) & mask).sum())
            if c:
                buckets[(big, sub)] = buckets.get((big, sub), 0) + c
        out[prod] = buckets
    return out


# ---------- 文字 ----------
def build_text(text_cfg, agg, start, end):
    total = sum(sum(b.values()) for b in agg.values())
    lines = [
        f"截至{start.strftime('%Y年%m月%d日')}至{end.strftime('%Y年%m月%d日')}，共收到个例安全性报告{total}例。",
        "",
        "按报告来源分类:",
    ]
    for i, prod in enumerate(agg.keys(), 1):
        buckets = agg[prod]
        lines.append(f"{i}. {prod}")
        nsadr = {(sub): c for (big, sub), c in buckets.items() if big == "NSADR研究"}
        if nsadr:
            parts = [f"{c}例来自{sub}" for sub, c in nsadr.items()]
            lines.append(f"•NSADR LL     {sum(nsadr.values())}例：（{'；'.join(parts)}），")
        rest = {k: v for k, v in buckets.items() if k[0] != "NSADR研究"}
        segs = []
        for big_name in ["研究", "自发"]:
            sub_map = {sub: c for (big, sub), c in rest.items() if big == big_name}
            if sub_map:
                inner = [f"{c}例来自{sub}" for sub, c in sub_map.items()]
                segs.append(f"{big_name}{sum(sub_map.values())}例（{'；'.join(inner)}）")
        for big_name in ["反馈", "患者支持项目", "文献报道"]:
            for (big, sub), c in rest.items():
                if big == big_name:
                    segs.append(f"{big_name}{c}例")
        lines.append(f"•非NSADR LL  {sum(rest.values())}例：{'，'.join(segs)}.")
        lines.append("")
    return "\n".join(lines), total


# ---------- 图 ----------
def build_figure(chart_result, text_product_names, start, end):
    short_names = list(chart_result.keys())
    names = text_product_names[: len(short_names)]
    ns_vals = [chart_result[p][0] for p in short_names]
    ot_vals = [chart_result[p][1] for p in short_names]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(10, 2.0 * len(names)), dpi=200)
    c_ns, c_ot = "#7FB069", "#E8792B"
    ax.barh(y, ns_vals, color=c_ns, edgecolor="white", height=0.55, label="NSADR（上市后研究）")
    ax.barh(y, ot_vals, left=ns_vals, color=c_ot, edgecolor="white", height=0.55, label="其他（自发/反馈/SADR研究等）")
    xmax = max(ns_vals[i] + ot_vals[i] for i in range(len(names))) or 1
    # 自适应阈值：色块占比 >= 这个比例才把字放里面，否则甩到外面
    IN = 0.13
    pad = xmax * 0.012

    for yi, (n, o) in enumerate(zip(ns_vals, ot_vals)):
        total = n + o
        # NSADR 段
        if n > 0:
            t = f"NSADR {n} ({n/total*100:.0f}%)" if total else f"NSADR {n}"
            if n >= xmax * IN:
                ax.text(n/2, yi, t, ha="center", va="center", fontsize=9, color="white", fontweight="bold")
            else:
                # 甩到色块右上方（y 上抬 0.2），避免和"其他"外标叠
                ax.text(n + pad, yi + 0.2, t, ha="left", va="bottom", fontsize=8.5, color=c_ns, fontweight="bold")
        # 其他 段
        if o > 0:
            t = f"其他 {o} ({o/total*100:.0f}%)" if total else f"其他 {o}"
            if o >= xmax * IN:
                ax.text(n + o/2, yi, t, ha="center", va="center", fontsize=9, color="white", fontweight="bold")
            else:
                # 甩到色块右下方（y 下压 0.2），和 NSADR 外标错开
                ax.text(n + o + pad, yi - 0.2, t, ha="left", va="top", fontsize=8.5, color=c_ot, fontweight="bold")

    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, xmax * 1.25)
    ax.set_xlabel("例数")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    ax.grid(axis="x", alpha=0.25)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.set_title(f"三产品 NSADR vs 其他（{start.strftime('%Y.%m.%d')}–{end.strftime('%Y.%m.%d')}）", fontsize=12, loc="left", color="#333")
    plt.tight_layout()
    return fig


# ---------------- UI ----------------
st.title("📝 个例小结（按报告来源分类）")
st.write("上传 AE 追踪表 → 选日期范围 → 自动出文字小结 + 三产品 NSADR/其他对比图。")

f = st.file_uploader("上传 AE 追踪表 (.xlsx)", type=["xlsx"], key="s_file")
f_map = st.file_uploader("上传口径 map (.xlsx) —— 留空则用同目录 summary_map.xlsx", type=["xlsx"], key="s_map")
c1, c2 = st.columns(2)
with c1:
    start = st.date_input("开始日期", value=pd.Timestamp("2025-11-26"))
with c2:
    end = st.date_input("结束日期", value=pd.Timestamp("2026-01-30"))

if st.button("生成小结", type="primary"):
    if not f:
        st.error("请先上传追踪表。"); st.stop()
    if f_map is not None:
        map_source = f_map
        st.write("**使用上传的 map。**")
    elif os.path.exists(DEFAULT_MAP):
        map_source = DEFAULT_MAP
        st.write(f"**使用默认 map：** `{DEFAULT_MAP}`")
    else:
        st.error(f"未上传 map，且同目录找不到 {DEFAULT_MAP}"); st.stop()

    chart_cfg, text_cfg = parse_map(map_source)
    xl = pd.ExcelFile(f)
    chart_result = agg_chart(chart_cfg, xl, start, end)
    text_agg = agg_text(text_cfg, xl, start, end)
    text, total = build_text(text_cfg, text_agg, start, end)

    st.subheader("① 文字小结")
    st.code(text, language=None)
    st.download_button("下载小结 .txt", text, file_name="ICSR_summary.txt", mime="text/plain")

    st.subheader("② NSADR vs 其他 对比图")
    fig = build_figure(chart_result, list(text_agg.keys()), start, end)
    st.pyplot(fig)
    bp = io.BytesIO(); fig.savefig(bp, format="png", dpi=200, bbox_inches="tight", facecolor="white"); bp.seek(0)
    bs = io.BytesIO(); fig.savefig(bs, format="svg", bbox_inches="tight", facecolor="white"); bs.seek(0)
    d1, d2 = st.columns(2)
    d1.download_button("下载 PNG", bp, file_name="ICSR_nsadr_vs_other.png", mime="image/png")
    d2.download_button("下载 SVG(可编辑)", bs, file_name="ICSR_nsadr_vs_other.svg", mime="image/svg+xml")
#（注：内容由AI生成）
