import csv
from collections import defaultdict
from pathlib import Path

base = Path(__file__).parent

rows = list(csv.DictReader(open(base / "amount-2026-5.csv", encoding="utf-8")))

by_model = defaultdict(
    lambda: {"requests": 0, "cache_hit": 0, "cache_miss": 0, "output": 0}
)

for r in rows:
    m = r["model"]
    t = r["type"]
    amt = int(r["amount"]) if r["amount"] else 0
    if t == "request_count":
        by_model[m]["requests"] += amt
    elif t == "input_cache_hit_tokens":
        by_model[m]["cache_hit"] += amt
    elif t == "input_cache_miss_tokens":
        by_model[m]["cache_miss"] += amt
    elif t == "output_tokens":
        by_model[m]["output"] += amt

cost_rows = list(csv.DictReader(open(base / "cost-2026-5.csv", encoding="utf-8")))
cost_by_model = defaultdict(float)
for r in cost_rows:
    cost_by_model[r["model"]] += float(r["cost"])

print("=== AGGREGATE BY MODEL ===")
for m in sorted(by_model.keys()):
    d = by_model[m]
    req = d["requests"]
    total_in = d["cache_hit"] + d["cache_miss"]
    print(f"\n{m}:")
    print(f"  API requests: {req:,}")
    print(f"  Input cache hit tokens: {d['cache_hit']:,}")
    print(f"  Input cache miss tokens: {d['cache_miss']:,}")
    print(f"  Total input tokens: {total_in:,}")
    print(f"  Output tokens: {d['output']:,}")
    print(f"  Total tokens (in+out): {total_in + d['output']:,}")
    if req:
        print(f"  Avg input/request: {total_in / req:,.1f}")
        print(f"  Avg cache miss/request: {d['cache_miss'] / req:,.1f}")
        print(f"  Avg cache hit/request: {d['cache_hit'] / req:,.1f}")
        print(f"  Avg output/request: {d['output'] / req:,.1f}")
        print(f"  Avg total tokens/request: {(total_in + d['output']) / req:,.1f}")
    print(f"  Total cost (USD): ${cost_by_model[m]:.6f}")

flash = by_model["deepseek-v4-flash"]
req_f = flash["requests"]
total_in_f = flash["cache_hit"] + flash["cache_miss"]
cost_f = cost_by_model["deepseek-v4-flash"]

print("\n=== FLASH SUMMARY (primary production model) ===")
print(f"Total API requests: {req_f:,}")
print(f"Avg cost per API request: ${cost_f / req_f:.6f}")
print(f"Avg output tokens per request: {flash['output'] / req_f:.1f}")
print(f"Avg cache miss input per request: {flash['cache_miss'] / req_f:.1f}")
print(f"Cache hit ratio (input): {flash['cache_hit'] / total_in_f * 100:.1f}%")

for calls_per_msg in [1.0, 1.5, 2.0, 2.5]:
    est_messages = req_f / calls_per_msg
    cost_per_msg = cost_f / est_messages
    tokens_per_msg = (total_in_f + flash["output"]) / est_messages
    out_per_msg = flash["output"] / est_messages
    in_miss_per_msg = flash["cache_miss"] / est_messages
    print(f"\nIf ~{calls_per_msg} API calls per user message:")
    print(f"  Est. user messages: {est_messages:,.0f}")
    print(f"  Cost per user message: ${cost_per_msg:.6f}")
    print(f"  Output tokens per user message: {out_per_msg:.1f}")
    print(f"  Cache-miss input per user message: {in_miss_per_msg:.1f}")
    print(f"  Total billable tokens per user message: {tokens_per_msg:.1f}")

print("\n=== DAILY FLASH BREAKDOWN ===")
daily = defaultdict(
    lambda: {"requests": 0, "cache_hit": 0, "cache_miss": 0, "output": 0, "cost": 0}
)
for r in rows:
    if r["model"] != "deepseek-v4-flash":
        continue
    d = r["utc_date"]
    t = r["type"]
    amt = int(r["amount"]) if r["amount"] else 0
    if t == "request_count":
        daily[d]["requests"] += amt
    elif t == "input_cache_hit_tokens":
        daily[d]["cache_hit"] += amt
    elif t == "input_cache_miss_tokens":
        daily[d]["cache_miss"] += amt
    elif t == "output_tokens":
        daily[d]["output"] += amt
for r in cost_rows:
    if r["model"] == "deepseek-v4-flash":
        daily[r["utc_date"]]["cost"] += float(r["cost"])

for d in sorted(daily.keys()):
    x = daily[d]
    req = x["requests"]
    if req == 0:
        continue
    tin = x["cache_hit"] + x["cache_miss"]
    cpr = x["cost"] / req
    print(
        f"{d}: {req:4d} req | avg in {tin / req:6.0f} | avg out {x['output'] / req:5.1f} | "
        f"cost ${x['cost']:.4f} | ${cpr:.5f}/req"
    )

