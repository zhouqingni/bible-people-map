"""给每个人定年代和时期，并加上"同一事件"关系线。

年代来源（按优先顺序）：
  1. 生卒年：Theographic 里有明确生卒年的约 70 人，取壮年（洪水前的长寿者取中点）。
  2. 经文年代：Theographic 给约九成经文标了大约年份（乌雪年表系，创世为公元前 4003 年）。
     取此人出现过的叙事经文里偏早的年份（第 25 百分位），代表他"在世活动"的时候。
     家谱章节（如代上 1-9 章、太 1 章、路 3 章）不算，因为那里的年份是成书时代，不是本人的时代。
  3. 亲属推算：只出现在家谱里的人，按"父母比子女早一代（约 30 年）、兄弟夫妻同代"推算；
     夹在两个已知年代的人中间的，会被均匀摊开（例如路加家谱大卫到耶稣之间的 40 代）。
  4. 书卷年代：上面都推不出来的，用他第一次出现那卷书的中位年份。

年代只是大概，用来在时间轴上排顺序，不是考证结论。

需要先运行：02、03
输出：
  数据/时间轴.json   每个人的年代、时期、来源；时期列表；事件列表
  数据/图数据.json   加上年代、时期字段和"事件"类关系线（就地更新）

运行：python3 -I 脚本/04_时间轴.py
"""
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = os.path.join(ROOT, "数据源", "bibledata")
THEO = os.path.join(ROOT, "数据源", "theographic", "json")
USFM = os.path.join(ROOT, "数据源", "和合本", "usfm")
OUT = os.path.join(ROOT, "数据")

NT = {"MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
      "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"}
JESUS_WORDS = ("Jesus", "Christ", "Son of Man", "Son of G-d", "Son of David", "Messiah", "Lamb", "Nazarene",
               "King of the Jews", "Rabbi", "Teacher", "Master", "Savior", "Son")

# 家谱、名单章节：(书卷, 章, 起节, 止节)，止节 999 表示到章末
GENEALOGY = [
    ("GEN", 5, 1, 999), ("GEN", 10, 1, 999), ("GEN", 11, 10, 32), ("GEN", 25, 1, 4), ("GEN", 25, 12, 18),
    ("GEN", 36, 1, 999), ("GEN", 46, 8, 27), ("EXO", 6, 14, 25), ("NUM", 1, 5, 16), ("NUM", 26, 1, 999),
    ("RUT", 4, 18, 22), *[("1CH", c, 1, 999) for c in range(1, 10)], ("EZR", 2, 1, 999), ("EZR", 10, 18, 44),
    ("NEH", 7, 6, 73), ("NEH", 10, 1, 27), ("NEH", 11, 1, 999), ("NEH", 12, 1, 26),
    ("MAT", 1, 1, 17), ("LUK", 3, 23, 38),
]

# 时期：(名称, 起年, 止年)，负数为公元前
PERIODS = [
    ("太初", -4100, -2348), ("洪水之后", -2348, -1921), ("族长", -1921, -1706), ("寄居埃及", -1706, -1491),
    ("出埃及与旷野", -1491, -1451), ("进迦南与士师", -1451, -1095), ("统一王国", -1095, -975),
    ("南北分裂", -975, -586), ("被掳与归回", -586, -400), ("两约之间", -400, -5),
    ("耶稣在世", -5, 33), ("使徒时期", 33, 110),
]
GEN = 30          # 一代约 30 年
NO_YEAR = {"YHVH_1"}  # 神不放在时间轴上
# 人工指定的年代（推算明显偏离的，在这里改，并写明理由）
YEAR_FIX = {
    "Cyrus_1": (-538, "古列（塞鲁士）下诏归回，拉1:1"),
}


def who(pid, ref, label=""):
    pid = {"YHVH_2": "YHVH_1"}.get(pid, pid)
    if pid == "YHVH_1" and ref.split()[0] in NT and (not label or any(w in label for w in JESUS_WORDS)):
        return "Jesus"
    return pid


def is_genealogy(ref):
    b, cv = ref.split()
    c, v = cv.split(":")
    c, v = int(c), int(v.split("-")[0])
    return any(b == gb and c == gc and a <= v <= z for gb, gc, a, z in GENEALOGY)


def period_of(y):
    if y is None:
        return None
    for name, a, z in PERIODS:
        if a <= y < z:
            return name
    return PERIODS[0][0] if y < PERIODS[0][1] else PERIODS[-1][0]


def fmt_year(y):
    return f"约公元前 {-y} 年" if y < 0 else f"约公元 {y} 年"


