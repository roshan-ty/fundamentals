import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("=== FINAL WORKSPACE VERIFICATION ===")

# 1. Directory structure
print("\n[1] Directory structure:")
print("  backend exists:", os.path.exists("backend"))
print("  scripts files:", sorted(os.listdir("scripts")))
print("  public/data files:", sorted(os.listdir("public/data")))

# 2. Output files valid & correctly keyed
print("\n[2] Pipeline outputs:")
files = {
    "calendar.json": "list",
    "news.json": "dict",
    "master_bias.json": "dict",
    "cftc_report.json": "dict",
    "ai_insights.json": "dict",
}
for f, kind in files.items():
    p = os.path.join("public/data", f)
    try:
        d = json.load(open(p, encoding="utf-8"))
        n = len(d) if kind == "list" else len(d)
        print(f"  {f}: OK ({n} entries, {os.path.getsize(p)} bytes)")
    except Exception as e:
        print(f"  {f}: FAIL {e}")

# 3. master_bias math spot checks
print("\n[3] master_bias.json math:")
mb = json.load(open("public/data/master_bias.json", encoding="utf-8"))
usd, eur = mb["base_scores"]["USD"], mb["base_scores"]["EUR"]
eurusd = next(p for p in mb["pairs"] if p["name"] == "EUR/USD")
calc = max(1.0, min(10.0, 5.0 + (eur-usd)))
print(f"  EUR/USD {eurusd['combined_bias']} vs calc {round(calc,2)} -> {'PASS' if abs(eurusd['combined_bias']-calc)<0.01 else 'FAIL'}")
xau = mb["assets"]["XAU"]["score"]
calc_xau = max(1.0, min(10.0, 11.0-usd))
print(f"  XAU {xau} vs calc 11-S_USD={round(calc_xau,2)} -> {'PASS' if abs(xau-calc_xau)<0.01 else 'FAIL'}")
usdjpy = next(p for p in mb["pairs"] if p["name"] == "USD/JPY")
calc_u = max(1.0, min(10.0, 5.0 + (usd - mb["base_scores"]["JPY"])))
print(f"  USD/JPY {usdjpy['combined_bias']} vs calc {round(calc_u,2)} -> {'PASS' if abs(usdjpy['combined_bias']-calc_u)<0.01 else 'FAIL'}")
print(f"  80 pairs: {'PASS' if mb['total_pairs']==80 else 'FAIL ' + str(mb['total_pairs'])}")
print(f"  event_breakdowns for 8 majors: {'PASS' if len(mb['event_breakdowns'])==8 else 'FAIL'}")

# 4. No stale references
import re
print("\n[4] Stale references:")
for root, dirs, files in os.walk("."):
    if ".venv" in root or "node_modules" in root or "dist" in root or ".git" in root:
        continue
    for fn in files:
        if fn.endswith((".py", ".tsx", ".ts", ".md", ".yml", ".json")):
            p = os.path.join(root, fn)
            try:
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            for bad in ["backend/fetch_pipeline", "backend/requirements", "test_differential_math", "verify_pipeline.py", "test_scorer"]:
                if bad in txt:
                    print(f"  {p} references {bad}")

print("\n=== VERIFICATION COMPLETE ===")