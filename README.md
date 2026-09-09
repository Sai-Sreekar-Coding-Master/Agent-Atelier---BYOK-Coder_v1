# AgentArena — Atelier

**Chat with custom AI flows like a normal chat app. Build multi-agent workflows visually, then chat with them directly.**

AgentArena is a single-file web app + local Python proxy server that lets you wire multiple AI models together into visual flows — then chat with those flows as if they were a single assistant. No backend to deploy, no database to configure. Everything runs in your browser; the Python server handles API calls so providers like NVIDIA NIM, OpenAI, and OpenCode Zen work without CORS errors.

---

## Quick Start

```bash
# 1. Put both files in the same folder
#    AgentArena-Atelier.html
#    server.py

# 2. Run the server
python server.py

# 3. Open in your browser
#    http://localhost:5001
```

That's it. The app auto-detects the local proxy and routes all API calls through it.

---

## What Makes This Different

Most AI flow builders (n8n, ComfyUI, LangFlow) are workflow tools first — you build a flow, run it, read the output. AgentArena flips that: **you chat first, the flow runs behind the scenes**. Pick a flow from the dropdown in the topbar, type a message, and the flow executes with your full conversation history passed through every agent.

- **Chat with any flow directly** — select a flow from the topbar dropdown, send a message, get the flow's output as a chat reply
- **Multi-message context** — the last 12 messages of your conversation are passed through to every agent in the flow
- **Default "Direct chat" flow** — ships with a single-model flow that uses your global API config, so out-of-the-box it works like a normal chat app

---

## Flow System

### Node Types

| Node | Icon | Description |
|------|------|-------------|
| **Start** | ⚡ | Entry point — your chat message becomes the input |
| **Agent** | ✨ | LLM call — supports any OpenAI-compatible API, with system prompt, temperature, model selection |
| **Condition** | ⎇ | Branch on a JavaScript expression — `true` goes one way, `false` goes another |
| **Code** | `{ }` | Transform text with JavaScript — `result = input.toUpperCase()` |
| **API / Media** | 🖼 | Call any API — text, image generation, audio (TTS/Whisper), video, 3D models |
| **Text File** | 📄 | Intermediate text buffer — upstream agents write to it, downstream agents read from it |
| **Output** | 🏁 | End of flow — collects the final result |

### Multi-Connection (Fan-Out)

One node's output can connect to multiple inputs — like n8n and ComfyUI. An agent can pass its result to two different downstream agents simultaneously. The DAG executor (`execDAG`) handles this with a queue-based traversal that waits for all incoming edges to resolve before processing a node.

### Text File Node — Agent Communication

The Text File node is the intermediate buffer for agent-to-agent communication. Agent A writes its output into the text file, then Agent B and Agent C both read from it as their input. It can connect to any agent, and any agent can connect to it. This lets you build pipelines where multiple agents collaborate through a shared text workspace.

### Flow Runner

The `execDAG` function is a proper DAG executor — not a linear walk. It:
- Follows **all** outgoing edges from each node (fan-out)
- Waits for all incoming edges to a node to be resolved before processing it
- Passes conversation context through to every agent
- Collects results from all Output nodes
- Supports conditions that branch to specific ports
- Visualizes execution status on nodes and edges in real time

---

## Supported Providers

All providers route through `server.py` — no CORS errors, full streaming.

| Provider | Models | Notes |
|----------|--------|-------|
| **NVIDIA NIM** | DeepSeek V4, Llama 3.3 70B, Nemotron Ultra 253B, Kimi K3, MiniMax M2.7 | Auto-injects `reasoning_effort: "max"` and `seed: 0` |
| **OpenCode Zen** | Big Pickle, DeepSeek V4, GLM 5.2, Kimi K3, Grok 4.5, MiniMax M3 | Curated coding models |
| **B.AI** | GPT-5.2, GPT-5 Mini, Claude Opus 4.8, Claude Sonnet 4.6 | OpenAI-compatible endpoint |
| **OpenRouter** | Inkling, GLM 5.2, MiniMax M3, Cohere North Mini Code | Free models available |
| **OpenAI** | GPT-4o, GPT-4o-mini | Standard OpenAI API |
| **TokenRouter** | GLM 5.3 | — |
| **Ollama** | Llama 3.2 (local) | Run locally, no proxy needed |
| **Custom** | Any | Paste your own endpoint |

### NVIDIA NIM Support

