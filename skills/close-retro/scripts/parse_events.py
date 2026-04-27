"""
Parse one or more Numeric get_task_events result files into a merged event list.

Input: one or more paths to raw MCP tool-result files (JSON array [{type, text}])
       plus a user_map.json path for ID->name resolution
Output: saves to output_dir/events.json (flat array of events with user names resolved)

Usage: python3 parse_events.py <user_map.json> <output_dir> <event_file1> [event_file2] ...
"""
import json, sys, os


def parse(user_map_path, output_dir, event_files):
    with open(user_map_path) as f:
        user_map = json.load(f)

    def resolve(uid):
        if uid and uid in user_map:
            return user_map[uid].get("name", uid)
        return uid or "unknown"

    all_events = []
    for ef in event_files:
        with open(ef) as f:
            raw = json.load(f)
        text = raw[0]["text"]
        events = json.loads(text) if isinstance(text, str) else text
        if isinstance(events, list):
            all_events.extend(events)

    # Resolve user names and simplify
    cleaned = []
    for e in all_events:
        cleaned.append({
            "id": e.get("id"),
            "task_id": e.get("task_id"),
            "action_key": e.get("action_key"),
            "event": e.get("event"),
            "occurred_at": e.get("occurred_at"),
            "by_user_id": e.get("by_user"),
            "by_user": resolve(e.get("by_user")),
            "role_id": e.get("role_id"),
            "status_from": e.get("status_changed_from"),
            "status_to": e.get("status_changed_to"),
            "outputs": e.get("outputs", {}),
        })

    cleaned.sort(key=lambda x: x.get("occurred_at", ""))

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "events.json"), "w") as f:
        json.dump(cleaned, f, indent=2)

    # Summary
    by_action = {}
    for e in cleaned:
        ak = e["action_key"]
        by_action[ak] = by_action.get(ak, 0) + 1

    print(f"Parsed {len(cleaned)} events from {len(event_files)} files")
    print(f"  By action: {json.dumps(by_action)}")
    return cleaned


if __name__ == "__main__":
    parse(sys.argv[1], sys.argv[2], sys.argv[3:])
