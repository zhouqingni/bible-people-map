"""算出每个人在图上的位置，把网页要用的数据打包成 网页/数据.js。

布局：
  · 横向是时间：12 个时期每个一样宽；时期内部按年代先后排（一半按真实年代、一半按先后名次，避免挤在一起）。
  · 纵向像星图：有关系的人互相吸引，靠得太近的互相推开，所以会聚成一团团（大卫一家、十二使徒……）。
  · 耶稣家谱固定在正中间一条横线上：亚伯拉罕到大卫两支共用；大卫之后马太一支在上、路加一支在下，到约瑟会合。

需要先运行：01～04
输出：网页/数据.js（网页用 <script> 直接读取，双击打开就能用，不需要联网）

运行：python3 -I 脚本/05_网页数据.py
"""
import csv
import glob
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "数据")
WEB = os.path.join(ROOT, "网页")
USFM = os.path.join(ROOT, "数据源", "和合本", "usfm")
TITLES = os.path.join(ROOT, "脚本", "对照表", "事件标题.tsv")

BAND = 700             # 每个时期的宽度
STRETCH = 2.6          # 纵向拉开的倍数（让星图在屏幕上不至于压成一条线）
TYPES = ["主线", "亲属", "社会", "事件", "同节"]
PULL = {"亲属": 1.0, "社会": 0.8, "事件": 0.5, "同节": 0.12}
random.seed(42)


def load_bible():
    """和合本：经文代号 → 纯文字；书卷代号 → 中文书名"""
    text, books = {}, {}
    for path in sorted(glob.glob(os.path.join(USFM, "*.usfm"))):
        raw = open(path, encoding="utf-8").read()
        m = re.search(r"\\id (\w+)", raw)
        h = re.search(r"\\h (\S+)", raw)
        if not m:
            continue
        b = m.group(1)
        books[b] = h.group(1) if h else b
        for cm in re.finditer(r"\\c (\d+)\s(.*?)(?=\\c \d+\s|\Z)", raw, re.S):
            for vm in re.finditer(r"\\v (\d+)(?:-\d+)? (.*?)(?=\\v \d+|\Z)", cm.group(2), re.S):
                s = re.sub(r"\\f .*?\\f\*", "", vm.group(2), flags=re.S)
                s = re.sub(r"\\x .*?\\x\*", "", s, flags=re.S)
                s = re.sub(r"\\\+?\w+\*?", "", s)
                text[f"{b} {cm.group(1)}:{vm.group(1)}"] = re.sub(r"\s+", "", s)
    return text, books


