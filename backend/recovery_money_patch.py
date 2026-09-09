from pathlib import Path
import re

path = Path(__file__).with_name("server.py")
text = path.read_text(encoding="utf-8")

# General insights: remove unreliable monetary/value and CPW calculations + response fields.
pattern = re.compile(
    r'''    total_items = len\(items\)\n    total_wears = sum\(it\.get\("wear_count", 0\) for it in items\)\n    priced = \[it for it in items if it\.get\("price"\)\]\n    total_value = sum\(it\.get\("price", 0\) for it in priced\)\n\n    def cpw\(it\):\n        wc = it\.get\("wear_count", 0\)\n        return \(it\["price"\] / wc\) if it\.get\("price"\) and wc > 0 else None\n\n    avg_cpw_vals = \[cpw\(it\) for it in items if cpw\(it\) is not None\]\n    avg_cpw = round\(sum\(avg_cpw_vals\) / len\(avg_cpw_vals\), 2\) if avg_cpw_vals else None\n'''
)
text, n = pattern.subn(
    '    total_items = len(items)\n    total_wears = sum(it.get("wear_count", 0) for it in items)\n',
    text,
    count=1,
)
if n != 1:
    raise SystemExit(f"general insight money calculation block: expected 1 match, found {n}")

old = '''        "total_items": total_items,\n        "total_wears": total_wears,\n        "total_value": round(total_value, 2),\n        "avg_cost_per_wear": avg_cpw,\n        "outfits_logged": len(logs),\n'''
new = '''        "total_items": total_items,\n        "total_wears": total_wears,\n        "outfits_logged": len(logs),\n'''
if text.count(old) != 1:
    raise SystemExit(f"general insight response fields: expected 1 match, found {text.count(old)}")
text = text.replace(old, new, 1)

# Wardrobe Health: base report on wear history/category balance only, no prices or money.
health_pattern = re.compile(
    r'''    unworn = \[it for it in items if \(it\.get\("wear_count", 0\) or 0\) == 0\]\n    unworn_value = round\(sum\(it\.get\("price", 0\) or 0 for it in unworn\), 2\)\n    total_value = round\(sum\(it\.get\("price", 0\) or 0 for it in items\), 2\)\n\n    def cpw\(it\):\n        wc = it\.get\("wear_count", 0\) or 0\n        return \(it\["price"\] / wc\) if it\.get\("price"\) and wc > 0 else None\n\n    high_cpw = sorted\(\n        \[it for it in items if cpw\(it\) is not None\],\n        key=lambda x: cpw\(x\), reverse=True,\n    \)\[:3\]\n    high_cpw_desc = "; "\.join\(f"\{it\['name'\]\} \(\$\{cpw\(it\):\.2f\}/wear\)" for it in high_cpw\) or "none yet"\n'''
)
replacement = '''    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]\n    low_wear = sorted(\n        items,\n        key=lambda it: ((it.get("wear_count", 0) or 0), it.get("last_worn") or ""),\n    )[:8]\n    low_wear_desc = "; ".join(\n        f"{it.get('name')} ({it.get('category')}, worn {it.get('wear_count', 0) or 0}x)"\n        for it in low_wear\n    ) or "none yet"\n'''
text, n = health_pattern.subn(replacement, text, count=1)
if n != 1:
    raise SystemExit(f"health money calculation block: expected 1 match, found {n}")

old_prompt = '''    prompt = (\n        f"Total pieces: {len(items)}. Total wardrobe value: ${total_value}.\\n"\n        f"Pieces not yet worn: {len(unworn)} worth ${unworn_value}.\\n"\n        f"Highest cost-per-wear items: {high_cpw_desc}.\\n"\n        f"Category breakdown: {breakdown}.\\n\\n"\n        "Write the monthly wardrobe health report. Frame the numbers as underused pieces and "\n        "opportunities to wear more, never as wasted money, and name the single purchase that "\n        "would unlock the most outfits. Return JSON only."\n    )\n'''
new_prompt = '''    prompt = (\n        f"Total pieces: {len(items)}.\\n"\n        f"Pieces not yet worn: {len(unworn)}.\\n"\n        f"Lowest-wear pieces: {low_wear_desc}.\\n"\n        f"Category breakdown: {breakdown}.\\n\\n"\n        "Write the monthly wardrobe health report using wear history and category balance only. "\n        "Focus on underused pieces and practical rotation opportunities. Do not mention purchase "\n        "price, wardrobe value, money or cost-per-wear. Name the single purchase that would unlock "\n        "the most outfits. Return JSON only."\n    )\n'''
if text.count(old_prompt) != 1:
    raise SystemExit(f"health prompt block: expected 1 match, found {text.count(old_prompt)}")
text = text.replace(old_prompt, new_prompt, 1)

old_stats = '''    result["stats"] = {\n        "total_items": len(items),\n        "total_value": total_value,\n        "unworn_count": len(unworn),\n        "unworn_value": unworn_value,\n    }\n'''
new_stats = '''    result["stats"] = {\n        "total_items": len(items),\n        "unworn_count": len(unworn),\n    }\n'''
if text.count(old_stats) != 1:
    raise SystemExit(f"health stats block: expected 1 match, found {text.count(old_stats)}")
text = text.replace(old_stats, new_stats, 1)

path.write_text(text, encoding="utf-8")
print("monetary/value cleanup applied")