NVIDIA NIM blocks browser-direct calls (no CORS headers — [confirmed by NVIDIA](https://forums.developer.nvidia.com/t/please-handle-cors-to-make-it-possible-to-make-calls-from-the-browser/310061)). The Python proxy server bypasses this by making server-to-server requests using the `requests` library — the same pattern as NVIDIA's official Python notebooks. The server also auto-injects NVIDIA-specific parameters:

- `reasoning_effort: "max"` — for reasoning models like Kimi K3
- `seed: 0` — for reproducible outputs
- `max_tokens: 16384` — bumped for reasoning models that need more tokens

---

## Artifact System

Every file the AI creates is a **runnable artifact** — click to open in the built-in editor.

| Type | Extension | Viewer |
|------|-----------|--------|
| JavaScript | `.js` | Code editor + Run (console output) |
| HTML | `.html` | Code editor + Live preview (sandboxed iframe) |
| CSS | `.css` | Code editor |
| JSON | `.json` | Code editor |
| Markdown | `.md` | Code editor + Preview |
| Image | `.png` `.jpg` `.webp` `.svg` | Image viewer |
| Audio | `.mp3` `.wav` `.ogg` `.m4a` | Audio player |
| Video | `.mp4` `.webm` `.mov` | Video player |
| **3D Model** | `.glb` `.gltf` `.obj` `.stl` `.ply` | Interactive 3D viewer (model-viewer) |

### Media Node Presets

| Preset | Use Case |
|--------|----------|
| Seedream (BytePlus) | Image generation |
| OpenAI Images | DALL-E / GPT-Image |
| OpenAI Chat (vision) | Vision-capable chat |
| Whisper | Audio transcription |
| OpenAI TTS | Text-to-speech |
| Music gen | Custom audio API |
| Video gen | Custom video API |
| Custom | Your own endpoint |

Placeholders for body templates: `{{input_raw}}`, `{{image}}`, `{{audio}}`, `{{video}}`, `{{file}}`, `{{model}}`

---

## Architecture

```
Browser (AgentArena-Atelier.html)
  │
  ├── Chat UI — send messages, view streaming responses
  ├── Flow Editor — drag-and-drop node graph (SVG edges, pan/zoom)
  ├── Artifact Panel — code editor, image/audio/video/3D viewers
  └── Settings — provider config, model tester, flow management
  │
  ▼ (all API calls routed through)
  │
server.py (Python, localhost:5001)
  │
  ├── Serves the HTML app (same origin → no CORS)
  ├── Transparent proxy — forwards requests to any API
  ├── SSE streaming pass-through (real-time token streaming)
  ├── Auto-injects NVIDIA-specific params (reasoning_effort, seed)
  └── Uses requests library (server-to-server → no CORS enforcement)
  │
  ▼
  │
API Providers (NVIDIA NIM, OpenAI, OpenRouter, B.AI, OpenCode Zen, ...)
```

### Files

| File | Description |
|------|-------------|
| `AgentArena-Atelier.html` | The entire app — HTML, CSS, JS in one file. No build step, no dependencies. |
| `server.py` | Local Python proxy server. Serves the app + transparently proxies API calls. |

### Key Design Decisions

- **Single HTML file** — no bundler, no npm install, no build step. Open the file and it works.
- **Python proxy, not Node** — Python's `requests` library is the gold standard for API calls. Same pattern as NVIDIA's official Colab notebooks.
- **localStorage for everything** — chats, artifacts, flows, API keys. No database, no server-side state. Keys never leave your browser except to the endpoints you configure.
- **DAG executor, not linear walk** — flows are directed acyclic graphs. One output can fan out to many inputs. The executor waits for all incoming edges before processing a node.
- **No external JS libraries** — the flow editor, markdown renderer, code highlighter, and syntax editor are all hand-written. The only external script is Google's `model-viewer` web component for 3D rendering.

---

## How It Works

### Chat → Flow Bridge

When you select a flow in the topbar dropdown and send a message:

1. Your message becomes the input to the **Start** node
2. The last 12 messages of conversation history are passed as `context`
3. `execDAG` runs the flow — each agent receives the context + its upstream input
4. All **Output** node results are collected
5. The combined output is displayed as the AI's chat reply

If no flow is selected, the app uses the default "Direct chat" flow (single model → your global API config).

### Multi-Message Context

Every agent in a flow receives the full conversation history (last 12 messages) when run from chat. This means agents can reference previous turns, maintain continuity, and respond in context — not just to the current message in isolation.

The `callAgent` function builds the messages array as:
```
[system prompt] + [last 12 conversation messages] + [current input]
```

### CORS Proxy

The app auto-detects if `server.py` is running by pinging `http://localhost:5001/health`. If detected, it sets the CORS proxy to `http://localhost:5001/` for all providers. Every `fetch` call goes through `proxiedUrl()` which prepends the proxy URL.

The Python server receives the request, extracts the target URL from the path, forwards it using `requests.post()`, and streams the response back. Since Python makes server-to-server calls, CORS is never enforced.

---

## Settings

### Agents & API

- **Provider** — select from presets (auto-fills endpoint + default model)
- **Endpoint** — the API URL (auto-filled from provider, or custom)
- **API Key** — stored in localStorage, sent only to the endpoint you configure
- **Model** — type or pick from the provider's model list
- **CORS Proxy URL** — auto-set to `http://localhost:5001/` when the Python server is detected
- **Model Tester** — sends a 16-token "say ok" request to verify each model works. Shows live latency + real error messages. CORS failures are labeled explicitly.
- **Clear & return to demo** — resets to scripted demo mode (no API needed)

### Workflows

- Create, duplicate, delete flows
- Open the visual flow editor
- Flows are saved to localStorage

### Flow Editor

- **Drag nodes** from the toolbar onto the canvas
- **Connect nodes** by dragging from an output port (right side) to an input port (left side)
- **Pan** by dragging the canvas background
- **Zoom** with the scroll wheel or zoom controls
- **Inspector** — click a node to edit its config (system prompt, model, temperature, code, etc.)
- **Delete** — select a node or edge, press Delete or click the trash icon
- **Run flow** — execute with test input, see live status on nodes and edges
- **Flow console** — real-time execution log

---

## Requirements

- Python 3.8+ (for `server.py`)
- The `requests` library (auto-installed on first run if missing)
- A modern browser (Chrome, Firefox, Safari, Edge)

No other dependencies. No npm, no bundler, no build step.

---

## Privacy

- All data (chats, artifacts, flows, API keys) is stored in your browser's localStorage
- API keys are sent only to the endpoints you configure — never to any third party
- The Python proxy server (`server.py`) runs on your machine — your keys never leave localhost
- No analytics, no tracking, no telemetry

---

## License

This project is open source. Use it, modify it, ship with it.

---

## Acknowledgments

- Flow interface inspired by [n8n](https://n8n.io) and [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- 3D model rendering by [Google's model-viewer](https://modelviewer.dev/)
- Fonts: Bricolage Grotesque, Instrument Sans, JetBrains Mono (Google Fonts)
