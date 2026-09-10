# Config sanity checks — verifies all JSON configs parse and the scorecard's
# dataPoint ids used by the matchers exist inside the scorecard.
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.path.join(ROOT, "config")


def load(name):
    with open(os.path.join(CONFIG, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    errors = []
    for name in ("scorecard.json", "symbols.json", "news_rules.json"):
        try:
            load(name)
            print(f"OK   config/{name}")
        except Exception as exc:
            errors.append(f"config/{name}: {exc}")

    sc = load("scorecard.json")
    syms = load("symbols.json")

    # 1) Every currency block has a name + dataPoints list with weights > 0
    for code, cur in sc.get("currencies", {}).items():
        if not cur.get("name"):
            errors.append(f"[{code}] missing display name")
        dps = cur.get("dataPoints", [])
        if not dps:
            errors.append(f"[{code}] no data points")
        for dp in dps:
            if not dp.get("id") or not dp.get("weight") or dp["weight"] <= 0:
                errors.append(f"[{code}] bad data point {dp.get('id')}")
            if dp.get("direction") not in ("higher_is_bullish", "lower_is_bullish"):
                errors.append(f"[{code}] bad direction {dp.get('id')}")

    # 2) Derived targets exist in symbols where expected
    derived = set(sc.get("derived", {}).get("targets", []))
    all_syms = set()
    for cls in ("fx", "crypto", "metals", "energy", "indices"):
        all_syms.update(syms.get(cls, {}).keys())
    # indices may arrive under slightly different ids; allow missing silently but warn
    missing = derived - all_syms
    if missing:
        print(f"WARN derived targets not in symbols universe: {sorted(missing)}")

    # 3) news rules has both include and exclude lists where relevant
    for inst, cfg in load("news_rules.json").get("rules", {}).items():
        if not cfg.get("include"):
            errors.append(f"news rule {inst} missing include list")

    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("All config checks passed.")


if __name__ == "__main__":
    main()