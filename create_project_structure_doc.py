from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "outputs" / "MRPL_Agentic_Workbench_Project_Structure.docx"


def add_bullet(document, text, level=0):
    style = "List Bullet" if level == 0 else "List Bullet 2"
    document.add_paragraph(text, style=style)


def add_number(document, text):
    document.add_paragraph(text, style="List Number")


def build_document():
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    normal = document.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)

    title = document.add_heading("MRPL Agentic AI Workbench", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = document.add_paragraph("Project structure, architecture, runtime flow, and operating guide")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata = document.add_paragraph(
        f"Generated {date.today():%d %B %Y} | Local/offline engineering assistant"
    )
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER

    document.add_heading("1. Purpose and Scope", 1)
    document.add_paragraph(
        "This project is a local agentic AI workbench intended for refinery and engineering "
        "tasks. It combines local Ollama models, a LiteLLM compatibility proxy, LangGraph "
        "orchestration, local OCR and vision analysis, document retrieval, sandboxed code "
        "execution, and Word report generation. The primary design goal is to keep task data "
        "and model inference on the local machine."
    )
    document.add_paragraph(
        "The current implementation has evolved from a simple model router into a tool-using "
        "agent. The main implementation is under workbench/. The root-level scripts are "
        "mostly diagnostics, experiments, or older workflows."
    )

    document.add_heading("2. Directory Structure", 1)
    structure = [
        ("run_agent.py", "Main command-line entry point for the current agent."),
        ("litellm_config.yaml", "Maps logical model names to local Ollama models."),
        ("agent_router.py", "Older, simpler classify-then-answer LangGraph prototype."),
        ("workbench/agent.py", "Current LangGraph agent, action protocol, loop, and guards."),
        ("workbench/config.py", "Central paths, model names, timeouts, and step limits."),
        ("workbench/llm.py", "OpenAI-compatible client connected to the local LiteLLM proxy."),
        ("workbench/tools.py", "File, execution, OCR, vision, document, and search tools."),
        ("workbench/rag.py", "Embedding, chunking, storage, and semantic retrieval logic."),
        ("workbench/data/vectorstore.json", "JSON vector store containing ingested document chunks."),
        ("sandbox/", "Agent working area for code, test files, and reference documents."),
        ("outputs/", "Generated Word documents and other user-facing deliverables."),
        ("test_*.py and probe_format.py", "Layer-specific connectivity, OCR, vision, and protocol checks."),
        ("combine_context.py and generate_approval_note.py", "Earlier OCR/vision/reporting workflow."),
    ]
    for path, description in structure:
        add_bullet(document, f"{path}: {description}")

    document.add_heading("3. Main Runtime Architecture", 1)
    document.add_paragraph(
        "The current runtime is a stateful think-act-observe loop implemented as a LangGraph "
        "state machine. A task enters through run_agent.py, is classified by a router model, "
        "and is then handled by a worker model that selects tools using a strict JSON action "
        "protocol. Tool results are returned to the worker as observations until it produces "
        "a final answer or the orchestrator stops the run."
    )
    for item in [
        "run_agent.py creates the initial AgentState and invokes the compiled graph.",
        "classify selects coding, vision, or reasoning and chooses a worker model.",
        "agent_step sends the task, tool manifest, and transcript to the worker.",
        "tool_exec validates and executes the selected local tool.",
        "The observation is appended to the transcript and the worker receives another step.",
        "final_answer ends the graph and is printed by run_agent.py.",
    ]:
        add_number(document, item)

    document.add_heading("4. Agent State and Control Flow", 1)
    document.add_paragraph(
        "AgentState is the shared state passed between graph nodes. It includes the original "
        "task, optional image path, classification, selected worker, transcript, step count, "
        "pending action, action history, files read and written, verification state, and the "
        "final answer."
    )
    for item in [
        "classify -> agent_step",
        "agent_step -> tool_exec when a tool action is requested",
        "tool_exec -> agent_step after an observation",
        "agent_step -> END when final_answer is accepted",
        "agent_step -> END when a hard stop or deterministic failure condition is reached",
    ]:
        add_bullet(document, item)
    document.add_paragraph(
        "The normal step budget is MAX_AGENT_STEPS = 10. The orchestrator also protects the "
        "run from repeated reads or executions, malformed JSON, unverified code changes, and "
        "workers that continue acting after successful verification."
    )

    document.add_heading("5. Worker Action Protocol", 1)
    document.add_paragraph("The worker must return exactly one JSON object per step:")
    document.add_paragraph(
        '{"thought": "I will inspect the file first.", "action": "read_file", '
        '"action_input": {"path": "sandbox/app/src/index.ts"}}'
    )
    document.add_paragraph("To finish, it returns:")
    document.add_paragraph(
        '{"thought": "The change was tested successfully.", "action": "final_answer", '
        '"action_input": {"answer": "Fixed and verified the program."}}'
    )
    document.add_paragraph(
        "parse_action() is deliberately tolerant because small local models may return JSON "
        "inside Markdown fences, use raw newlines in strings, use backticks for multiline code, "
        "or emit Windows paths with unescaped backslashes. Invalid responses are saved to "
        "sandbox/debug_last_raw.txt and the worker is asked to retry."
    )

    document.add_heading("6. Model and Proxy Layer", 1)
    document.add_paragraph(
        "The model path is OpenAI client -> LiteLLM on localhost:4000 -> Ollama on localhost:11434. "
        "The API key is the placeholder sk-anything and is used only to satisfy the local OpenAI client."
    )
    for item in [
        "router -> qwen2.5:7b for task classification",
        "reasoning -> llama3.2 for general reasoning and reports",
        "coder -> qwen2.5-coder:3b-instruct for lightweight coding",
        "coder-pro -> qwen2.5:7b for the current coding worker",
        "vision -> granite3.2-vision:latest for image analysis",
        "vision-pro -> minicpm-v:latest for heavier visual reasoning",
        "embeddings -> nomic-embed-text for document retrieval",
    ]:
        add_bullet(document, item)
    document.add_paragraph(
        "The router model is unloaded before a different worker is loaded when possible. "
        "run_agent.py unloads the configured models at the end to reduce GPU memory pressure."
    )

    document.add_heading("7. Tool Layer", 1)
    tools = [
        ("list_files", "Lists files and folders within the project root."),
        ("read_file", "Reads a text file, returning at most 6000 characters."),
        ("write_file", "Creates or overwrites a text file after path and policy checks."),
        ("edit_file", "Replaces exactly one matching occurrence for small changes."),
        ("run_python", "Runs generated Python in sandbox/_agent_run.py with a timeout."),
        ("run_command", "Runs a shell command from the project root with a timeout."),
        ("ocr_image", "Extracts text locally through PaddleOCR."),
        ("analyze_image", "Sends a local image to the configured vision model."),
        ("create_docx", "Creates a Word deliverable in outputs/."),
        ("search_docs", "Retrieves relevant chunks from the local vector store."),
    ]
    for name, description in tools:
        add_bullet(document, f"{name}: {description}")
    document.add_paragraph(
        "All file paths pass through resolve_path(), which confines operations to the project "
        "directory. The agent also blocks overwriting an existing file unless it has read that "
        "file during the current session."
    )

    document.add_heading("8. Verification and Safety Guards", 1)
    for item in [
        "A successful run_python or run_command must return exit_code=0 before coding work is considered verified.",
        "Any write_file or edit_file action resets verification because the code may have changed.",
        "final_answer is rejected after an unverified coding change while steps remain.",
        "Repeated identical read or execution actions are blocked to prevent model loops.",
        "A worker that continues after successful verification is eventually auto-finished.",
        "Tool output is truncated before it is placed into the model transcript to limit context growth.",
    ]:
        add_bullet(document, item)

    document.add_heading("9. RAG Document Retrieval", 1)
    document.add_paragraph(
        "workbench/rag.py provides local retrieval-augmented generation without an external vector database. "
        "Documents are split into 600-character chunks with 120-character overlap. Each chunk is embedded "
        "with nomic-embed-text and stored in workbench/data/vectorstore.json along with its source path."
    )
    for item in [
        "Ingest: python -m workbench.rag ingest sandbox/SOP-26117_Pervaporation_Rig.txt",
        "Search: python -m workbench.rag search \"maximum feed pressure\"",
        "Agent access: search_docs(query)",
        "Ranking: cosine similarity computed with NumPy.",
    ]:
        add_bullet(document, item)
    document.add_paragraph(
        "The supplied SOP covers pressure, temperature, vacuum, startup, sampling, shutdown, "
        "emergency actions, and engineer sign-off limits. Safety or plant-procedure questions "
        "should be grounded with search_docs before an answer is drafted."
    )

    document.add_heading("10. Vision, OCR, and Reports", 1)
    document.add_paragraph(
        "OCR uses PaddleOCR locally to extract labels from scanned documents or images. "
        "analyze_image() base64-encodes an image and sends it to the local vision model with a "
        "specific question. Vision tasks are classified separately and assigned the vision "
        "worker, avoiding an unnecessary reasoning-model load."
    )
    document.add_paragraph(
        "create_docx() creates a Word document in outputs/ and supports plain paragraphs, headings "
        "using # or ##, and bullet lines beginning with - or *. The generated document includes a "
        "human engineer sign-off notice."
    )
    document.add_paragraph(
        "The older combine_context.py and generate_approval_note.py scripts form a separate workflow: "
        "OCR a diagram, ask the vision model for a grounded interpretation, save combined_context.txt, "
        "then ask the reasoning model to produce findings, observations, and a recommendation."
    )

    document.add_heading("11. Sandbox and Example Files", 1)
    for item in [
        "sandbox/pressure_check.py is a small Python pressure classification example.",
        "sandbox/app/src/index.ts is a strict TypeScript test target for coding tasks.",
        "sandbox/test_parser.py tests recovery from malformed model JSON.",
        "sandbox/SOP-26117_Pervaporation_Rig.txt is a sample engineering reference document.",
        "sandbox/_agent_run.py is generated temporarily by run_python().",
    ]:
        add_bullet(document, item)
    document.add_paragraph(
        "The TypeScript package has a strict noEmit compiler configuration. Its package.json currently "
        "contains only a placeholder test script, so direct validation is normally done with npx tsc --noEmit."
    )

    document.add_heading("12. Typical Setup and Usage", 1)
    commands = [
        "Start Ollama and ensure the configured models are installed.",
        "Start LiteLLM: litellm --config litellm_config.yaml --port 4000",
        "Check the proxy: python testlitellm.py",
        "Ingest references: python -m workbench.rag ingest sandbox/SOP-26117_Pervaporation_Rig.txt",
        "Run parser checks: python sandbox/test_parser.py",
        "Run a reasoning task: python run_agent.py \"what is transformer architecture\"",
        "Run a coding task: python run_agent.py \"Fix and test sandbox/app/src/index.ts\"",
        "Run an image task: python run_agent.py \"Analyze this process diagram\" --image images.jpg",
    ]
    for command in commands:
        add_number(document, command)

    document.add_heading("13. Older Prototype", 1)
    document.add_paragraph(
        "agent_router.py is the earlier implementation. It classifies a task and routes it directly "
        "to a reasoning, coder, or vision model. It does not have the current tool protocol, file policy, "
        "RAG search, execution verification, or loop protection. It is useful for understanding the "
        "project's evolution but is not the primary workbench entry point."
    )

    document.add_heading("14. Current Caveats", 1)
    for item in [
        "LiteLLM and Ollama must be running before the main agent can make model calls.",
        "The project has no dependency lockfile or requirements file, so Python dependencies must be installed separately.",
        "Re-ingesting the same document appends duplicate chunks to vectorstore.json.",
        "run_command uses shell=True; project path checks do not make it equivalent to an OS-level container.",
        "Vision classification currently uses the reasoning worker, which must invoke the vision tools explicitly.",
        "The TypeScript source comment mentions a typo, but the current code uses the declared value property correctly.",
        "Generated approval notes are drafts and require human engineer review and sign-off.",
    ]:
        add_bullet(document, item)

    document.add_heading("15. Summary", 1)
    document.add_paragraph(
        "The center of the project is workbench/agent.py. It coordinates a local router and worker "
        "model through a LangGraph state machine. workbench/tools.py supplies controlled local capabilities, "
        "workbench/rag.py grounds answers in reference documents, workbench/llm.py connects to the local "
        "LiteLLM proxy, and run_agent.py provides the user-facing command-line interface. The sandbox is "
        "where code tasks are created and tested, while outputs/ contains generated deliverables."
    )

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    document.save(OUTPUT_PATH)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(f"Created {build_document()}")