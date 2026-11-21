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
import glob
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = os.path.join(ROOT, "数据源", "bibledata")
OUT = os.path.join(ROOT, "数据")
USFM = os.path.join(ROOT, "数据源", "和合本", "usfm")
NAMES = os.path.join(ROOT, "脚本", "对照表", "同名称呼.tsv")
EXTRA = os.path.join(ROOT, "脚本", "对照表", "补充关系.tsv")

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


# ---------- 从经文句式提取人物互动 ----------
# 一节经文里出现"甲 + 动作 + 乙"的句子，就记一条互动。动作写在 ACTIONS 里：
#   (名称, 匹配甲乙之间文字的正则, 乙后面要接的文字（正则，可空）, 句式)
ACTIONS = [
    ("对话", r"(?:就|便|又|也|再|却|乃|遂)?(?:对|向)$", r"^(?:说|问|回答|发誓|讲|宣告)", "{a}对{b}说话"),
    ("对话", r"(?:就|便|又|也)?(?:问|回答|吩咐|嘱咐|劝)$", r"", "{a}对{b}说话"),
    ("杀害", r"(?:就|便|又|也|竟)?(?:杀了|杀死|击杀了?|刺死|打死|治死)$", r"", "{a}杀了{b}"),
    ("杀害", r"(?:想要|要|想|设法|寻索要)(?:杀|害死|击杀)$", r"", "{a}要杀{b}"),
    ("膏立", r"(?:就|便|又)?膏(?:了)?$", r"", "{a}膏{b}"),
    ("立王", r"(?:就|便|又)?立(?:了)?$", r"^(?:作|为)(?:王|.{0,4}王)", "{a}立{b}作王"),
    ("会面", r"(?:去|来|往|进|回|上|下|出)(?:见|朝见|拜见)(?:了)?$|(?:朝见|拜见|迎接|会见)$", r"", "{a}与{b}见面"),
    ("争战", r"(?:攻击|攻打|追赶|围困|击败|打败)$", r"", "{a}攻击{b}"),
    ("争战", r"(?:要|去|来|出去|上去)?(?:与|和|同)$", r"^(?:争战|交战|打仗)", "{a}攻击{b}"),
    ("差遣", r"(?:就|便|又)?(?:差遣|打发|差|派)(?:了|人)?(?:去|往)?$", r"", "{a}差遣{b}"),
    ("祝福", r"(?:就|便|又)?(?:为)?$", r"^祝福", "{a}为{b}祝福"),
    ("祝福", r"(?:就|便|又)?祝福$", r"", "{a}为{b}祝福"),
    ("咒诅", r"(?:就|便|又)?咒诅$", r"", "{a}咒诅{b}"),
    ("责备", r"(?:就|便|又)?(?:责备|斥责)$", r"", "{a}责备{b}"),
    ("下拜", r"(?:就|便|又)?(?:向|在)?$", r"^(?:面前)?(?:下拜|叩拜|俯伏)", "{a}向{b}下拜"),
    ("逃避", r"(?:就|便|又)?(?:逃避|躲避|逃离)$", r"", "{a}逃避{b}"),
    ("服侍", r"(?:就|便|又)?(?:服侍|伺候|侍立在?)$", r"", "{a}服侍{b}"),
    ("拯救", r"(?:就|便|又)?(?:救了|拯救|搭救)$", r"", "{a}救了{b}"),
    ("背叛", r"(?:就|便|又)?(?:背叛|背弃|出卖)$", r"", "{a}背叛了{b}"),
    ("交手", r"(?:就|便|又)?(?:与|和|同)$", r"^(?:立约|结盟)", "{a}与{b}立约"),
]


# 这些名字在经文里多半指国家、支派，不当作某个人
NOT_PERSON = {"以色列", "犹大", "以法莲", "便雅悯", "利未", "以东", "摩押", "亚扪", "埃及", "雅各"}


