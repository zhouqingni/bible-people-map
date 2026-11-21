"""给 BibleData 的全部人物找到和合本里的中文名。

思路（投票 + 排除）：
  · 和合本每节经文里的人名、地名都用 \\pn 标出；BibleData 记录了每个人出现在哪些节、那节里怎么称呼他。
  · 以"某人 + 某个称呼"为单位投票。同一个人会有不同称呼：雅各又叫以色列，西门又叫彼得、矶法。
    在这个称呼出现的那些节里，哪个中文名出现得最"稳"，就对应哪个中文名。
  · 地名先单独定下来（BibleData 和 Theographic 两份地点数据），占掉的名字不会被当成人名。
  · 只出现一两次的人，同一节里候选名有好几个：先排除已确定的人和地点占用的名字；
    还分不出来，就按经文里的先后顺序对位（BibleData 每节的人物是按出场顺序排的）。
  · 每个结果都标可信度（高 / 中 / 低）。中、低的列进核对表，方便人工抽查。

特别处理：
  · 和合本不给"耶稣""神""法老""撒但"这类名字加人名标记，这些按 MANUAL 表处理。
  · BibleData 的 YHVH_1 同时指神和耶稣：新约里称呼为 Jesus / Christ 等的归"耶稣"，其余归"神"；
    YHVH_2（天父）也并入"神"。
  · BibleData 的 NA 是"未具名的人"的占位，不算人物。

输出：
  数据/人物.json       全部人物
  数据/地点名.json      和合本里被判定为地名的名字（供后续脚本排除用）
  数据/人名核对表.csv   可信度为中、低的人物，按出现次数排序

运行：python3 -I 脚本/02_全本人物中文名.py
"""
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USFM = os.path.join(ROOT, "数据源", "和合本", "usfm")
BD = os.path.join(ROOT, "数据源", "bibledata")
THEO = os.path.join(ROOT, "数据源", "theographic", "json")
OUT = os.path.join(ROOT, "数据")

TEXT_FIXES = {
    "\\pn 希斯 \\pn*": "\\pn 希斯仑\\pn*",
    "是该南的儿子": "是\\pn 该南\\pn*的儿子",
}

NT = {"MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
      "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"}
JESUS_WORDS = ("Jesus", "Christ", "Son of Man", "Son of G-d", "Son of David", "Messiah", "Lamb", "Nazarene",
               "King of the Jews", "Rabbi", "Teacher", "Master", "Savior", "Son")

# 和合本没有加人名标记的称呼：英文称呼 → 中文（只有该节经文里真的出现这个中文词才算）
MANUAL = {
    "Pharaoh": "法老", "Satan": "撒但", "the devil": "魔鬼", "Devil": "魔鬼",
    "the angel of the LORD": "耶和华的使者", "angel of the LORD": "耶和华的使者",
    "the angel of G-d": "神的使者", "angel of G-d": "神的使者",
}
# 一律固定的人物
FIXED = {"YHVH_1": "神", "YHVH_2": "神", "Jesus": "耶稣"}
MERGE = {"YHVH_2": "YHVH_1"}
# 主名指定：出现最多的称呼不是大家习惯的叫法时（雅各在经文里更多被称为"以色列"，但那多半指国家）
MAIN_NAME = {"Jacob_1": "雅各"}
SKIP = {"NA"}
# 不放进人物图的：神（BibleData 里圣灵也记在这个编号下）。耶稣已在前面单独分出来
EXCLUDE = {"YHVH_1"}

BOOK_ORDER = []


def load_cuv():
    names, plain = {}, {}
    for path in sorted(glob.glob(os.path.join(USFM, "*.usfm"))):
        text = open(path, encoding="utf-8").read()
        m = re.search(r"\\id (\w+)", text)
        if not m or m.group(1) in ("FRT", "GLO", "INT", "BAK", "OTH"):
            continue
        book = m.group(1)
        BOOK_ORDER.append(book)
        for a, b in TEXT_FIXES.items():
            text = text.replace(a, b)
        for cm in re.finditer(r"\\c (\d+)\s(.*?)(?=\\c \d+\s|\Z)", text, re.S):
            ch = cm.group(1)
            for vm in re.finditer(r"\\v (\d+)(?:-\d+)? (.*?)(?=\\v \d+|\Z)", cm.group(2), re.S):
                body = re.sub(r"\\f .*?\\f\*", "", vm.group(2), flags=re.S)
                ref = f"{book} {ch}:{vm.group(1)}"
                ns = [n.strip().replace(" ", "") for n in re.findall(r"\\pn (.*?)\\pn\*", body)]
                names[ref] = [n for n in ns if n]
                plain[ref] = re.sub(r"\s+", "", re.sub(r"\\\+?\w+\*?", "", body))
    return names, plain


