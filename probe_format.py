"""Debug probe: what do the local models actually reply to the agent protocol?"""
import subprocess

from openai import OpenAI

from workbench.agent import SYSTEM_PROMPT
from workbench.tools import TOOL_MANIFEST

client = OpenAI(api_key="sk-anything", base_url="http://localhost:4000", timeout=300)

TASK = ("Write a Python program sandbox/pressure_check.py that takes the pressure readings "
        "[4.2, 7.8, 9.1, 6.5, 10.3, 3.3], flags readings above the 8.5 bar threshold, prints "
        "SAFE/HIGH per reading and a summary count. Run it and fix errors until it works.")

msgs = [{"role": "system", "content": SYSTEM_PROMPT.format(tools=TOOL_MANIFEST)},
        {"role": "user", "content": TASK}]

for logical, ollama in [("coder", "qwen2.5-coder:7b"),
                        ("reasoning", "llama3.2"),
                        ("router", "qwen2.5:7b")]:
    try:
        r = client.chat.completions.create(model=logical, messages=msgs,
                                           temperature=0.15, max_tokens=3000)
        content = r.choices[0].message.content
    except Exception as e:
        content = f"<ERROR: {e}>"
    print("=" * 25 + f" {logical} " + "=" * 25, flush=True)
    print(repr(content[:900]) if content else "<empty>", flush=True)
    subprocess.run(["ollama", "stop", ollama], capture_output=True)
