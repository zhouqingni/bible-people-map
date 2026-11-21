"""整理全本人物关系，合成给网页用的图数据。

关系线三类：
  亲属  父子、母子、夫妻、兄弟姐妹、祖孙、后裔等（BibleData 关系表）
  社会  主仆、师徒、君臣、盟友、杀害者与被害者等（BibleData 关系表）
  同节  在同一节经文里一起出现（BibleData 出场表）。最多，覆盖"认识、说过话"这类关系

另外标出耶稣家谱主线（马太、路加），来自 数据/耶稣家谱.json。

需要先运行：01_整理耶稣家谱.py、02_全本人物中文名.py
输出：
  数据/关系.json    全部关系线
  数据/图数据.json  点 + 线，给网页直接用

运行：python3 -I 脚本/03_全本关系.py
"""
import csv
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = os.path.join(ROOT, "数据源", "bibledata")
OUT = os.path.join(ROOT, "数据")

NT = {"MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
      "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"}
JESUS_WORDS = ("Jesus", "Christ", "Son of Man", "Son of G-d", "Son of David", "Messiah", "Lamb", "Nazarene",
               "King of the Jews", "Rabbi", "Teacher", "Master", "Savior", "Son")
MERGE = {"YHVH_2": "YHVH_1"}
SKIP = {"NA"}

# 关系类型：英文 → (类别, 句式)。句式里 {a}{b} 代入人名，读作"A 是 B 的……"
REL = {
    "father": ("亲属", "{a}是{b}的父亲"), "mother": ("亲属", "{a}是{b}的母亲"),
    "son": ("亲属", "{a}是{b}的儿子"), "daughter": ("亲属", "{a}是{b}的女儿"),
    "husband": ("亲属", "{a}是{b}的丈夫"), "wife": ("亲属", "{a}是{b}的妻子"),
    "concubinator": ("亲属", "{b}是{a}的妾"), "concubine": ("亲属", "{a}是{b}的妾"),
    "brother": ("亲属", "{a}是{b}的兄弟"), "sister": ("亲属", "{a}是{b}的姐妹"),
    "half-brother": ("亲属", "{a}是{b}的异母（或异父）兄弟"), "half-sister": ("亲属", "{a}是{b}的异母（或异父）姐妹"),
    "grandfather": ("亲属", "{a}是{b}的祖父"), "grandmother": ("亲属", "{a}是{b}的祖母"),
    "grandson": ("亲属", "{a}是{b}的孙子"), "granddaughter": ("亲属", "{a}是{b}的孙女"),
    "ancestor": ("亲属", "{a}是{b}的祖先"), "descendant": ("亲属", "{a}是{b}的后裔"),
    "uncle": ("亲属", "{a}是{b}的叔伯（或舅舅）"), "aunt": ("亲属", "{a}是{b}的姑姨"),
    "nephew": ("亲属", "{a}是{b}的侄子（或外甥）"), "cousin": ("亲属", "{a}是{b}的堂（表）亲"),
    "father-in-law": ("亲属", "{a}是{b}的岳父（或公公）"), "mother-in-law": ("亲属", "{a}是{b}的岳母（或婆婆）"),
    "son-in-law": ("亲属", "{a}是{b}的女婿"), "daughter-in-law": ("亲属", "{a}是{b}的儿媳"),
    "brother-in-law": ("亲属", "{a}是{b}的姻亲兄弟"), "sister-in-law": ("亲属", "{a}是{b}的姻亲姐妹"),
    "bearer": ("亲属", "{a}生了{b}"), "born by": ("亲属", "{a}由{b}所生"),
    "raper": ("社会", "{a}玷污了{b}"),
    "Creator": ("社会", "{a}创造了{b}"), "creation": ("社会", "{a}是{b}所造的"),
    "master": ("社会", "{a}是{b}的主人"), "servant": ("社会", "{a}是{b}的仆人"),
    "lady": ("社会", "{a}是{b}的主母"),
    "rabbi": ("社会", "{a}是{b}的老师"), "disciple": ("社会", "{a}是{b}的门徒"),
    "apostle": ("社会", "{a}是{b}的使徒"),
    "king": ("社会", "{a}是{b}的王"), "chief": ("社会", "{a}是{b}的首领"),
    "chief official": ("社会", "{a}是{b}的大臣"), "officer": ("社会", "{a}是{b}的官员"),
    "chamberlain": ("社会", "{a}是{b}的内侍"), "lieutenant": ("社会", "{a}是{b}的副将"),
    "army commander": ("社会", "{a}是{b}的元帅"), "army captain": ("社会", "{a}是{b}的军长"),
    "ally": ("社会", "{a}是{b}的盟友"), "patron": ("社会", "{a}是{b}的恩主"), "client": ("社会", "{a}受{b}的庇护"),
    "killer": ("社会", "{a}杀了{b}"), "killed by": ("社会", "{a}被{b}所杀"), "victim": ("社会", "{a}被{b}所害"),
    "exiled": ("社会", "{a}掳走了{b}"), "exiled by": ("社会", "{a}被{b}掳走"),
    "original heir": ("社会", "{b}原是{a}的继承人"), "original inheritor": ("社会", "{a}原是{b}的继承人"),
}
# 一对关系在表里通常正反各记一次（暗兰是摩西的父亲 / 摩西是暗兰的儿子），只保留前一种说法
REVERSE_OF = {
    "son": {"father", "mother"}, "daughter": {"father", "mother"}, "wife": {"husband"},
    "concubine": {"concubinator"}, "descendant": {"ancestor"}, "grandson": {"grandfather", "grandmother"},
    "granddaughter": {"grandfather", "grandmother"}, "nephew": {"uncle", "aunt"},
    "son-in-law": {"father-in-law", "mother-in-law"}, "daughter-in-law": {"father-in-law", "mother-in-law"},
    "born by": {"bearer"}, "creation": {"Creator"}, "servant": {"master", "lady", "king", "chief"},
    "disciple": {"rabbi"}, "apostle": {"rabbi"}, "killed by": {"killer"}, "victim": {"killer"},
    "exiled by": {"exiled"}, "original inheritor": {"original heir"}, "client": {"patron"},
    "officer": {"king"}, "chief official": {"king"}, "chamberlain": {"king"}, "lieutenant": {"army commander"},
}
# 对称关系（兄弟、姻亲、盟友）：同一对人只留一句
SYMMETRIC = {"brother", "sister", "half-brother", "half-sister", "brother-in-law", "sister-in-law", "cousin", "ally"}


