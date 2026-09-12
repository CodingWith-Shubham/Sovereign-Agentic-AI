"""LangGraph agent: router (auto model selection) + think->act->observe loop
with a live, user-visible thinking trace (Antigravity-style, fully offline)."""
import json
import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, END

from . import config
from .llm import chat, unload
from .tools import IMAGE_EXTENSIONS, TOOLS, TOOL_MANIFEST, resolve_path


class AgentState(TypedDict):
    task: str
    image: str
    task_type: str
    worker: str
    transcript: list      # assistant/user message pairs fed back to the worker
    blank_streak: int     # consecutive empty worker completions
    steps: int
    pending: dict         # parsed action awaiting tool execution
    history: list         # executed "action|args" keys, for loop detection
    files_read: list      # resolved paths the agent has read this session
    files_written: list   # resolved paths the agent created this session
    verified: bool        # a run_python/run_command has returned exit_code=0 since the last write
    post_success: int     # worker steps taken after verification without concluding
    final_answer: str
    done: bool


SYSTEM_PROMPT = """You are an autonomous agent inside a secure, fully offline refinery AI workbench.
You complete the user's task step-by-step by calling tools. Think out loud in the "thought" field.

AVAILABLE TOOLS:
{tools}

STRICT RESPONSE FORMAT - reply with exactly ONE JSON object and nothing else (no markdown fences, no extra words):
{{"thought": "your reasoning for this step, 1-3 sentences", "action": "<tool name>", "action_input": {{...}}}}

To finish the task, use:
{{"thought": "...", "action": "final_answer", "action_input": {{"answer": "<complete final answer for the user>"}}}}

EXAMPLE:
User task: Write and test a python add() function.
Your reply: {{"thought": "I will create the file first.", "action": "write_file", "action_input": {{"path": "sandbox/add.py", "content": "def add(a, b):\\n    return a + b\\n\\nprint(add(2, 3))"}}}}
After OBSERVATION says OK, your next reply: {{"thought": "Now I run it to verify it works.", "action": "run_command", "action_input": {{"command": "python sandbox/add.py"}}}}
After OBSERVATION shows exit_code=0 and output 5: {{"thought": "The code works.", "action": "final_answer", "action_input": {{"answer": "Created sandbox/add.py; tested it, output is 5."}}}}

RULES:
- For edit_file, NEVER use multi-line strings in the 'search' or 'replace' fields. If you need to change more than one line of code, DO NOT use edit_file. Instead, use write_file to rewrite the entire script with the corrected code.
- JSON rules: Never use raw line breaks or Python triple quotes (\"\"\") inside a JSON string. CRITICAL: JSON values must be literal strings or numbers only — NEVER Python expressions, f-strings (f"..."), list comprehensions ([x for x in ...]), or any code constructs. For create_excel rows, write out every row as a hardcoded array: [[\"Alice\", \"101\", \"10A\"], [\"Bob\", \"102\", \"10B\"]] — never [[f\"Name {{i}}\" for i in range(5)]].
- General Knowledge: If the user asks a simple question or asks for an explanation and you already know the answer, you do NOT need to call search_docs or list_files. Output the final_answer immediately.
- NEVER create a file (write_file, create_docx, create_pdf, create_excel, create_pptx) "to have something to show." Only create a file if the user's task explicitly asks for code, a script, or a report/document/presentation as the deliverable. A knowledge question is answered with final_answer text - nothing else.
- If search_docs returns NO_RELEVANT_DOCUMENTS_FOUND or an unrelated document, do NOT try to force it into an answer and do NOT compensate by writing unrelated code/files. Just answer from your own knowledge (clearly noting it is not grounded in plant documents) or say plainly that the ingested documents do not cover this.
- If you must use pip to install a package, always add the -q flag (e.g., python -m pip install -q package_name) to avoid spamming the OBSERVATION.
- One JSON object per reply. After a tool call you receive an OBSERVATION message; use it to pick the next step.
- If an OBSERVATION starts with FORMAT_ERROR, your last reply was invalid: reply again with ONE valid JSON object.
- Coding tasks: write the file, run it, read any error, fix the code, run again. Repeat until it works.
- NEVER claim you fixed a bug unless your immediately preceding successful action was edit_file or write_file. Reading a file does not change it.
- If you run code and see a SyntaxError or TypeError, you MUST use edit_file or write_file to apply a fix before running it again. Do not just read the file repeatedly.
- If edit_file fails because the search text does not match exactly, use read_file to copy the exact surrounding text, then retry with a more specific search. If that still fails, use write_file to rewrite the complete file with the corrected code.
- Static HTML/CSS tasks: do not run a foreground development server (such as `python -m http.server`, Vite, Flask, or Uvicorn); it never exits and blocks the agent. Inspect or validate the files directly, then finish.
- For small fixes to existing files, prefer edit_file(path, search, replace) over rewriting the whole file with write_file.
- CRITICAL: never claim code works unless you actually ran it with run_python or run_command and received an OBSERVATION containing 'exit_code=0'. Do NOT simulate, predict or invent command outputs - only real OBSERVATIONs count.
- File reading: for .pdf use read_pdf first, for .docx use read_docx, for .pptx use read_pptx, and for .xlsx/.xlsm use read_excel. If read_pdf reports no selectable text, use ocr_image on the PDF; do not call analyze_image on PDFs, DOCX files, PPTX files, or Excel files. Use analyze_image only for image files or visual questions that text extraction cannot answer. After a document reader returns useful content, answer from that observation instead of inspecting the same file again.
- Reports: build them with create_docx or create_pdf, presentations with create_pptx (all saved to outputs/), and tables/datasets with create_excel. For create_pptx, pass exactly one slide object per requested slide; the title is stored as presentation metadata. Code files go to sandbox/.
- Never invent file contents - read files with read_file. ALL paths (write_file, read_file, run_command) are relative to the project root: a file written as "sandbox/x.py" is run as "python sandbox/x.py".
- If the task involves plant procedures, limits, standards or equipment specs, call search_docs first to ground your answer in the ingested reference documents.
- Before editing an existing file, read_file it first so you understand and preserve its content.
- If an action fails the same way twice, STOP repeating it: inspect with read_file or list_files and rethink your approach.
- Work autonomously; only use final_answer when the task is truly done.
"""