def load_people():
    persons = {r["person_id"]: r for r in csv.DictReader(open(os.path.join(BD, "BibleData-Person.csv"), encoding="utf-8-sig"))}
    occ = defaultdict(list)  # 人物id → [(经文, 顺序, 称呼)]
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PersonVerse.csv"), encoding="utf-8-sig")):
        pid, ref, label = r["person_id"], r["reference_id"], r["person_label"].strip()
        if pid in SKIP:
            continue
        pid = MERGE.get(pid, pid)
        if pid == "YHVH_1" and ref.split()[0] in NT and any(w in label for w in JESUS_WORDS):
            pid = "Jesus"
        occ[pid].append((ref, int(r["person_verse_sequence"] or 0), label))
    return persons, occ


def load_places(order):
    """两份地点数据 → {地点键: 经文集合}"""
    out = defaultdict(set)
    for r in csv.DictReader(open(os.path.join(BD, "BibleData-PlaceVerse.csv"), encoding="utf-8-sig")):
        out["BD:" + r["place_id"]].add(r["reference_id"])
    books = {x["fields"]["osisName"]: order[x["fields"]["bookOrder"] - 1] for x in json.load(open(os.path.join(THEO, "books.json")))}
    vid = {}
    for x in json.load(open(os.path.join(THEO, "verses.json"))):
        b, c, v = x["fields"]["osisRef"].split(".")
        vid[x["id"]] = f"{books[b]} {c}:{v}"
    for x in json.load(open(os.path.join(THEO, "places.json"))):
        f = x["fields"]
        for v in f.get("verses") or []:
            if v in vid:
                out["TH:" + f["placeLookup"]].add(vid[v])
    return out


