"""整理耶稣家谱主线（出自福音书）。

来源：
  中文名：和合本  太 1:1-17、路 3:23-38（数据源/和合本/usfm）
  人物编号与关系：BibleData（数据源/bibledata），每个人有唯一编号，
                 可以区分同名的人（例如路加家谱里有好几个"约瑟"）

做法：
  1. 从和合本经文里按顺序读出家谱里的中文名。
  2. 在 BibleData 里沿着"父→子"关系、并限定在这几节经文里出现的人，走出同一条链。
  3. 两条链逐个配对；配不上就报错，不会悄悄错位。

输出：
  数据/耶稣家谱.json        给网页用
  数据/耶稣家谱核对表.csv    用表格软件打开人工核对

运行：python3 -I 脚本/01_整理耶稣家谱.py
"""
import csv
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USFM = os.path.join(ROOT, "数据源", "和合本", "usfm")
BD = os.path.join(ROOT, "数据源", "bibledata")
OUT = os.path.join(ROOT, "数据")

# eBible 版和合本底本里的已知瑕疵，统一在这里修正
TEXT_FIXES = {
    "\\pn 希斯 \\pn*": "\\pn 希斯仑\\pn*",   # 太 1:3 缺一个"仑"字
    "是该南的儿子": "是\\pn 该南\\pn*的儿子",  # 路 3:37 人名没有标出
}

# 耶稣在 BibleData 里被编为 YHVH_1（与"神"同一编号），图里需要单独一个点
JESUS_ID = "Jesus"


# ---------- 和合本 ----------
def read_chapter(book, chapter):
    path = glob.glob(os.path.join(USFM, f"*-{book}cmn-cu89s.usfm"))[0]
    text = open(path, encoding="utf-8").read()
    for a, b in TEXT_FIXES.items():
        text = text.replace(a, b)
    m = re.search(rf"\\c {chapter}\s(.*?)(?=\\c {chapter + 1}\s|\Z)", text, re.S)
    verses = {}
    for vm in re.finditer(r"\\v (\d+) (.*?)(?=\\v \d+ |\Z)", m.group(1), re.S):
        verses[int(vm.group(1))] = re.sub(r"\\f .*?\\f\*", "", vm.group(2), flags=re.S)
    return verses


def pn(s):
    return [n.strip() for n in re.findall(r"\\pn (.*?)\\pn\*", s)]


def plain(s):
    s = re.sub(r"\\f .*?\\f\*", "", s, flags=re.S)
    s = re.sub(r"\\\+?\w+\*?", "", s)
    return re.sub(r"\s+", "", s)


def cuv_matthew():
    """亚伯拉罕 → 耶稣，返回 [{名, 节, 母亲}] 以及旁支人物"""
    vs = read_chapter("MAT", 1)
    chain = [{"名": "亚伯拉罕", "节": 2, "母亲": None}]
    side = []
    for v in range(2, 17):
        for clause in re.split(r"[；。]", vs[v]):
            if "生" not in clause:
                continue
            before, after = clause.split("生", 1)
            nb, na = pn(before), pn(after)
            if not nb or not na:
                continue
            mother = None
            mm = re.search(r"从\\pn (.*?)\\pn\*氏", before)
            if mm:
                mother = mm.group(1)
            if "乌利亚" in before:
                mother = "拔示巴"          # 经文作"乌利亚的妻子"
                side.append(("乌利亚", "前夫", "拔示巴", v))
            # "生"字前面最后一个人名是父亲（去掉"从某某氏""从乌利亚的妻子"这段）
            father = pn(re.sub(r"从.*$", "", before))[-1]
            if chain[-1]["名"] != father:
                raise SystemExit(f"太1:{v} 断链：{chain[-1]['名']} ≠ {father}")
            chain.append({"名": na[0], "节": v, "母亲": mother})
            # 只有"某和某"并列的才是兄弟（太1:3 法勒斯和谢拉）
            for extra in re.findall(r"\\pn [^\\]*\\pn\*和\\pn (.*?)\\pn\*", after):
                side.append((extra.strip(), "兄弟", na[0], v))
            if "的丈夫" in after:  # 太1:16 约瑟，就是马利亚的丈夫
                side.append((na[1], "妻子", na[0], v))
    chain.append({"名": "耶稣", "节": 16, "母亲": "马利亚"})
    return chain, side, vs


def cuv_luke():
    """耶稣 → 亚当 → 神（往上），返回 [{名, 节}]"""
    vs = read_chapter("LUK", 3)
    seq = [{"名": "耶稣", "节": 23}]
    for v in range(23, 39):
        for clause in re.split(r"[；。]", vs[v]):
            if "的儿子" not in clause:
                continue
            ns = pn(clause)
            name = "神" if "神的儿子" in clause and v == 38 and len(ns) == 1 else ns[-1]
            seq.append({"名": name, "节": v})
    return seq, vs


# ---------- BibleData ----------
def load_bd():
    persons = {r["person_id"]: r for r in csv.DictReader(open(os.path.join(BD, "BibleData-Person.csv"), encoding="utf-8-sig"))}
    in_verse = {}
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonVerse.csv"), encoding="utf-8-sig")):
        in_verse.setdefault(r["reference_id"], []).append(r["person_id"])
    kids = {}
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonRelationship.csv"), encoding="utf-8-sig")):
        if r["relationship_type"] == "father":
            kids.setdefault(r["person_id_1"], set()).add(r["person_id_2"])
        elif r["relationship_type"] == "son":
            kids.setdefault(r["person_id_2"], set()).add(r["person_id_1"])
    return persons, in_verse, kids