def main():
    graph = json.load(open(os.path.join(OUT, "图数据.json"), encoding="utf-8"))
    bible, books = load_bible()
    zh2code = {v: k for k, v in books.items()}
    titles = {}
    for row in csv.DictReader(open(TITLES, encoding="utf-8"), delimiter="\t"):
        titles[row["英文标题"]] = row["中文标题"]

    def to_code(ref):
        """统一成 'GEN 1:1' 形式"""
        if not ref:
            return None
        b, cv = ref.split(" ", 1)
        return ref if b in books else (f"{zh2code[b]} {cv}" if b in zh2code else None)

    def show(ref):
        b, cv = ref.split(" ", 1)
        return f"{books.get(b, b)} {cv}"

    periods = graph["时期"]
    pidx = {p["名"]: i for i, p in enumerate(periods)}
    nodes = graph["点"]
    idx = {n["id"]: i for i, n in enumerate(nodes)}
    N = len(nodes)

    # ---------- 横坐标：时期 + 年代 ----------
    by_period = defaultdict(list)
    for i, n in enumerate(nodes):
        by_period[pidx.get(n["时期"], 0)].append(i)
    X = [0.0] * N
    for p, members in by_period.items():
        a, z = periods[p]["起"], periods[p]["止"]
        members.sort(key=lambda i: (nodes[i]["年代"] if nodes[i]["年代"] is not None else a, random.random()))
        for r, i in enumerate(members):
            y = nodes[i]["年代"] if nodes[i]["年代"] is not None else a
            t = 0.5 * (y - a) / (z - a) + 0.5 * (r / max(1, len(members) - 1))
            X[i] = p * BAND + 60 + t * (BAND - 120)

    # ---------- 主线固定 ----------
    mt, lk = graph["主线顺序"]["马太"], graph["主线顺序"]["路加"]
    both = set(mt) & set(lk)
    fixed = {}
    for pid in mt:
        fixed[idx[pid]] = 0 if pid in both else -70
    for pid in lk:
        if pid in idx:
            fixed[idx[pid]] = 0 if pid in both else 70
    fixed[idx["Jesus"]] = 0

    # ---------- 纵坐标：力导向（只在纵向和小范围横向移动） ----------
    Y = [fixed.get(i, random.uniform(-1600, 1600)) for i in range(N)]
    X0 = X[:]
    springs = []
    for e in graph["线"]:
        if e["类别"] == "主线" or e["a"] not in idx or e["b"] not in idx:
            continue
        w = PULL[e["类别"]] * (min(e.get("次数", 1), 5) if e["类别"] == "同节" else 1)
        springs.append((idx[e["a"]], idx[e["b"]], w))
    deg = Counter()
    for a, b, w in springs:
        deg[a] += w; deg[b] += w
    R = 46  # 两点之间的最小距离
    for it in range(260):
        cool = 1 - it / 260
        fx, fy = [0.0] * N, [0.0] * N
        for a, b, w in springs:
            dx, dy = X[b] - X[a], Y[b] - Y[a]
            d = math.hypot(dx, dy) + 0.01
            f = w * (d - 60) / d * 0.04
            fx[a] += dx * f; fy[a] += dy * f
            fx[b] -= dx * f; fy[b] -= dy * f
        grid = defaultdict(list)
        for i in range(N):
            grid[(int(X[i] // R), int(Y[i] // R))].append(i)
        for (gx, gy), cell in grid.items():
            near = []
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    near.extend(grid.get((gx + ox, gy + oy), ()))
            for i in cell:
                for j in near:
                    if j <= i:
                        continue
                    dx, dy = X[j] - X[i], Y[j] - Y[i]
                    d = math.hypot(dx, dy)
                    if d < R:
                        if d < 0.01:
                            dx, dy, d = random.uniform(-1, 1), random.uniform(-1, 1), 1
                        push = (R - d) / d * 0.5
                        fx[i] -= dx * push; fy[i] -= dy * push
                        fx[j] += dx * push; fy[j] += dy * push
        for i in range(N):
            if i in fixed:
                continue
            fx[i] += (X0[i] - X[i]) * 0.05          # 横向不能离开自己的年代太远
            fy[i] += -Y[i] * 0.0015                  # 轻轻往中间收
            if abs(Y[i]) < 110:                      # 给主线留出一条通道
                fy[i] += (1 if Y[i] >= 0 else -1) * (110 - abs(Y[i])) * 0.2
            step = 18 * cool + 2
            X[i] += max(-step, min(step, fx[i]))
            Y[i] += max(-step, min(step, fy[i]))
        for i, y in fixed.items():
            Y[i] = y; X[i] = X0[i]
    for i in range(N):
        if i not in fixed:
            Y[i] *= STRETCH

    # ---------- 经文 ----------
    need = set()

    def keep(ref):
        c = to_code(ref)
        if c and c in bible:
            need.add(c)
            return show(c)
        return None

    # ---------- 打包 ----------
    out_nodes = []
    for i, n in enumerate(nodes):
        line = {"马太": 1, "路加": 2, "马太路加": 3}.get(n["主线"], 0)
        first = keep(n["首次"]) if n["首次"] else None
        out_nodes.append([
            n["名"] or "（无名）", round(X[i]), round(Y[i]), n["节数"],
            {"男": 1, "女": 2}.get(n["性别"], 0), pidx.get(n["时期"], 0), n["年代"], line,
            {"高": 0, "中": 1, "低": 2}.get(n["可信度"], 2), n["别名"], first,
            [books.get(b, b) for b in n["书卷"]][:12], n["年代说明"],
        ])
    out_edges = []
    for e in graph["线"]:
        if e["a"] not in idx or e["b"] not in idx:
            continue
        t = TYPES.index(e["类别"])
        refs = [r for r in (keep(x) for x in e.get("经文", [])[:5]) if r]
        info = e.get("说明") or ([e["福音书"]] if e["类别"] == "主线" else [])
        out_edges.append([idx[e["a"]], idx[e["b"]], t, e.get("次数", 1), info, refs])
    out_events = []
    for ev in graph["事件"]:
        ps = [idx[p] for p in ev["参与者"] if p in idx]
        out_events.append([titles.get(ev["英文标题"], ev["英文标题"]), ev["年代"], keep(ev["经文"]) if ev["经文"] else None, ps])

    data = {
        "时期": [[p["名"], p["起"], p["止"]] for p in periods],
        "带宽": BAND,
        "类型": TYPES,
        "点字段": ["名", "x", "y", "节数", "性别", "时期", "年代", "主线", "可信度", "别名", "首次", "书卷", "年代说明"],
        "点": out_nodes,
        "线字段": ["a", "b", "类型", "次数", "说明", "经文"],
        "线": out_edges,
        "事件": out_events,
        "主线": {"马太": [idx[p] for p in mt if p in idx], "路加": [idx[p] for p in lk if p in idx]},
        "经文": {show(c): bible[c] for c in sorted(need)},
        "版本": "和合本（eBible.org cmn-cu89s）",
    }
    os.makedirs(WEB, exist_ok=True)
    with open(os.path.join(WEB, "数据.js"), "w", encoding="utf-8") as fh:
        fh.write("window.圣经数据 = ")
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    print(f"点 {len(out_nodes)}，线 {len(out_edges)}，事件 {len(out_events)}，经文 {len(need)} 节")
    print("未翻译的事件标题：", [ev["英文标题"] for ev in graph["事件"] if ev["英文标题"] not in titles][:10])
    print(f"文件大小：{os.path.getsize(os.path.join(WEB, '数据.js')) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