def extract_interactions(people, zh):
    """返回 [(甲编号, 乙编号, 动作名称, 说明, 经文)]"""
    names_of = {}
    for p in people:
        names_of[p["id"]] = {n for n in (p["中文名"], *p["别名"]) if n}
    in_verse = defaultdict(list)
    for p in people:
        for ref in p["经文"]:
            in_verse[ref].append(p["id"])
    out = []
    pn = re.compile(r"\\pn ([^\\]+?)\s*\\pn\*")
    for path in sorted(glob.glob(os.path.join(USFM, "*.usfm"))):
        raw = open(path, encoding="utf-8").read()
        m = re.search(r"\\id (\w+)", raw)
        if not m:
            continue
        book = m.group(1)
        # 创世记里雅各、犹大、利未等是人；之后多半指支派或国家
        skip_np = {"以色列"} if book == "GEN" else NOT_PERSON
        for cm in re.finditer(r"\\c (\d+)\s(.*?)(?=\\c \d+\s|\Z)", raw, re.S):
            for vm in re.finditer(r"\\v (\d+)(?:-\d+)? (.*?)(?=\\v \d+|\Z)", cm.group(2), re.S):
                ref = f"{book} {cm.group(1)}:{vm.group(1)}"
                ids = in_verse.get(ref)
                if not ids or len(ids) < 2:
                    continue
                text = re.sub(r"\\f .*?\\f\*", "", vm.group(2), flags=re.S)
                text = re.sub(r"\\(?:add|nd|wj|qt|k)\*?\s?", "", text)
                # 以句为单位（到句号、问号、叹号或引号为止）；逗号不断句，好找回省略的主语
                for sent in re.split(r"[。！？「」『』]", text):
                    hits = [h for h in pn.finditer(sent)]
                    for j, B in enumerate(hits):
                        if j == 0:
                            continue
                        start = max(hits[j - 1].end(), sent.rfind("，", 0, B.start()) + 1, sent.rfind("；", 0, B.start()) + 1)
                        gap = sent[start:B.start()]
                        tail = sent[B.end():B.end() + 8]
                        if "\\" in gap or len(gap) > 12 or "被" in gap or "的" in gap:
                            continue
                        if tail.startswith(("人", "族", "支派", "的", "城", "地", "王的")):
                            continue
                        gap = re.sub(r"^(?:王|先知|祭司|大祭司|巡抚|元帅|就|便|又)+", "", gap)
                        action = None
                        for name, gre, tre, pat in ACTIONS:
                            if re.search(gre, gap) and (not tre or re.match(tre, tail)):
                                action = (name, pat); break
                        if not action:
                            continue
                        if B.group(1) in skip_np:
                            continue
                        b_ids = [x for x in ids if B.group(1) in names_of[x]]
                        if len(b_ids) != 1:
                            continue
                        # 主语：这一句里第一个人名（不能是"某某的……"、"某某人"、"某某被……"）
                        a_id = None
                        for A in hits[:j]:
                            after = sent[A.end():A.end() + 1]
                            if after in ("的", "人", "族", "城", "地", "被") or A.group(1) in skip_np:
                                continue
                            cand = [x for x in ids if A.group(1) in names_of[x]]
                            if len(cand) == 1 and cand[0] != b_ids[0]:
                                a_id = cand[0]
                            break
                        if a_id:
                            out.append((a_id, b_ids[0], action[0], action[1].format(a=zh[a_id], b=zh[b_ids[0]]), ref))
    return out


def display_names(people, base, override, rows):
    """同名的人加区分：人工对照表 > 父母（某某之子）> 配偶 > 子女 > 首次出现的书卷章"""
    book_short = {}
    for path in glob.glob(os.path.join(USFM, "*.usfm")):
        head = open(path, encoding="utf-8").read(400)
        m, t = re.search(r"\\id (\w+)", head), re.search(r"\\toc3 (\S+)", head)
        if m and t:
            book_short[m.group(1)] = t.group(1)
    sex = {p["id"]: p["性别"] for p in people}
    parent, spouse, child = {}, {}, {}
    for a, b, t, ref, _ in rows:
        if t in ("father", "mother"):
            if t == "father" or b not in parent:
                parent[b] = a
            child.setdefault(a, b)
        elif t in ("son", "daughter"):
            parent.setdefault(a, b); child.setdefault(b, a)
        elif t == "husband":
            spouse.setdefault(b, ("妻", a)); spouse.setdefault(a, ("夫", b))
        elif t == "wife":
            spouse.setdefault(a, ("妻", b)); spouse.setdefault(b, ("夫", a))
    out = {pid: override.get(pid, n) for pid, n in base.items()}
    groups = defaultdict(list)
    for p in people:
        groups[base[p["id"]]].append(p)
    for name, ps in groups.items():
        if len(ps) < 2:
            continue
        ps.sort(key=lambda p: -p["出现节数"])
        for k, p in enumerate(ps):
            pid = p["id"]
            if pid in override or k == 0 or pid == "Jesus":
                continue  # 出现最多的那位保留原名
            if pid in parent and base.get(parent[pid]):
                q = base[parent[pid]] + ("之女" if sex.get(pid) == "女" else "之子")
            elif pid in spouse and base.get(spouse[pid][1]):
                q = base[spouse[pid][1]] + ("的妻子" if spouse[pid][0] == "妻" else "的丈夫")
            elif pid in child and base.get(child[pid]):
                q = base[child[pid]] + ("之母" if sex.get(pid) == "女" else "之父")
            elif p["首次出现"]:
                b, cv = p["首次出现"].split()
                q = "首见" + book_short.get(b, b) + cv.split(":")[0]
            else:
                continue
            out[pid] = f"{name}（{q}）"
    # 还重名的，再补上首次出现
    seen = defaultdict(list)
    for p in people:
        seen[out[p["id"]]].append(p)
    for n, ps in seen.items():
        if len(ps) > 1 and "（" in n:
            for p in ps:
                if p["首次出现"]:
                    b, cv = p["首次出现"].split()
                    out[p["id"]] = n[:-1] + "，首见" + book_short.get(b, b) + cv.split(":")[0] + "）"
    return out