def main():
    cuv, plain = load_cuv()
    persons, occ = load_people()
    places = load_places(BOOK_ORDER)

    name_verses = defaultdict(set)
    for ref, ns in cuv.items():
        for n in set(ns):
            name_verses[n].add(ref)
    claimed = defaultdict(set)  # 经文 → 已被占用的名字

    def rank(vs):
        cnt = Counter()
        for v in vs:
            for n in set(cuv[v]) - claimed[v]:
                cnt[n] += 1
        out = [(c / len(vs), c / len(name_verses[n]), n) for n, c in cnt.items()]
        out.sort(reverse=True)
        return out

    def decisive(r):
        if not r:
            return None
        second = r[1][0] if len(r) > 1 else 0
        if r[0][0] >= 0.5 and r[0][0] - second >= 0.2:
            return r[0]
        return None

    # ---- 第一步：地名
    place_names = Counter()
    place_zh = {}  # 英文地名（小写）→ 中文地名，给"King of 某地"用
    for _ in range(3):
        for key, vs in sorted(places.items(), key=lambda kv: -len(kv[1])):
            vs = [v for v in vs if v in cuv]
            if not vs:
                continue
            d = decisive(rank(vs))
            if d and d[0] >= 0.6:
                place_zh.setdefault(re.sub(r"_\d+$", "", key.split(":", 1)[1]).lower(), d[2])
                place_names[d[2]] += len(vs)
                for v in vs:
                    claimed[v].add(d[2])
    # 一个名字主要是作为人名出现（如"以撒"），不能因为某地点数据误收而算地名：留给后面人物投票再判断
    # 只有一半以上出现都是作地名用的，才算地名（"大卫"也出现在"大卫城"，但主要是人名）
    place_set = {n for n, c in place_names.items() if c >= 0.5 * len(name_verses[n])}

    # ---- 第二步：人物，以"人物 + 称呼"为单位
    units = defaultdict(list)  # (人物, 称呼) → 经文
    for pid, lst in occ.items():
        for ref, seq, label in lst:
            if ref in cuv:
                units[(pid, label)].append(ref)
    for u in units:
        units[u] = sorted(set(units[u]))

    def is_title(label):
        # "king of Israel""the king""son of man""man of G-d" 这类是称号，不是名字，不拿来对人名
        return (not label[:1].isupper()) or label.startswith(("The ", "King ", "Son ", "Lord ")) \
            or " of " in label or label in ("Father", "Son", "King", "Lord", "Teacher", "Master")

    result = {}  # 单位 → (中文名, 可信度, 依据)
    for u, vs in units.items():
        pid, label = u
        if pid in FIXED:
            result[u] = (FIXED[pid], "高", "固定")
        elif label in MANUAL:
            hit = sum(1 for v in vs if MANUAL[label] in plain[v])
            if hit / len(vs) >= 0.5:
                result[u] = (MANUAL[label], "高", "和合本未标人名，按对照表")
        elif label.startswith("King of "):
            # 没有名字的王：用经文里的"某某王"，如"摩押王""以东王"
            x = label[8:].replace("the sons of ", "").replace("the ", "").lower()
            zh = place_zh.get(x)
            if zh and any(zh in plain[v] for v in vs):
                result[u] = (zh + "王", "高", "无名的王：地名 + 王")
            else:
                cnt = Counter(n for v in vs for n in set(cuv[v]) if n + "王" in plain[v])
                result[u] = (cnt.most_common(1)[0][0] + "王", "低", "无名的王，取经文里的「某某王」") if cnt \
                    else (None, "低", "称号")
        elif is_title(label):
            result[u] = (None, "低", "称号")

    # 人名的占用：确定一个单位，就在它的经文里占掉这个名字。地名的占用先撤掉，
    # 让人物有机会拿回被地点数据误占的名字（如"以色列"既是人也是国）。
    claimed = defaultdict(set)

    # ---- 同英文名合并投票：所有叫 Joseph 的人一起投，得出"Joseph = 约瑟"，
    #      再分给每一个只出现一两次的约瑟（只要他那节经文里确实有"约瑟"）
    by_label = defaultdict(list)
    for u in units:
        if u not in result:
            by_label[u[1]].append(u)
    group_name = {}
    for label, us in by_label.items():
        vs = sorted({v for u in us for v in units[u]})
        r = [x for x in rank(vs) if x[2] not in place_set or x[0] >= 0.9]
        d = decisive(r)
        if d and (len(us) > 1 or len(vs) >= 3):
            group_name[label] = d
    for u, vs in units.items():
        if u in result or u[1] not in group_name:
            continue
        cov, _, zh = group_name[u[1]]
        hit = sum(1 for v in vs if zh in cuv[v])
        if hit / len(vs) >= 0.5:
            result[u] = (zh, "高" if cov >= 0.8 else "中", f"同英文名的人合并投票（{cov:.0%}）")
            for v in vs:
                claimed[v].add(zh)
    for _ in range(8):
        changed = 0
        for u in sorted(units, key=lambda x: -len(units[x])):
            if u in result:
                continue
            vs = units[u]
            # 排除：同节里已确定的人名，以及地名（除非这个名字在本单位的经文里几乎每节都有）
            r = rank(vs)
            r = [x for x in r if x[2] not in place_set or x[0] >= 0.9]
            d = decisive(r)
            if d:
                result[u] = (d[2], "高" if d[0] >= 0.8 else "中", f"出现在该称呼 {d[0]:.0%} 的经文中")
                for v in vs:
                    claimed[v].add(d[2])
                changed += 1
        if not changed:
            break

    # ---- 读音相似度：从已确定的人名里学"英文首字母 ↔ 中文首字"的对应
    #      （A 多对"亚"，P 多对"毗/波"，Z 多对"撒/西"……），用来在同一节的几个候选名里挑
    def syll(s):
        return max(1, len(re.findall(r"[aeiouy]+", s.lower())))

    def key_first(s):
        return s[:1].upper()

    def key_last(s):
        return s[-1:].lower()

    pf, pl, cf, cl = Counter(), Counter(), Counter(), Counter()
    for (pid, label), (zh, conf, why) in result.items():
        if zh and conf == "高" and pid not in FIXED and label not in MANUAL and label[:1].isalpha():
            pf[(zh[0], key_first(label))] += 1; cf[zh[0]] += 1
            pl[(zh[-1], key_last(label))] += 1; cl[zh[-1]] += 1

    import math

    def sound(label, zh):
        a = math.log((pf[(zh[0], key_first(label))] + 0.2) / (cf[zh[0]] + 5))
        b = math.log((pl[(zh[-1], key_last(label))] + 0.2) / (cl[zh[-1]] + 5))
        return a + 0.5 * b - 0.6 * abs(len(zh.replace("·", "")) - syll(label))

    # ---- 第三步：同节里未确定的人 ↔ 未被占用的名字，按读音配对
    verse_units = defaultdict(list)
    for pid, lst in occ.items():
        for ref, seq, label in lst:
            verse_units[ref].append((seq, (pid, label)))
    for ref in verse_units:
        seen, ordered = set(), []
        for _, u in sorted(verse_units[ref]):
            if u not in seen:
                seen.add(u); ordered.append(u)
        verse_units[ref] = ordered

    for _ in range(4):
        changed = 0
        votes = defaultdict(Counter)
        for v, ulist in verse_units.items():
            if v not in cuv:
                continue
            pending = [u for u in ulist if u not in result]
            if not pending:
                continue
            free = []
            for n in cuv[v]:
                if n not in claimed[v] and n not in place_set and n not in free:
                    free.append(n)
            if not free or len(free) < len(pending):
                continue
            # 贪心配对：读音最像的先配
            pairs = sorted(((sound(u[1], n), u, n) for u in pending for n in free), reverse=True)
            used_u, used_n = set(), set()
            for s, u, n in pairs:
                if u in used_u or n in used_n:
                    continue
                used_u.add(u); used_n.add(n)
                # 和该人的第二候选比，差距越大越可信
                alt = max((sound(u[1], m) for m in free if m != n), default=-99)
                votes[u][n] += 1 + min(2, max(0, s - alt))
        for u, c in votes.items():
            (n, s), *rest = c.most_common()
            if rest and rest[0][1] >= s * 0.8:
                continue
            margin = s / sum(c.values()) if rest else 1
            result[u] = (n, "中" if s >= 1.5 or not rest else "低", "同节候选按读音配对")
            for v in units[u]:
                claimed[v].add(n)
            changed += 1
        if not changed:
            break

    for u, vs in units.items():
        if u in result:
            continue
        r = [x for x in rank(vs) if x[2] not in place_set] if vs else []
        if r:
            top = max(x[0] for x in r)
            best = max((x for x in r if x[0] >= top - 0.01), key=lambda x: sound(u[1], x[2]))
            result[u] = (best[2], "低", "候选并列，按读音挑")
        else:
            result[u] = (None, "低", "该称呼在和合本里没有对应的人名")

    # ---- 汇总到人物
    book_idx = {b: i for i, b in enumerate(BOOK_ORDER)}

    def vkey(ref):
        b, cv = ref.split()
        c, v = cv.split(":")
        return (book_idx.get(b, 99), int(c), int(v.split("-")[0]))

    rank_conf = {"高": 0, "中": 1, "低": 2}
    people_out = []
    for pid, lst in occ.items():
        labels = Counter(label for _, _, label in lst)
        named = []  # (中文名, 可信度, 出现次数, 称呼)
        for label, cnt in labels.most_common():
            zh, conf, why = result.get((pid, label), (None, "低", ""))
            if zh:
                named.append((zh, conf, cnt, label, why))
        # 主名：出现最多、可信度不是"低"、且不是地名/国名的那个称呼（雅各不显示成"以色列"）
        main = None
        if pid in MAIN_NAME:
            main = next((c for c in named if c[0] == MAIN_NAME[pid]), None)
        for cand in ([] if main else named):
            if cand[1] != "低" and cand[0] not in place_set:
                main = cand; break
        if not main:
            main = next((c for c in named if c[1] != "低"), named[0] if named else (None, "低", 0, "", "没有找到中文名"))
        aliases = []
        for zh, conf, cnt, label, why in named:
            if zh != main[0] and conf != "低" and zh not in aliases and zh not in place_set:
                aliases.append(zh)
        refs = sorted({ref for ref, _, _ in lst}, key=vkey)
        books = []
        for ref in refs:
            b = ref.split()[0]
            if b not in books:
                books.append(b)
        p = persons.get(pid, {})
        people_out.append({
            "id": pid,
            "中文名": main[0],
            "别名": aliases,
            "可信度": main[1],
            "依据": main[4],
            "英文名": p.get("person_name") or ("Jesus" if pid == "Jesus" else ""),
            "英文称呼": [l for l, _ in labels.most_common(4)],
            "性别": "男" if pid == "Jesus" else {"male": "男", "female": "女"}.get(p.get("sex"), ""),
            "支派": p.get("tribe", ""),
            "简介": "拿撒勒人耶稣" if pid == "Jesus" else p.get("unique_attribute", ""),
            "出现节数": len(refs),
            "首次出现": refs[0] if refs else None,
            "书卷": books,
            "经文": refs,
        })

    # 神（含圣灵，BibleData 里同一编号）是全书的作者和主角，不放进人物关系图；耶稣保留
    people_out = [r for r in people_out if r["id"] not in EXCLUDE]
    people_out.sort(key=lambda r: -r["出现节数"])
    os.makedirs(OUT, exist_ok=True)
    json.dump(people_out, open(os.path.join(OUT, "人物.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(sorted(place_set), open(os.path.join(OUT, "地点名.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    with open(os.path.join(OUT, "人名核对表.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["人物编号", "中文名", "别名", "可信度", "依据", "英文称呼", "出现节数", "首次出现", "简介"])
        for r in people_out:
            if r["可信度"] != "高":
                w.writerow([r["id"], r["中文名"] or "", "、".join(r["别名"]), r["可信度"], r["依据"],
                            " / ".join(r["英文称呼"]), r["出现节数"], r["首次出现"], r["简介"]])

    c = Counter(r["可信度"] for r in people_out)
    print(f"人物 {len(people_out)}：高 {c['高']}，中 {c['中']}，低 {c['低']}；地名 {len(place_set)} 个")
    for r in people_out[:45]:
        print(r["id"], r["中文名"], r["别名"], r["可信度"], r["出现节数"])


if __name__ == "__main__":
    main()