def who(pid, ref, label=""):
    """统一人物编号：合并天父、把新约里的 YHVH_1 分给耶稣"""
    pid = MERGE.get(pid, pid)
    if pid == "YHVH_1" and ref.split()[0] in NT and (not label or any(w in label for w in JESUS_WORDS)):
        return "Jesus"
    return pid


def main():
    people = json.load(open(os.path.join(OUT, "人物.json"), encoding="utf-8"))
    lineage = json.load(open(os.path.join(OUT, "耶稣家谱.json"), encoding="utf-8"))
    zh = {p["id"]: p["中文名"] or (p["英文称呼"][0] if p["英文称呼"] else p["id"]) for p in people}

    # ---------- 亲属 / 社会 ----------
    rows = []
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonRelationship.csv"), encoding="utf-8-sig")):
        a, b, t, ref = r["person_id_1"], r["person_id_2"], r["relationship_type"], r["reference_id"]
        if a in SKIP or b in SKIP or t not in REL:
            continue
        a, b = who(a, ref), who(b, ref)
        if a == b:
            continue
        rows.append((a, b, t, ref, r["relationship_category"]))
    have = {(a, b, t) for a, b, t, _, _ in rows}

    rel_edges = {}
    for a, b, t, ref, how in rows:
        if any((b, a, p) in have for p in REVERSE_OF.get(t, ())):
            continue  # 反向说法已经有了
        cat, pat = REL[t]
        key = tuple(sorted((a, b)))
        e = rel_edges.setdefault(key, {"a": key[0], "b": key[1], "类别": cat, "说明": [], "经文": []})
        if cat == "亲属":
            e["类别"] = "亲属"
        s = pat.format(a=zh.get(a, a), b=zh.get(b, b))
        if t in SYMMETRIC:
            e.setdefault("_对称", set())
            if t in e["_对称"] or ({"brother", "sister"} & e["_对称"] and t in ("brother", "sister")):
                continue
            e["_对称"].add(t)
        if s not in e["说明"]:
            e["说明"].append(s)
        if ref and ref not in e["经文"]:
            e["经文"].append(ref)

    # ---------- 同节共现 ----------
    in_verse = defaultdict(set)
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonVerse.csv"), encoding="utf-8-sig")):
        pid = r["person_id"]
        if pid in SKIP:
            continue
        in_verse[r["reference_id"]].add(who(pid, r["reference_id"], r["person_label"]))
    co = Counter()
    co_refs = defaultdict(list)
    for ref, ps in in_verse.items():
        ps = sorted(ps)
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                k = (ps[i], ps[j])
                co[k] += 1
                if len(co_refs[k]) < 5:
                    co_refs[k].append(ref)
    co_edges = [{"a": a, "b": b, "类别": "同节", "次数": n, "经文": co_refs[(a, b)]} for (a, b), n in co.items()]

    for e in rel_edges.values():
        e.pop("_对称", None)
        # 师徒之间又记了"主人"（耶稣与十二门徒），保留"老师"一句就够了
        if any("的老师" in x for x in e["说明"]):
            e["说明"] = [x for x in e["说明"] if "的主人" not in x]
    edges = list(rel_edges.values()) + co_edges
    # 只保留两端都是图中人物的线（神不在图里，和神相连的线一并去掉）
    ids = {p["id"] for p in people} | {x["id"] for x in lineage["路加福音"] if x["id"] != "YHVH_1"}
    edges = [e for e in edges if e["a"] in ids and e["b"] in ids]
    json.dump(edges, open(os.path.join(OUT, "关系.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    # ---------- 图数据：点 + 线 ----------
    mt_ids = [x["id"] for x in lineage["马太福音"]]
    lk_ids = [x["id"] for x in lineage["路加福音"]]
    nodes = []
    known = set()
    for p in people:
        known.add(p["id"])
        nodes.append({
            "id": p["id"], "名": zh[p["id"]], "别名": p["别名"], "性别": p["性别"], "简介": p["简介"],
            "可信度": p["可信度"], "节数": p["出现节数"], "首次": p["首次出现"], "书卷": p["书卷"],
            "主线": ("马太" if p["id"] in mt_ids else "") + ("路加" if p["id"] in lk_ids else ""),
        })
    for x in lineage["路加福音"]:  # 路 3:36 的该南在 BibleData 里没有
        if x["id"] not in known and x["id"] != "YHVH_1":
            nodes.append({"id": x["id"], "名": x["中文名"], "别名": [], "性别": "男", "简介": "路3:36 家谱中的人物",
                          "可信度": "高", "节数": 1, "首次": "LUK 3:36", "书卷": ["LUK"], "主线": "路加"})
            known.add(x["id"])
    main_edges = []
    lk_ids = [i for i in lk_ids if i != "YHVH_1"]  # 路加家谱末尾"亚当是神的儿子"，神不在图里
    for chain, name in ((mt_ids, "马太"), (lk_ids, "路加")):
        for x, y in zip(chain, chain[1:]):
            main_edges.append({"a": x, "b": y, "类别": "主线", "福音书": name})

    graph = {
        "说明": "点 = 人物；线的类别：主线（耶稣家谱）、亲属、社会、同节（同一节经文里一起出现）",
        "点": nodes,
        "线": main_edges + edges,
        "主线顺序": {"马太": mt_ids, "路加": lk_ids},
    }
    json.dump(graph, open(os.path.join(OUT, "图数据.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    c = Counter(e["类别"] for e in edges)
    deg = Counter()
    for e in edges:
        deg[e["a"]] += 1; deg[e["b"]] += 1
    lonely = [n for n in nodes if deg[n["id"]] == 0]
    print(f"点 {len(nodes)} 个；线：亲属 {c['亲属']}，社会 {c['社会']}，同节 {c['同节']}，主线 {len(main_edges)}")
    print(f"没有任何连线的人：{len(lonely)}")
    print("连线最多的人：", [(zh.get(k, k), v) for k, v in deg.most_common(12)])


if __name__ == "__main__":
    main()