def main():
    graph = json.load(open(os.path.join(OUT, "图数据.json"), encoding="utf-8"))
    nodes = {n["id"]: n for n in graph["点"]}

    # ---------- Theographic：经文年份、人物、事件 ----------
    books = json.load(open(os.path.join(THEO, "books.json")))
    order = []
    for path in sorted(glob.glob(os.path.join(USFM, "*.usfm"))):
        m = re.search(r"\\id (\w+)", open(path, encoding="utf-8").read(200))
        h = re.search(r"\\h (\S+)", open(path, encoding="utf-8").read(400))
        if m:
            order.append((m.group(1), h.group(1) if h else m.group(1)))
    usfm_code = [c for c, _ in order]
    zh_book = dict(order)
    osis2usfm = {b["fields"]["osisName"]: usfm_code[b["fields"]["bookOrder"] - 1] for b in books}

    verse_year, vid2ref = {}, {}
    for x in json.load(open(os.path.join(THEO, "verses.json"))):
        b, c, v = x["fields"]["osisRef"].split(".")
        ref = f"{osis2usfm[b]} {c}:{v}"
        vid2ref[x["id"]] = ref
        if x["fields"].get("yearNum") is not None:
            verse_year[ref] = x["fields"]["yearNum"]

    # 书卷中位年份（兜底用）
    by_book = defaultdict(list)
    for ref, y in verse_year.items():
        by_book[ref.split()[0]].append(y)
    book_year = {b: sorted(ys)[len(ys) // 2] for b, ys in by_book.items()}

    # ---------- BibleData：每人出现的经文 ----------
    occ = defaultdict(set)
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonVerse.csv"), encoding="utf-8-sig")):
        if r["person_id"] == "NA":
            continue
        occ[who(r["person_id"], r["reference_id"], r["person_label"])].add(r["reference_id"])
    for x in graph["主线顺序"]["路加"]:
        if x not in occ and x in nodes:
            occ[x].add(nodes[x]["首次"])

    # ---------- Theographic 人物 → BibleData 人物（看经文重合度） ----------
    bd_by_verse = defaultdict(set)
    for pid, refs in occ.items():
        for ref in refs:
            bd_by_verse[ref].add(pid)
    theo_to_bd = {}
    theo_people = json.load(open(os.path.join(THEO, "people.json")))
    for x in theo_people:
        f = x["fields"]
        refs = {vid2ref[v] for v in f.get("verses") or [] if v in vid2ref}
        if not refs:
            continue
        cand = Counter()
        for ref in refs:
            for pid in bd_by_verse[ref]:
                cand[pid] += 1
        if f.get("personLookup", "").startswith("jesus_"):
            theo_to_bd[x["id"]] = "Jesus"; continue
        best = None
        for pid, n in cand.most_common(5):
            if pid == "YHVH_1":
                continue
            same_name = f["name"].lower() == (nodes.get(pid, {}).get("英文") or pid.rsplit("_", 1)[0]).lower()
            score = n / min(len(refs), len(occ[pid])) + (0.3 if same_name else 0)
            if score >= 0.6 and (best is None or score > best[0]):
                best = (score, pid)
        if best:
            theo_to_bd[x["id"]] = best[1]

    # ---------- 年代 ----------
    year, source = {}, {}
    # 1. 生卒年
    for x in theo_people:
        f = x["fields"]
        pid = theo_to_bd.get(x["id"])
        if not pid or not f.get("birthYear"):
            continue
        try:
            b = int(f["birthYear"]); d = int(f["deathYear"]) if f.get("deathYear") else b + 60
        except ValueError:
            continue
        # 取壮年：30 岁以后、去世前 40 年内（摩西 80 岁才领百姓出埃及）；洪水前的长寿者取中点
        year[pid] = (b + d) // 2 if d - b > 150 else max(b + 30, d - 40)
        source[pid] = f"生卒年（约 {b}～{d}）"
    # 2. 经文年代
    for pid, refs in occ.items():
        if pid in year or pid in NO_YEAR:
            continue
        ys = sorted(verse_year[r] for r in refs if r in verse_year and not is_genealogy(r))
        if ys:
            # 取第 25 百分位：既不被预言里提前点名拉得太早（以赛亚书提到古列），也不被后人追述拉得太晚
            year[pid] = ys[len(ys) // 4] if len(ys) >= 4 else ys[0]
            source[pid] = f"出现经文的年代（{len(ys)} 节）"
    for pid, (y, why) in YEAR_FIX.items():
        year[pid] = y; source[pid] = f"人工指定（{why}）"
    fixed = set(year)

    # 3. 亲属推算：边 (a, b, 偏移) 表示 year[b] ≈ year[a] + 偏移
    OFF = {"father": GEN, "mother": GEN, "son": -GEN, "daughter": -GEN, "grandfather": 2 * GEN,
           "grandmother": 2 * GEN, "grandson": -2 * GEN, "granddaughter": -2 * GEN,
           "husband": 0, "wife": 0, "brother": 0, "sister": 0, "half-brother": 0, "half-sister": 0}
    nb = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonRelationship.csv"), encoding="utf-8-sig")):
        t = r["relationship_type"]
        if t not in OFF or "NA" in (r["person_id_1"], r["person_id_2"]):
            continue
        a, b = who(r["person_id_1"], r["reference_id"]), who(r["person_id_2"], r["reference_id"])
        if a == b or a in NO_YEAR or b in NO_YEAR:
            continue
        nb[b].append((a, OFF[t])); nb[a].append((b, -OFF[t]))
    for chain in graph["主线顺序"].values():  # 家谱主线：前一位是后一位的父亲（马太往下，路加往上）
        pass
    mt, lk = graph["主线顺序"]["马太"], graph["主线顺序"]["路加"]
    for x, y in zip(mt, mt[1:]):
        nb[y].append((x, GEN)); nb[x].append((y, -GEN))
    for x, y in zip(lk[1:], lk[2:]):  # 路加：后一位是前一位的父亲（跳过"神"）
        if y in NO_YEAR:
            continue
        nb[x].append((y, GEN)); nb[y].append((x, -GEN))

    est = dict(year)
    for _ in range(300):
        moved = 0
        for pid in nb:
            if pid in fixed:
                continue
            vals = [est[q] + off for q, off in nb[pid] if q in est]
            if vals:
                new = round(sum(vals) / len(vals))
                if est.get(pid) != new:
                    est[pid] = new; moved += 1
        if not moved:
            break
    for pid in est:
        if pid not in fixed:
            source[pid] = "按亲属关系推算"

    # 4. 书卷年代兜底
    for pid in nodes:
        if pid in est or pid in NO_YEAR:
            continue
        first = nodes[pid]["首次"]
        if first and first.split()[0] in book_year:
            est[pid] = book_year[first.split()[0]]
            source[pid] = f"首次出现的书卷（{zh_book.get(first.split()[0], '')}）的年代"

    # ---------- 事件 ----------
    events = []
    ev_edges = {}
    for x in json.load(open(os.path.join(THEO, "events.json"))):
        f = x["fields"]
        ps = sorted({theo_to_bd[p] for p in f.get("participants") or [] if p in theo_to_bd})
        refs = [vid2ref[v] for v in f.get("verses") or [] if v in vid2ref]
        try:
            y = int(f.get("startDate")) if f.get("startDate") not in (None, "") else None
        except ValueError:
            y = None
        if refs:
            b, cv = refs[0].split()
            where = f"{zh_book.get(b, b)} {cv}"
        else:
            where = ""
        events.append({"id": f.get("eventID") or x["id"], "英文标题": f.get("title"), "年代": y,
                       "时期": period_of(y), "经文": where, "参与者": ps})
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                k = (ps[i], ps[j])
                e = ev_edges.setdefault(k, {"a": ps[i], "b": ps[j], "类别": "事件", "经文": [], "次数": 0})
                e["次数"] += 1
                if where and len(e["经文"]) < 5:
                    e["经文"].append(where)

    # ---------- 写回 ----------
    timeline = {}
    for pid, n in nodes.items():
        y = est.get(pid)
        n["年代"] = y
        n["时期"] = period_of(y) if y is not None else ("超越时间" if pid in NO_YEAR else None)
        n["年代说明"] = (fmt_year(y) + "，依据：" + source.get(pid, "")) if y is not None else ""
        timeline[pid] = {"名": n["名"], "年代": y, "时期": n["时期"], "依据": source.get(pid, "")}
    graph["线"] = [e for e in graph["线"] if e["类别"] != "事件"] + list(ev_edges.values())
    graph["时期"] = [{"名": a, "起": b, "止": c} for a, b, c in PERIODS]
    graph["事件"] = events
    graph["说明"] = "点 = 人物；线的类别：主线（耶稣家谱）、亲属、社会、事件（同一事件）、同节（同一节经文里一起出现）"
    json.dump(graph, open(os.path.join(OUT, "图数据.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"时期": graph["时期"], "人物": timeline, "事件": events},
              open(os.path.join(OUT, "时间轴.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    src = Counter(s.split("（")[0] for s in source.values())
    print(f"有年代的人：{sum(1 for p in nodes if est.get(p) is not None)} / {len(nodes)}")
    print("年代来源：", dict(src))
    print("各时期人数：", dict(Counter(n["时期"] for n in nodes.values())))
    print(f"Theographic 人物对上 {len(theo_to_bd)} 个；事件 {len(events)} 个，事件关系线 {len(ev_edges)} 条")


if __name__ == "__main__":
    main()