def _escape_control_in_strings(text: str) -> str:
    """Small models often put raw newlines/tabs inside JSON strings, which is
    illegal JSON. Escape those control chars so json.loads accepts it."""
    out, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            if esc:
                out.append(ch); esc = False
            elif ch == "\\":
                out.append(ch); esc = True
            elif ch == '"':
                out.append(ch); in_str = False
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_str = True
    return "".join(out)


def _fix_backtick_strings(s: str) -> str:
    """Convert JS/Markdown backtick strings into valid JSON double-quoted
    strings, escaping inner quotes, backslashes and raw newlines. Small models
    frequently emit "content": `...multi-line code...` which is not JSON."""
    out, in_str, in_tick, esc = [], False, False, False
    for ch in s:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif in_tick:
            if ch == "`":
                out.append('"'); in_tick = False
            elif ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            if ch == '"':
                out.append(ch); in_str = True
            elif ch == "`":
                out.append('"'); in_tick = True  # replace opening backtick with a quote
            else:
                out.append(ch)
    return "".join(out)


def _fix_lone_backslashes(s: str) -> str:
    """Escape backslashes that are not part of a valid JSON escape sequence.
    Small models often emit Windows paths like sandbox\\app\\src\\index.ts,
    where \\a or \\s are invalid JSON escapes."""
    return re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', s)


_DOC_TOOLS = ("create_docx", "create_pdf", "create_pptx", "create_excel")


