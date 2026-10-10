"""
入口：ICSR 面板
================
只负责"挂哪些工具"。加新工具时：
  1. 在 tools/ 文件夹里新建一个 xxx.py（照抄现有两个工具的写法）
  2. 在下面 PAGES 列表里加一行
别的工具一行都不用动。

运行：  streamlit run app.py
"""
import os
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 中文字体（全局生效，两个工具都用）
# 云端 Linux 有 Noto/WenQuanYi，本地 Windows 有雅黑/黑体；按机器自动挑第一个能用的
plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
    "Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="ICSR 面板", layout="wide", page_icon="📊")

# 以本文件所在目录为基准定位 tools/，换启动目录也不会找不到
BASE = os.path.dirname(os.path.abspath(__file__))

# 在这里登记工具：(tools下的文件名, 侧边栏名字, 图标)
PAGES = [
    ("tool_donut.py",   "环形图工具", "🍩"),
    ("tool_summary.py", "个例小结",   "📝"),
]

# 先检查文件在不在，不在就给中文提示，而不是抛英文栈
missing = [f for f, _, _ in PAGES if not os.path.exists(os.path.join(BASE, "tools", f))]
if missing:
    st.error(
        "找不到工具文件。请确认在 app.py 同目录下有一个名叫 **tools** 的文件夹，"
        "里面放着这两个文件：\n\n"
        + "\n".join(f"- tools/{f}" for f in missing)
        + f"\n\n当前 app.py 位置：`{BASE}`"
    )
    st.stop()

pg = st.navigation([
    st.Page(os.path.join(BASE, "tools", f), title=title, icon=icon)
    for f, title, icon in PAGES
])
pg.run()
#（注：内容由AI生成）
