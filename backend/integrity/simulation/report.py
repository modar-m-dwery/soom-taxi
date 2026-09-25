"""
تقرير المحاكاة: الذروة (عرض/طلب بالساعة) والنزاهة (من انكشف، من فلت، ومن
اتُّهم ظلمًا) — بأرقام من القاعدة نفسها لا من عدّادات المحاكي.
"""

from collections import Counter, defaultdict

from integrity import registry
from integrity.models import LEVEL_ORDER, RiskLevel, RiskNote, RiskProfile, RiskSignal
from integrity.simulation.world import ACCOMPLICE, CUSTOMER_CHEATS, DRIVER_CHEATS, HONEST


def _is_cheater(persona):
    return persona != HONEST


def _label(persona):
    if persona.startswith(ACCOMPLICE):
        base = persona.split(":", 1)[1] if ":" in persona else ""
        return f"شريك «{DRIVER_CHEATS.get(base, base)}»"
    return DRIVER_CHEATS.get(persona) or CUSTOMER_CHEATS.get(persona) or "نظاميّ"


def build(world):
    truth = world.ground_truth()
    profiles = {
        p.user_id: p for p in RiskProfile.objects.filter(user_id__in=list(truth))
    }
    signals = defaultdict(list)
    for s in RiskSignal.objects.filter(user_id__in=list(truth)).order_by("created_at"):
        signals[s.user_id].append(s)
    notes = defaultdict(list)
    for n in RiskNote.objects.filter(user_id__in=list(truth)).order_by("created_at"):
        notes[n.user_id].append(n.text)

    def level(uid):
        p = profiles.get(uid)
        return p.effective_level() if p else RiskLevel.CLEAR

    def flagged(uid, at_least):
        return LEVEL_ORDER[level(uid)] >= LEVEL_ORDER[at_least]

    # ------------------------------------------------------------ الدقّة
    metrics = {}
    for threshold in (RiskLevel.WATCH, RiskLevel.REVIEW):
        tp = fp = fn = tn = 0
        for uid, (_, persona, _) in truth.items():
            is_flagged = flagged(uid, threshold)
            is_cheat = _is_cheater(persona)
            if is_flagged and is_cheat:
                tp += 1
            elif is_flagged:
                fp += 1
            elif is_cheat:
                fn += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        metrics[threshold] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3), "recall": round(recall, 3),
        }

    # ------------------------------------------------------------ لكلّ شخصيّة
    per_persona = defaultdict(lambda: Counter())
    for uid, (role, persona, _) in truth.items():
        key = (role, persona)
        per_persona[key]["accounts"] += 1
        per_persona[key][level(uid)] += 1
        if flagged(uid, RiskLevel.WATCH):
            per_persona[key]["caught"] += 1

    rows = []
    for (role, persona), c in sorted(per_persona.items(), key=lambda kv: (kv[0][0], kv[0][1] == HONEST, kv[0][1])):
        rows.append({
            "role": role, "persona": persona, "label": _label(persona),
            "accounts": c["accounts"], "caught": c["caught"],
            "watch": c[RiskLevel.WATCH], "review": c[RiskLevel.REVIEW],
            "restricted": c[RiskLevel.RESTRICTED],
        })

    # ------------------------------------------------------------ أمثلة
    def account_story(uid):
        role, persona, noise = truth[uid]
        p = profiles.get(uid)
        return {
            "user_id": uid, "role": role, "persona": persona, "label": _label(persona),
            "noise": noise, "score": p.score if p else 0, "level": level(uid),
            "signals": [
                f"{s.kind_label} (وزن {s.weight})" for s in signals[uid][:6]
            ],
            "notes": notes[uid][-3:],
        }

    false_positives = [
        account_story(uid) for uid, (_, persona, _) in truth.items()
        if not _is_cheater(persona) and flagged(uid, RiskLevel.WATCH)
    ]
    missed = [
        account_story(uid) for uid, (_, persona, _) in truth.items()
        if _is_cheater(persona) and not flagged(uid, RiskLevel.WATCH)
    ]
    caught_examples = sorted(
        (account_story(uid) for uid, (_, persona, _) in truth.items()
         if _is_cheater(persona) and flagged(uid, RiskLevel.WATCH)),
        key=lambda r: -r["score"],
    )

    # ------------------------------------------------------------ الذروة
    peak = []
    for (day, hour), b in sorted(world.hourly.items()):
        steps_per_hour = max(1, 60 // world.step)
        online = round(b["online"] / steps_per_hour)
        peak.append({
            "day": day, "hour": hour, "requests": b["requests"], "matched": b["matched"],
            "expired": b["expired"], "online_drivers": online,
            "avg_wait_min": round(b["wait_min_total"] / b["wait_n"], 1) if b["wait_n"] else None,
        })

    signal_totals = Counter(
        s.kind for uid in truth for s in signals[uid]
    )

    return {
        "config": {
            "days": world.days, "drivers": world.n_drivers, "customers": len(world.customers),
            "cheat_ratio": world.cheat_ratio, "ramadan": world.ramadan, "step_minutes": world.step,
            "area": getattr(world.area, "name", ""),
        },
        "counts": world.counts,
        "metrics": {k.value if hasattr(k, "value") else k: v for k, v in metrics.items()},
        "per_persona": rows,
        "signals_by_kind": {
            (registry.KINDS[k].label if k in registry.KINDS else k): n
            for k, n in signal_totals.most_common()
        },
        "false_positives": false_positives,
        "missed": missed,
        "caught_examples": caught_examples[:12],
        "peak": peak,
        "errors": world.errors,
    }


def to_markdown(data):
    c = data["config"]
    lines = [
        "# تقرير محاكاة المدينة",
        "",
        f"- المنطقة: {c['area']} · الأيّام: {c['days']} · السائقون: {c['drivers']} · "
        f"الزبائن: {c['customers']} · نسبة الغشّاشين: {int(c['cheat_ratio'] * 100)}٪ · "
        f"رمضان: {'نعم' if c['ramadan'] else 'لا'}",
        "",
        "## الحركة",
        "",
        "| الطلبات | العروض | اكتملت | انتهت بلا سائق | ألغاها الزبون | ألغاها السائق | شكاوى | مواقع مرفوضة |",
        "|---|---|---|---|---|---|---|---|",
        "| {requests} | {offers} | {completed} | {expired} | {cust_cancel} | {drv_cancel} | {complaints} | {gps_rejected} |".format(**data["counts"]),
        "",
        "## دقّة كشف الغش",
        "",
        "| العتبة | صحيح (غشّاش انكشف) | اتّهام ظالم | غشّاش فلت | الدقّة | الاستدعاء |",
        "|---|---|---|---|---|---|",
    ]
    names = {"watch": "تحت المراقبة فأعلى", "review": "بحاجة مراجعة فأعلى"}
    for key, m in data["metrics"].items():
        lines.append(
            f"| {names.get(key, key)} | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{int(m['precision'] * 100)}٪ | {int(m['recall'] * 100)}٪ |"
        )
    lines += [
        "",
        "> **الدقّة**: من كلّ من علّمهم النظام، كم منهم غشّاش فعلًا. **الاستدعاء**: من كلّ الغشّاشين، كم منهم انكشف.",
        "",
        "## حسب الشخصيّة",
        "",
        "| الدور | الشخصيّة | الحسابات | انكشف | مراقبة | مراجعة | مقيّد |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data["per_persona"]:
        role = "سائق" if r["role"] == "driver" else "زبون"
        lines.append(
            f"| {role} | {r['label']} | {r['accounts']} | {r['caught']} | "
            f"{r['watch']} | {r['review']} | {r['restricted']} |"
        )
    lines += ["", "## الإشارات حسب النمط", ""]
    for label, n in data["signals_by_kind"].items():
        lines.append(f"- {label}: {n}")

    def stories(title, items, empty):
        out = ["", f"## {title}", ""]
        if not items:
            return out + [empty]
        for s in items:
            role = "سائق" if s["role"] == "driver" else "زبون"
            noise = f" (ضوضاء: {s['noise']})" if s["noise"] else ""
            out.append(f"- **{role} #{s['user_id']}** — {s['label']}{noise} — النقاط {s['score']} — {RiskLevel(s['level']).label}")
            for sig in s["signals"]:
                out.append(f"  - {sig}")
            for note in s["notes"]:
                out.append(f"  - ملاحظة: {note}")
        return out

    lines += stories("أمثلة ممّن انكشفوا (مع الملاحظات والتعيينات)", data["caught_examples"], "—")
    lines += stories("اتّهامات ظالمة (نظاميّون علّمهم النظام)", data["false_positives"], "لا أحد ✅")
    lines += stories("غشّاشون فلتوا", data["missed"], "لا أحد ✅")

    lines += [
        "",
        "## الذروة: العرض والطلب بالساعة",
        "",
        "| اليوم | الساعة | طلبات | تطابقت | بلا سائق | سائقون أونلاين | انتظار وسطيّ (د) |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in data["peak"]:
        if p["requests"] == 0 and p["online_drivers"] == 0:
            continue
        wait = "—" if p["avg_wait_min"] is None else p["avg_wait_min"]
        lines.append(
            f"| {p['day']} | {p['hour']:02d} | {p['requests']} | {p['matched']} | "
            f"{p['expired']} | {p['online_drivers']} | {wait} |"
        )
    if data["errors"]:
        lines += ["", "## أخطاء أثناء التشغيل (من خدمات المنصّة)", ""]
        for k, n in sorted(data["errors"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {n}× {k}")
    return "\n".join(lines) + "\n"