pro = by_model.get("deepseek-v4-pro", {})
if pro.get("requests"):
    req_p = pro["requests"]
    total_in_p = pro["cache_hit"] + pro["cache_miss"]
    cost_p = cost_by_model["deepseek-v4-pro"]
    print("\n=== PRO vs FLASH (measured) ===")
    print(f"Pro requests: {req_p}, cost: ${cost_p:.4f}, ${cost_p / req_p:.6f}/req")
    print(f"Flash requests: {req_f}, cost: ${cost_f:.4f}, ${cost_f / req_f:.6f}/req")
    print(f"Pro avg output/request: {pro['output'] / req_p:.1f}")
    print(f"Pro avg input/request: {total_in_p / req_p:.1f}")
    print(f"Cost ratio pro/flash per request: {(cost_p / req_p) / (cost_f / req_f):.2f}x")

avg_cost_req = cost_f / req_f
avg_out = flash["output"] / req_f
avg_in_miss = flash["cache_miss"] / req_f
avg_in_hit = flash["cache_hit"] / req_f
avg_in = avg_in_miss + avg_in_hit

prices = {
    "deepseek-v4-pro": {"in_hit": 0.003625, "in_miss": 0.435, "out": 0.87},
    "gpt-4o-mini": {"in_hit": 0.075, "in_miss": 0.15, "out": 0.60},
    "gpt-4o": {"in_hit": 1.25, "in_miss": 2.50, "out": 10.00},
}

print("\n=== PROJECTED COST PER API REQUEST (same token profile as measured Flash) ===")
print(
    f"Measured avg tokens/request: {avg_in:.0f} in "
    f"({avg_in_hit:.0f} hit + {avg_in_miss:.0f} miss), {avg_out:.0f} out"
)
print(f"Measured DeepSeek Flash: ${avg_cost_req:.6f}")
for name, p in prices.items():
    proj = (
        (avg_in_hit / 1e6) * p["in_hit"]
        + (avg_in_miss / 1e6) * p["in_miss"]
        + (avg_out / 1e6) * p["out"]
    )
    print(f"Projected {name}: ${proj:.6f} ({proj / avg_cost_req:.1f}x Flash)")

total_cost = sum(cost_by_model.values())
total_req = sum(d["requests"] for d in by_model.values())
active_days = len([d for d in daily if daily[d]["requests"] > 0])
print(f"\n=== MONTH TOTAL (May 2026) ===")
print(f"Total cost: ${total_cost:.4f}")
print(f"Total API requests (all models): {total_req:,}")
print(f"Flash-only requests: {req_f:,}")
print(f"Pro-only requests: {pro.get('requests', 0):,}")
print(f"Active days with Flash usage: {active_days}")

# User-message level metrics (architecture: ~1.7 API calls per user message)
calls_per_msg = 1.7
user_msgs = req_f / calls_per_msg
cost_per_msg = cost_f / user_msgs
total_tok_per_msg = (total_in_f + flash["output"]) / user_msgs
out_per_msg = flash["output"] / user_msgs
in_miss_per_msg = flash["cache_miss"] / user_msgs
in_hit_per_msg = flash["cache_hit"] / user_msgs

print("\n=== USER MESSAGE METRICS (1.7 API calls per message, architecture-based) ===")
print(f"Estimated user messages in May 2026: {user_msgs:.0f}")
print(f"Billable input tokens per user message: {in_miss_per_msg + in_hit_per_msg:.0f}")
print(f"  - cache miss: {in_miss_per_msg:.0f}")
print(f"  - cache hit: {in_hit_per_msg:.0f}")
print(f"Billable output tokens per user message: {out_per_msg:.1f}")
print(f"Total billable tokens per user message: {total_tok_per_msg:.1f}")
print(f"Measured cost per user message (Flash): ${cost_per_msg:.6f}")
print(f"Measured cost per 1,000 user messages (Flash): ${cost_per_msg * 1000:.2f}")

models = [
    ("DeepSeek V4 Flash", 0.0028, 0.14, 0.28),
    ("DeepSeek V4 Pro", 0.003625, 0.435, 0.87),
    ("OpenAI GPT-4o mini", 0.075, 0.15, 0.60),
    ("OpenAI GPT-4o", 1.25, 2.50, 10.00),
]
print("\n=== MODEL COST COMPARISON (measured token volume per user message) ===")
for name, ph, pm, po in models:
    c = in_hit_per_msg / 1e6 * ph + in_miss_per_msg / 1e6 * pm + out_per_msg / 1e6 * po
    print(f"{name}: ${c:.6f}/message (${c * 1000:.2f} per 1,000 messages)")

print("\n=== MONTHLY PROJECTIONS (Flash, measured rate) ===")
for vol in [1000, 10000, 50000, 100000]:
    print(f"  {vol:,} user messages/month: ${cost_per_msg * vol:.2f}")
