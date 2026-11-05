"""منطق العلاقات (بدون flet وبدون supabase) ليسهل اختباره."""
import datetime as _dt

KINDS = {
    "شخص جديد (ذكر)": ("new", "M"), "شخص جديد (أنثى)": ("new", "F"),
    "أب": ("father", "M"), "أم": ("mother", "F"),
    "أخ": ("sibling", "M"), "أخت": ("sibling", "F"),
    "ابن": ("child", "M"), "ابنة": ("child", "F"),
    "زوج": ("spouse", "M"), "زوجة": ("spouse", "F"),
}

RELATIONS = [
    ("الأب", ["father"]), ("الأم", ["mother"]),
    ("الجد", ["parent", "father"]), ("الجدة", ["parent", "mother"]),
    ("الأخ", ["sibling:M"]), ("الأخت", ["sibling:F"]),
    ("الابن", ["child:M"]), ("الابنة", ["child:F"]),
    ("الحفيد", ["child", "child:M"]), ("الحفيدة", ["child", "child:F"]),
    ("العم", ["father", "sibling:M"]), ("العمة", ["father", "sibling:F"]),
    ("الخال", ["mother", "sibling:M"]), ("الخالة", ["mother", "sibling:F"]),
    ("ابن الأخ", ["sibling:M", "child:M"]), ("ابنة الأخ", ["sibling:M", "child:F"]),
    ("ابن الأخت", ["sibling:F", "child:M"]), ("ابنة الأخت", ["sibling:F", "child:F"]),
    ("الزوج", ["spouse:M"]), ("الزوجة", ["spouse:F"]),
]


def build_spouses(people, marriages):
    sp = {i: set() for i in people}
    for m in marriages:
        a, b = m["person1_id"], m["person2_id"]
        if a in sp and b in sp:
            sp[a].add(b)
            sp[b].add(a)
    return sp


def step(people, spouses, current, s):
    name, _, g = s.partition(":")
    out = set()
    for p in current:
        x = people[p]
        if name == "father":
            out.add(x["father_id"])
        elif name == "mother":
            out.add(x["mother_id"])
        elif name == "parent":
            out |= {x["father_id"], x["mother_id"]}
        elif name == "child":
            out |= {i for i, y in people.items() if p in (y["father_id"], y["mother_id"])}
        elif name == "sibling":
            out |= {i for i, y in people.items() if i != p and (
                (x["father_id"] and y["father_id"] == x["father_id"]) or
                (x["mother_id"] and y["mother_id"] == x["mother_id"]))}
        elif name == "spouse":
            out |= spouses.get(p, set())
    out.discard(None)
    out = {i for i in out if i in people}
    if g:
        out = {i for i in out if people[i]["gender"] == g}
    return out


def relatives(people, spouses, pid):
    """[(عنوان العلاقة, [ids مرتبة بالاسم])]"""
    result = []
    for title, steps in RELATIONS:
        cur = {pid}
        for s in steps:
            cur = step(people, spouses, cur, s)
        if cur:
            result.append((title, sorted(cur, key=lambda i: people[i]["ar_name"])))
    return result


def roots(people):
    """الجذور: من ليس له أب ولا أم (أجداد العائلة)."""
    return sorted((p for p in people.values() if not p["father_id"] and not p["mother_id"]),
                  key=lambda p: p["id"])


def marital_status(person, marriages):
    f = person["gender"] == "F"
    mine = [m for m in marriages if person["id"] in (m["person1_id"], m["person2_id"])]
    if person.get("is_deceased"):
        return "متوفاة" if f else "متوفى"
    sts = {m["status"] for m in mine}
    if "married" in sts:
        return "متزوجة" if f else "متزوج"
    if "widowed" in sts:
        return "أرملة" if f else "أرمل"
    if "divorced" in sts:
        return "مطلقة" if f else "مطلق"
    return "عزباء" if f else "أعزب"


def validate_add(people, spouses, ref, label):
    """يرجع نص الخطأ أو None."""
    code, g = KINDS[label]
    if code == "new":
        return None
    if ref is None:
        return "اختر الشخص المرجع أولًا"
    r = people[ref]
    if code in ("father", "mother"):
        if r[code + "_id"]:
            return "هذا الشخص لديه " + ("أب" if code == "father" else "أم") + " بالفعل"
    elif code == "sibling":
        if not (r["father_id"] or r["mother_id"]):
            return "أضف أبًا أو أمًا لهذا الشخص أولًا"
    elif code == "spouse":
        if g == r["gender"]:
            return "الزوجان يجب أن يكونا من جنسين مختلفين"
    return None


def child_parents(people, spouses, ref):
    """(father_id, mother_id) لابن جديد للشخص ref."""
    mates = list(spouses.get(ref, set()))
    other = mates[0] if len(mates) == 1 else None
    return (ref, other) if people[ref]["gender"] == "M" else (other, ref)


def parse_date(s):
    """'' -> (True, None) ؛ 'YYYY-MM-DD' صحيح -> (True, 'YYYY-MM-DD') ؛ غير ذلك -> (False, None)"""
    s = (s or "").strip()
    if not s:
        return True, None
    try:
        return True, _dt.date.fromisoformat(s).isoformat()
    except ValueError:
        return False, None
