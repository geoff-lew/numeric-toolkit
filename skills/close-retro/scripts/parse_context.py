"""
Parse Numeric workspace context into lightweight lookups.

Input: path to the raw MCP tool-result file (JSON array [{type, text}])
Output: prints summary, saves to output_dir:
  - user_map.json: {user_id: {name, active}}
  - periods.json: [{id, slug, status, start, end, frequency_key}]

Usage: python3 parse_context.py <input_file> <output_dir>
"""
import json, sys, os


def parse(input_file, output_dir):
    with open(input_file) as f:
        raw = json.load(f)
    ctx = json.loads(raw[0]["text"])

    user_map = {}
    for u in ctx.get("users", []):
        user_map[u["id"]] = {
            "name": u.get("name", u["id"]),
            "active": u.get("active", True),
        }

    periods = []
    for p in ctx.get("periods", []):
        s, e = p.get("start", {}), p.get("end", {})
        periods.append({
            "id": p["id"],
            "slug": p.get("slug", ""),
            "status": p.get("status", ""),
            "start": f"{s.get('year','')}-{s.get('month',1):02d}-{s.get('day',1):02d}",
            "end": f"{e.get('year','')}-{e.get('month',1):02d}-{e.get('day',1):02d}",
            "frequency_key": p.get("frequency_key", ""),
        })
    periods.sort(key=lambda x: x["start"])

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "user_map.json"), "w") as f:
        json.dump(user_map, f, indent=2)
    with open(os.path.join(output_dir, "periods.json"), "w") as f:
        json.dump(periods, f, indent=2)

    print(f"Parsed {len(user_map)} users, {len(periods)} periods")
    closed = [p for p in periods if p["status"] == "closed"]
    open_p = [p for p in periods if p["status"] == "open"]
    print(f"  Closed: {len(closed)}, Open: {len(open_p)}")
    if closed:
        print(f"  Last closed: {closed[-1]['slug']} ({closed[-1]['id']})")
    if open_p:
        print(f"  Current open: {open_p[0]['slug']} ({open_p[0]['id']})")
    return user_map, periods


if __name__ == "__main__":
    parse(sys.argv[1], sys.argv[2])