def main():
    people = json.load(open(os.path.join(OUT, "人物.json"), encoding="utf-8"))
    lineage = json.load(open(os.path.join(OUT, "耶稣家谱.json"), encoding="utf-8"))
    # 图上显示的名字：人工对照表优先（同名的人加区分、无名的人给称呼）
    override = {r["人物编号"]: r["图上显示的名字"] for r in csv.DictReader(open(NAMES, encoding="utf-8"), delimiter="\t")}
    base = {p["id"]: p["中文名"] or override.get(p["id"]) or "无名氏" for p in people}

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
    zh = display_names(people, base, override, rows)

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

    # ---------- 经文句式提取的互动 ----------
    inter = extract_interactions(people, zh)
    for a, b, name, text, ref in inter:
        key = tuple(sorted((a, b)))
        e = rel_edges.setdefault(key, {"a": key[0], "b": key[1], "类别": "社会", "说明": [], "经文": []})
        if text not in e["说明"]:
            e["说明"].append(text)
            if ref not in e["经文"]:
                e["经文"].append(ref)
    print(f"经文句式提取的互动 {len(inter)} 处：", dict(Counter(x[2] for x in inter)))

    # ---------- 人工补充的关系（脚本/对照表/补充关系.tsv）----------
    #   原数据的"社会关系"很少（全本只有几十条），审判、同工、师生这类要靠人工补充
    occ_refs = {p["id"]: set(p["经文"]) for p in people}

    def resolve(token, ref):
        if token in zh:
            return token
        cands = [p["id"] for p in people
                 if token in (p["中文名"], zh[p["id"]], *p["别名"]) and ref in occ_refs[p["id"]]]
        if not cands:  # 这节没收这个人，就放宽到同一章
            ch = ref.rsplit(":", 1)[0] + ":"
            cands = [p["id"] for p in people
                     if token in (p["中文名"], zh[p["id"]], *p["别名"]) and any(r.startswith(ch) for r in occ_refs[p["id"]])]
        return cands[0] if len(cands) == 1 else None

    bad = []
    for r in csv.DictReader(open(EXTRA, encoding="utf-8"), delimiter="\t"):
        a, b = resolve(r["甲"], r["经文"]), resolve(r["乙"], r["经文"])
        if not a or not b:
            bad.append(f'{r["甲"]} - {r["乙"]}（{r["经文"]}）')
            continue
        key = tuple(sorted((a, b)))
        e = rel_edges.setdefault(key, {"a": key[0], "b": key[1], "类别": r["类别"], "说明": [], "经文": []})
        if e["类别"] != "亲属":
            e["类别"] = r["类别"]
        if r["说明"] not in e["说明"]:
            e["说明"].insert(0, r["说明"])
        if r["经文"] not in e["经文"]:
            e["经文"].insert(0, r["经文"])
    if bad:
        print("补充关系里对不上人物的：", bad)

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
            "id": p["id"], "名": zh[p["id"]], "本名": base[p["id"]], "别名": p["别名"], "性别": p["性别"], "简介": p["简介"],
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
