"""
入口：ICSR 面板
================
只负责"挂哪些工具"。加新工具时：
  1. 在 tools/ 文件夹里新建一个 xxx.py（照抄现有两个工具的写法）
  2. 在下面 PAGES 列表里加一行
别的工具一行都不用动。

运行：  streamlit run app.py
"""
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 中文字体（全局生效，两个工具都用）
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS",
    "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="ICSR 面板", layout="wide", page_icon="📊")

# 在这里登记工具：(文件路径, 侧边栏名字, 图标)
PAGES = [
    ("tools/tool_donut.py",   "环形图工具", "🍩"),
    ("tools/tool_summary.py", "个例小结",   "📝"),
]

pg = st.navigation([
    st.Page(path, title=title, icon=icon) for path, title, icon in PAGES
])
pg.run()
#（注：内容由AI生成）
