#!/usr/bin/env python3
"""Turn `claude -p --output-format stream-json` NDJSON into live, colored
diffs — one JSON event per line, printed and flushed as it arrives so
scripts/ralph/ralph.sh no longer sits silent until the whole run finishes.

Usage: claude ... --output-format stream-json | python3 -u ralph_format_stream.py
"""

import difflib
import json
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"


def read_before(file_path):
    try:
        with open(file_path, "r") as f:
            return f.read()
    except OSError:
        return ""


def print_diff(file_path, old, new):
    adds = dels = 0
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2))
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("@@"):
            print(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            adds += 1
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            dels += 1
            print(f"{RED}{line}{RESET}")
        else:
            print(f"{DIM}{line}{RESET}")
    print(f"  {GREEN}+{adds}{RESET} {RED}-{dels}{RESET}")


def handle_tool_use(block):
    name = block.get("name", "")
    tool_input = block.get("input", {}) or {}
    file_path = tool_input.get("file_path", "")

    if name == "Edit":
        print(f"{BOLD}{CYAN}✎ Edit {file_path}{RESET}")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        print_diff(file_path, old, new)

    elif name == "MultiEdit":
        edits = tool_input.get("edits", []) or []
        print(f"{BOLD}{CYAN}✎ Edit {file_path} ({len(edits)} edits){RESET}")
        for i, edit in enumerate(edits, 1):
            print(f"{DIM}  -- edit {i}/{len(edits)} --{RESET}")
            print_diff(file_path, edit.get("old_string", ""), edit.get("new_string", ""))

    elif name == "Write":
        before = read_before(file_path)
        after = tool_input.get("content", "")
        label = "Create" if not before else "Overwrite"
        print(f"{BOLD}{CYAN}✎ {label} {file_path}{RESET}")
        print_diff(file_path, before, after)

    elif name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        suffix = f"  {DIM}({desc}){RESET}" if desc else ""
        print(f"{YELLOW}$ {cmd}{RESET}{suffix}")

    else:
        summary = json.dumps(tool_input)[:120]
        print(f"{DIM}→ {name} {summary}{RESET}")


def handle_event(event):
    etype = event.get("type")

    if etype == "system" and event.get("subtype") == "init":
        model = event.get("model", "?")
        print(f"{DIM}── session started (model: {model}) ──{RESET}")

    elif etype == "assistant":
        for block in event.get("message", {}).get("content", []) or []:
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "")
                if text.strip():
                    print(text)
            elif btype == "tool_use":
                handle_tool_use(block)

    elif etype == "user":
        for block in event.get("message", {}).get("content", []) or []:
            if block.get("type") == "tool_result" and block.get("is_error"):
                content = block.get("content", "")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                print(f"{RED}✗ tool error: {str(content)[:300]}{RESET}")

    elif etype == "result":
        duration = event.get("duration_ms", 0) / 1000
        cost = event.get("total_cost_usd", 0)
        print(f"{DIM}── done in {duration:.1f}s, cost ${cost:.4f} ──{RESET}")
        result_text = event.get("result", "")
        if result_text:
            print(result_text)


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            handle_event(event)
        except Exception as exc:  # noqa: BLE001 - never let a formatting bug kill the loop
            print(f"{RED}(formatter error: {exc}){RESET}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
