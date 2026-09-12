"""Quick sanity checks for the lenient action parser."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workbench.agent import parse_action

# 1. backtick-wrapped multi-line content (observed failure with qwen2.5-coder)
raw1 = '{"thought": "fix the typo", "action": "write_file", "action_input": {"path": "sandbox/app/src/index.ts", "content": `interface A {\n    x: number;\n}\nconsole.log("hi");`}}'
obj = parse_action(raw1)
assert obj and obj["action"] == "write_file", "backtick payload failed"
assert 'console.log("hi");' in obj["action_input"]["content"], "inner quotes lost"
print("PASS 1: backtick strings ->", repr(obj["action_input"]["content"][:40]))

# 2. Windows path with lone backslashes
raw2 = '{"thought": "read", "action": "read_file", "action_input": {"path": "sandbox\\app\\src\\index.ts"}}'
obj = parse_action(raw2)
assert obj and obj["action_input"]["path"] == "sandbox\\app\\src\\index.ts", "backslash path failed"
print("PASS 2: lone backslashes ->", obj["action_input"]["path"])

# 3. raw newlines inside a normal string
raw3 = '{"thought": "write", "action": "write_file", "action_input": {"path": "sandbox/x.py", "content": "a = 1\nprint(a)"}}'
obj = parse_action(raw3)
assert obj and "a = 1\nprint(a)" in obj["action_input"]["content"], "raw newline failed"
print("PASS 3: raw newlines in strings")

# 4. markdown fence + chatter around the JSON
raw4 = 'Sure! Here is the action:\n```json\n{"thought": "go", "action": "list_files", "action_input": {}}\n```\nHope that helps.'
obj = parse_action(raw4)
assert obj and obj["action"] == "list_files", "fenced payload failed"
print("PASS 4: markdown fences + chatter")

print("ALL PARSER TESTS PASSED")