def walk(start, book, chapter, verse_range, in_verse, kids):
    pool = set()
    for v in verse_range:
        pool |= set(in_verse.get(f"{book} {chapter}:{v}", []))
    chain = [start]
    while True:
        c = [k for k in kids.get(chain[-1], ()) if k in pool and k not in chain]
        if len(c) > 1:  # 双胞胎（法勒斯和谢拉）：选在家谱里还有后代的那个
            c = [k for k in c if any(g in pool for g in kids.get(k, ()))]
        if len(c) != 1:
            return chain
        chain.append(c[0])


def main():
    persons, in_verse, kids = load_bd()

    # —— 马太
    mt_cuv, mt_side, mt_vs = cuv_matthew()
    # BibleData 每节里的人是按经文出现顺序排的：依次取出，去掉连续重复，
    # 再去掉旁支（母亲们、谢拉、乌利亚、马利亚，以及与"神"同编号的耶稣）
    mt_bd = []
    for v in range(2, 17):
        for pid in in_verse.get(f"MAT 1:{v}", []):
            if pid in ("YHVH_1", "Zerah_3", "Uriah_1") or persons.get(pid, {}).get("sex") == "female":
                continue
            if not mt_bd or mt_bd[-1] != pid:
                mt_bd.append(pid)
    mt_bd.append(JESUS_ID)
    unchecked = [f"{a}→{b}" for a, b in zip(mt_bd, mt_bd[1:-1]) if b not in kids.get(a, ())]
    if len(mt_bd) != len(mt_cuv):
        raise SystemExit(f"马太配对失败：和合本 {len(mt_cuv)} 人，BibleData {len(mt_bd)} 人")

    # —— 路加（BibleData 从亚当往下走，再倒过来）
    lk_cuv, lk_vs = cuv_luke()
    lk_bd = walk("Adam_1", "LUK", 3, range(23, 39), in_verse, kids)[::-1]
    # 抄本差异：BibleData 依据的希腊文本在亚米拿达和希斯仑之间多了"亚德敏"，
    # 而和合本（与英王钦定本相同）没有；和合本在沙拉和亚法撒之间有"该南"，BibleData 没走到。
    lk_bd.remove("Admin_1")
    i = lk_bd.index("Arpachshad_1")
    lk_bd.insert(i, "Cainan_路3:36")
    lk_bd = [JESUS_ID] + lk_bd + ["YHVH_1"]
    if len(lk_bd) != len(lk_cuv):
        raise SystemExit(f"路加配对失败：和合本 {len(lk_cuv)} 人，BibleData {len(lk_bd)} 人")

    def node(pid, zh):
        p = persons.get(pid, {})
        return {"id": pid, "中文名": zh, "英文名": p.get("person_name", "Jesus" if pid == JESUS_ID else ""),
                "简介": p.get("unique_attribute", "")}

    mt = []
    for k, (c, pid) in enumerate(zip(mt_cuv, mt_bd)):
        mt.append({**node(pid, c["名"]), "代": k + 1, "经文": f"太1:{c['节']}", "母亲": c["母亲"]})
    lk = []
    for k, (c, pid) in enumerate(zip(lk_cuv, lk_bd)):
        lk.append({**node(pid, c["名"]), "往上第几代": k, "经文": f"路3:{c['节']}"})

    mt_ids = {x["id"] for x in mt}
    shared = [x["中文名"] for x in lk if x["id"] in mt_ids and x["id"] != JESUS_ID]
    # 从约瑟往上，第一个又和马太重合的人就是分叉点（大卫）
    split_at = next(x for x in lk[2:] if x["id"] in mt_ids)

    side = [{"中文名": a, "关系": rel, "对象": b, "经文": f"太1:{v}"} for a, rel, b, v in mt_side]
    data = {
        "说明": "耶稣家谱主线。马太：亚伯拉罕→大卫→所罗门→……→约瑟→耶稣；路加：耶稣→约瑟→希里→……→拿单→大卫→……→亚当→神。",
        "马太福音": mt,
        "路加福音": lk,
        "马太旁支": side,
        "两条家谱共有的人": shared,
        "两条家谱分开处": f"从{split_at['中文名']}往下分成两支：马太经所罗门，路加经拿单；到约瑟又会合。",
        "马太省略的世代": [
            "约兰→乌西雅：中间省略亚哈谢、约阿施、亚玛谢三王",
            "约西亚→耶哥尼雅：中间省略约雅敬",
            "撒拉铁→所罗巴伯：代上3:19 作毗大雅之子",
            "亚兰→亚米拿达：BibleData 注明为祖孙",
        ],
        "经文原文": {
            "太1": {v: plain(t) for v, t in mt_vs.items() if v <= 17},
            "路3": {v: plain(t) for v, t in lk_vs.items() if v >= 23},
        },
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(data, open(os.path.join(OUT, "耶稣家谱.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(os.path.join(OUT, "耶稣家谱核对表.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["福音书", "序号", "中文名", "经文", "人物编号", "英文名", "母亲", "简介"])
        for x in mt:
            w.writerow(["马太", x["代"], x["中文名"], x["经文"], x["id"], x["英文名"], x["母亲"] or "", x["简介"]])
        for x in lk:
            w.writerow(["路加", x["往上第几代"], x["中文名"], x["经文"], x["id"], x["英文名"], "", x["简介"]])

    print(f"马太 {len(mt)} 人，路加 {len(lk)} 人，两边共有 {len(shared)} 人")
    print("马太中关系表里没有直接父子记录的：", unchecked or "无")
    for x in mt:
        print("太", x["代"], x["中文名"], x["id"])
    for x in lk:
        print("路", x["往上第几代"], x["中文名"], x["id"])


if __name__ == "__main__":
    main()