def _fix_json_brackets(s: str) -> str:
    """Balance { } and [ ] in a JSON string by scanning with a stack.

    qwen2.5 consistently produces create_pptx output where the slides array
    is never closed with ] — the model emits }}} (closing action_input and
    the outer object) directly after the last slide object, leaving one open
    [ bracket and one extra } on the stack.

    This scanner inserts a ] whenever a } is encountered while the top of
    the stack is an open [, and drops any extra } that appear when the stack
    is already empty.  Valid JSON is passed through unchanged.
    """
    stack = []
    result = list(s)
    i = 0
    in_str = False
    esc = False
    while i < len(result):
        c = result[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in ('{', '['):
                stack.append(c)
            elif c == '}':
                if stack and stack[-1] == '[':
                    # Array was not closed — insert the missing ] and reprocess
                    result.insert(i, ']')
                    stack.pop()
                    continue          # don't advance; reprocess this } next iteration
                elif stack and stack[-1] == '{':
                    stack.pop()
                elif not stack:
                    # Spurious extra } — discard it
                    result.pop(i)
                    continue
            elif c == ']':
                if stack and stack[-1] == '[':
                    stack.pop()
        i += 1
    # Append any remaining unclosed openers
    for opener in reversed(stack):
        result.append(']' if opener == '[' else '}')
    return ''.join(result)


def _repair_doc_action_json(text: str):
    """Fallback JSON repair for document-creation tool calls.

    Applies _fix_json_brackets then attempts to parse.  Only activates when
    the output contains one of the known document tool names.
    Returns a parsed dict or None.
    """
    if not any(t in text for t in _DOC_TOOLS):
        return None
    start = text.find('{')
    if start < 0:
        return None
    base = _escape_control_in_strings(_fix_backtick_strings(text[start:]))
    base = _fix_lone_backslashes(base)
    fixed = _fix_json_brackets(base)
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(fixed)
        if isinstance(obj, dict) and "action" in obj:
            return obj
    except Exception:
        pass
    return None



def parse_action(raw: str):
    """Lenient extractor: find the first decodable JSON object in the reply,
    tolerating markdown fences, chatter around it, unescaped newlines,
    lone backslashes, and the bracket-mismatch that qwen2.5 produces for
    document-creation tools (create_pptx / create_docx / etc.)."""
    text = raw.strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        base = _escape_control_in_strings(_fix_backtick_strings(text[i:]))
        for candidate in (text[i:], base, _fix_lone_backslashes(base)):
            try:
                obj, _ = decoder.raw_decode(candidate)
            except Exception:
                continue
            if isinstance(obj, dict) and "action" in obj:
                return obj
    # Fallback: targeted bracket repair for document-creation tools
    return _repair_doc_action_json(text)


def _code_changed(transcript: list) -> bool:
    return any(isinstance(m.get("content"), str)
               and m["content"].startswith(("OBSERVATION (write_file)",
                                            "OBSERVATION (edit_file)"))
               and ":\nOK" in m["content"]
               for m in transcript if m.get("role") == "user")


def _code_verified(transcript: list) -> bool:
    """True only if a run with exit_code=0 comes AFTER the last successful code change."""
    last_change, last_success = -1, -1
    for i, m in enumerate(transcript):
        if m.get("role") != "user" or not isinstance(m.get("content"), str):
            continue
        c = m["content"]
        if c.startswith(("OBSERVATION (write_file)", "OBSERVATION (edit_file)")) and ":\nOK" in c:
            last_change = i
        elif c.startswith("OBSERVATION (run_") and "exit_code=0" in c:
            last_success = i
    return last_success > last_change


def classify(state: AgentState) -> dict:
    hint = "\n(An image file is attached, so 'vision' is very likely.)" if state["image"] else ""
    prompt = (
        "Classify the task into exactly one category: coding, vision, or reasoning.\n"
        "- coding = writing, debugging, testing or explaining CODE (Python, JS, SQL scripts, etc.)\n"
        "- vision = understanding images, scanned documents, engineering drawings, photos, OCR\n"
        "- reasoning = everything else: summaries, analysis, Q&A, calculations, explanations,\n"
        "  AND any task that involves creating OR reading documents/reports/spreadsheets/presentations\n"
        "  (e.g. make a report, create a docx, build an Excel sheet, make a PowerPoint,\n"
        "   read a PDF/DOCX/XLSX/PPTX, write a Word document, generate a PDF report, etc.)\n"
        "Reply with ONLY the single category word.\n\n"
        "Task: Write a function to reverse a string\nAnswer: coding\n\n"
        "Task: Debug this Python script that crashes\nAnswer: coding\n\n"
        "Task: Read this scanned inspection report and draft an approval note\nAnswer: vision\n\n"
        "Task: Summarize this maintenance log\nAnswer: reasoning\n\n"
        "Task: Make a report docx on convolutional neural networks\nAnswer: reasoning\n\n"
        "Task: Create an Excel spreadsheet with sales data\nAnswer: reasoning\n\n"
        "Task: Build a PowerPoint presentation on machine learning\nAnswer: reasoning\n\n"
        "Task: Read the PDF and summarize it\nAnswer: reasoning\n\n"
        "Task: Write a Word document explaining transformer models\nAnswer: reasoning\n\n"
        f"Task: {state['task']}{hint}\nAnswer:"
    )
    raw = (chat(config.MODEL_ROUTER, [{"role": "user", "content": prompt}],
                temperature=0, max_tokens=8) or "").strip().lower()
    if "coding" in raw:
        task_type = "coding"
    elif "vision" in raw:
        task_type = "vision"
    else:
        task_type = "reasoning"
    # Override: document/report creation tasks always use the reasoning model regardless
    # of what the router said, because the coder model cannot produce large structured JSON.
    doc_keywords = (
        "docx", "xlsx", "pptx", ".doc", ".xls", ".ppt",
        "report", "word document", "pdf report", "excel sheet",
        "spreadsheet", "powerpoint", "presentation", "create a pdf",
        "make a pdf", "write a report", "build a report",
    )
    task_lower = state["task"].lower()
    if task_type == "coding" and any(kw in task_lower for kw in doc_keywords):
        task_type = "reasoning"
        raw += " [overridden->reasoning: document-creation task]"
    worker = (config.MODEL_CODER if task_type == "coding"
              else config.MODEL_REASONING)
    print(f"[ROUTER] classified as '{task_type}' -> worker model: {worker} "
          f"(router raw: '{raw}')", flush=True)
    # free VRAM before the worker loads (RTX 3050 6GB) - unless it IS the same weights
    if config.OLLAMA_NAMES.get(worker) != config.OLLAMA_NAMES.get(config.MODEL_ROUTER):
        unload(config.MODEL_ROUTER)
    return {"task_type": task_type, "worker": worker}



def agent_step(state: AgentState) -> dict:
    step = state["steps"] + 1

    # ORCHESTRATOR-OWNED TERMINATION: once execution has verified success, the
    # worker gets one explicit directive to conclude; if it still refuses after
    # two further steps, the run is closed deterministically.
    if state.get("verified"):
        if state.get("post_success", 0) >= 2:
            print(f"\n[STEP {step}] AUTO-FINISH: success was verified but the worker "
                  "kept going - concluding deterministically", flush=True)
            return {"steps": step, "done": True, "pending": {}, "post_success": 0,
                    "final_answer": ("Task completed and verified: the final execution "
                                     "returned exit_code=0. (Concluded by the orchestrator "
                                     "after the worker model kept inspecting instead of "
                                     "reporting completion.)")}

    messages = ([{"role": "system", "content": SYSTEM_PROMPT.format(tools=TOOL_MANIFEST)},
                 {"role": "user", "content": state["task"]}]
                + state["transcript"][-24:])
    if state.get("verified"):
        messages.append({"role": "user", "content":
            "Verification has ALREADY PASSED: the last run_command/run_python returned "
            "exit_code=0 and the task is complete. Reply ONLY with the final_answer action "
            "summarising what was done. Any other action is a mistake."})
    raw = chat(state["worker"], messages, temperature=0.15,
               max_tokens=config.AGENT_MAX_TOKENS,
               timeout=config.AGENT_TIMEOUT) or ""
    action = parse_action(raw)
    if action is None:
        blank = not raw.strip()
        blank_streak = state.get("blank_streak", 0) + 1 if blank else 0
        if blank and blank_streak >= 3:
            print(f"[STEP {step}] BLANK-OUT TERMINATE: model produced empty output "
                  f"{blank_streak} times in a row - closing run", flush=True)
            return {"steps": step, "done": True, "pending": {}, "blank_streak": 0,
                    "final_answer": ("TASK FAILED (orchestrator stop): the worker model "
                                     "stopped producing output. Try re-running the task, "
                                     "or switch to a larger model for this task type.")}
        snippet = raw.strip().replace("\n", " ")[:240]
        print(f"\n[STEP {step}] FORMAT_ERROR - reply was not valid JSON, retrying", flush=True)
        print(f"[STEP {step}] RAW MODEL OUTPUT (first 240 chars): {snippet}", flush=True)
        try:  # keep the full raw reply for offline debugging
            (config.SANDBOX_DIR / "debug_last_raw.txt").write_text(raw, encoding="utf-8")
        except Exception:
            pass
        obs = ('FORMAT_ERROR: your reply was not one valid JSON object. '
               'Re-issue the SAME action you intended, only with corrected JSON syntax: '
               'exactly one object {"thought": ..., "action": ..., "action_input": {...}}, '
               'strings in double quotes (never backticks), newlines inside strings as \\n.')
        new_transcript = state["transcript"] + ([{"role": "user", "content": obs}] if blank
            else [{"role": "assistant", "content": raw}, {"role": "user", "content": obs}])
        return {"steps": step, "pending": {},
            "blank_streak": blank_streak, "transcript": new_transcript}
    thought = str(action.get("thought", "")).strip()
    name = str(action.get("action", "")).strip()
    inp = action.get("action_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    print(f"\n[STEP {step}] THOUGHT: {thought}", flush=True)
    if name == "final_answer":
        unverified_code = (state["task_type"] == "coding"
                           and _code_changed(state["transcript"])
                           and not _code_verified(state["transcript"]))
        if unverified_code and state["steps"] >= config.MAX_AGENT_STEPS:
            print(f"[STEP {step}] GUARD: step limit reached with unverified code; "
                  "refusing final_answer", flush=True)
            return {"steps": step, "done": True, "pending": {}, "blank_streak": 0,
                    "final_answer": ("TASK FAILED (orchestrator stop): code was changed "
                                     "but never passed a successful verification run. "
                                     "The worker's final claim was rejected.")}
        if unverified_code:
            print(f"[STEP {step}] GUARD: final_answer rejected - latest code change has not "
                  "been re-verified with a successful run", flush=True)
            obs = ("SYSTEM: final_answer rejected. Your LAST code change was never re-tested: "
                   "run the verification command again (run_python or run_command) and only "
                   "finish after an OBSERVATION containing 'exit_code=0'. Run it now.")
            return {"steps": step, "pending": {},
                    "blank_streak": 0,
                    "transcript": state["transcript"] + [{"role": "assistant", "content": raw},
                                                         {"role": "user", "content": obs}]}
        print(f"[STEP {step}] ACTION: final_answer", flush=True)
        return {"steps": step, "done": True, "pending": {},
            "blank_streak": 0,
                "final_answer": str(inp.get("answer", "")).strip(),
                "transcript": state["transcript"] + [{"role": "assistant", "content": raw}]}
    short = json.dumps(inp, ensure_ascii=False)
    print(f"[STEP {step}] ACTION: {name}({short[:220]}{'...' if len(short) > 220 else ''})",
          flush=True)
    ret = {"steps": step, "pending": {"name": name, "input": inp},
            "blank_streak": 0,
           "transcript": state["transcript"] + [{"role": "assistant", "content": raw}]}
    if state.get("verified"):
        ret["post_success"] = state.get("post_success", 0) + 1
    return ret


def tool_exec(state: AgentState) -> dict:
    name = state["pending"]["name"]
    inp = state["pending"]["input"]
    key = name + "|" + json.dumps(inp, sort_keys=True, ensure_ascii=False, default=str)
    history = state.get("history", [])
    repeats = history.count(key)
    files_read = list(state.get("files_read", []))
    files_written = list(state.get("files_written", []))
    tool = TOOLS.get(name)

    # STUCK-LOOP BLOCK: 3 consecutive identical read/exec actions -> refuse and redirect.
    consec = 0
    for k in reversed(history):
        if k == key:
            consec += 1
        else:
            break
    if consec >= 2 and name in ("read_file", "list_files", "run_python", "run_command",
                                "analyze_image"):
        if consec >= 4:
            # worker ignored two consecutive blocks: parroting loop - stop deterministically
            print(f"[STEP {state['steps']}] STUCK-LOOP TERMINATE: worker ignored repeated "
                  "blocks - closing run", flush=True)
            return {"done": True, "pending": {}, "steps": state["steps"],
                    "final_answer": ("TASK FAILED (orchestrator stop): the worker model kept "
                                     f"repeating '{name}' with identical input despite "
                                     "receiving the information and explicit BLOCKED "
                                     "directives. No code was corrupted; files touched: "
                                     + (", ".join(files_read) if files_read else "none")
                                     + ". Re-run the task to retry.")}
        obs = ("BLOCKED: you repeated this exact action 3 times with no file change in "
               "between, so it is disabled now. You ALREADY have all the information it "
               "returns. Do NOT inspect again - apply the fix NOW with edit_file (small "
               "change) or write_file (full rewrite).")
        print(f"[STEP {state['steps']}] STUCK-LOOP BLOCK: {name} disabled for this repetition",
              flush=True)
        transcript = state["transcript"] + [{"role": "user",
                                             "content": f"OBSERVATION ({name}):\n{obs}"}]
        return {"transcript": transcript, "pending": {}, "history": history + [key],
                "files_read": files_read, "files_written": files_written,
                "verified": state.get("verified", False),
                "post_success": state.get("post_success", 0)}

    # POLICY GUARD: never overwrite an existing file the agent has not read this session.
    if name == "write_file":
        try:
            target = str(resolve_path(inp.get("path", "")))
        except Exception:
            target = ""
        if (target and Path(target).is_file()
                and target not in files_read and target not in files_written):
            obs = (f"POLICY BLOCK: '{inp.get('path')}' already exists and you have not read it. "
                   "First read_file it to see its current content, then retry write_file with "
                   "the FULL intended content, preserving everything that should stay.")
            print(f"[STEP {state['steps']}] GUARD: overwrite blocked - file not read yet", flush=True)
            transcript = state["transcript"] + [{"role": "user",
                                                 "content": f"OBSERVATION ({name}):\n{obs}"}]
            return {"transcript": transcript, "pending": {}, "history": history + [key],
                    "files_read": files_read, "files_written": files_written,
                    "verified": False, "post_success": 0}

    image_reader_tools = {"read_file", "read_pdf", "read_docx", "read_pptx", "read_excel"}
    image_path = str(inp.get("path", ""))
    if name in image_reader_tools and Path(image_path).suffix.lower() in IMAGE_EXTENSIONS:
        if history.count(key) == 0:
            requested_image_path = image_path
            resolved_image = resolve_path(image_path)
            if not resolved_image.is_file():
                sandbox_candidate = config.SANDBOX_DIR / Path(image_path).name
                if sandbox_candidate.is_file():
                    image_path = str(sandbox_candidate.relative_to(config.BASE_DIR))
            question = state["task"]
            try:
                obs = str(TOOLS["analyze_image"]["fn"]({
                    "path": image_path,
                    "question": question,
                }))
                path_note = (f" Resolved '{requested_image_path}' to '{image_path}'."
                             if image_path != requested_image_path else "")
                obs = (f"AUTO-CORRECTED: {name} was not valid for an image."
                       f"{path_note} "
                       f"analyze_image was executed instead.\n{obs}")
            except Exception as e:
                obs = f"ERROR: automatic analyze_image correction failed: {e}"
                print(f"[STEP {state['steps']}] OBSERVATION: {obs}", flush=True)
                return {
                    "done": True,
                    "pending": {},
                    "steps": state["steps"],
                    "transcript": state["transcript"] + [
                        {"role": "user", "content": f"OBSERVATION ({name}):\n{obs}"}
                    ],
                    "final_answer": (
                        "TASK FAILED: the local Ollama vision runner stopped while "
                        "analyzing the image. The agent stopped without retrying with "
                        "OCR or another model. Check Ollama server.log and GPU memory, "
                        "then retry the image analysis."
                    ),
                }
        else:
            obs = (f"BLOCKED: {name} cannot be used for image files "
                   f"({Path(image_path).suffix.lower()}). The image analysis was already "
                   "attempted. Do not repeat this action; use final_answer or choose "
                   "analyze_image with a specific question.")
    elif tool is None:
        obs = f"ERROR: unknown tool '{name}'. Available: {', '.join(sorted(TOOLS))}, final_answer"
    else:
        try:
            obs = str(tool["fn"](inp))
            try:
                resolved = str(resolve_path(inp.get("path", "")))
                if name == "read_file" and not obs.startswith("ERROR"):
                    files_read.append(resolved)
                elif name == "write_file" and obs.startswith("OK"):
                    files_written.append(resolved)
            except Exception:
                pass
        except TypeError as e:
            obs = f"ERROR: bad arguments for {name}: {e}. Correct signature: {tool['sig']}"
        except Exception as e:
            obs = f"ERROR: tool {name} failed: {e}"
    obs = obs[:4000]
    if name in ("run_python", "run_command") and obs.startswith("exit_code=0"):
        obs += ("\nSYSTEM: the command succeeded (exit_code=0). If the task goal is met, "
                "reply with final_answer now - do not keep polishing working code.")
    if repeats >= 1:
        obs += ("\nSYSTEM WARNING: you already ran this exact action before and it did not "
                "solve the problem. Repeating it changes nothing. Inspect with read_file "
                "or list_files, then try a DIFFERENT approach.")
        print(f"[STEP {state['steps']}] LOOP DETECTED: same action repeated - warning injected",
              flush=True)
    print(f"[STEP {state['steps']}] OBSERVATION: {obs[:600]}"
          f"{' ...[truncated]' if len(obs) > 600 else ''}", flush=True)
    transcript = state["transcript"] + [{"role": "user", "content": f"OBSERVATION ({name}):\n{obs}"}]
    if state["steps"] >= config.MAX_AGENT_STEPS:
        transcript.append({"role": "user",
                           "content": "SYSTEM: step budget exhausted. Reply with final_answer NOW."})
    if name in ("write_file", "edit_file"):
        history = []  # file content changed: re-running earlier commands is meaningful again
    verified = state.get("verified", False)
    if name in ("run_python", "run_command"):
        verified = obs.startswith("exit_code=0")  # proof of success / failure resets it
    elif name in ("write_file", "edit_file"):
        verified = False  # code changed: previous verification no longer applies
    return {"transcript": transcript, "pending": {}, "history": history + [key],
            "files_read": files_read, "files_written": files_written,
            "verified": verified, "post_success": state.get("post_success", 0) if verified else 0}


def after_step(state: AgentState) -> str:
    if state.get("done"):
        return "end"
    if state.get("pending"):
        return "tool"
    if state["steps"] > config.MAX_AGENT_STEPS + 3:  # hard stop on repeated format errors
        return "end"
    return "again"


graph = StateGraph(AgentState)
graph.add_node("classify", classify)
graph.add_node("agent_step", agent_step)
graph.add_node("tool_exec", tool_exec)
graph.set_entry_point("classify")
graph.add_edge("classify", "agent_step")
graph.add_conditional_edges("agent_step", after_step,
                            {"end": END, "tool": "tool_exec", "again": "agent_step"})
graph.add_edge("tool_exec", "agent_step")
app = graph.compile()
