"""
MACIE Web Server
================
Serves the MACIE browser interface at http://localhost:5000/macie

Run from C:\SageForge\macie:
    python macie_web.pys

Then visit http://localhost:5000/macie in your browser.
Pete Jr. reaches it through core.actionforgelabs.com/macie via Cloudflare Tunnel.
"""

from __future__ import annotations
import json
import os
import sys
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

import macie_config as cfg
from audit_log import log_run

app = Flask(__name__)

# ── HTML template ─────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MACIE — SageForge Core</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0c10;
    --surface: #111318;
    --surface2: #181c24;
    --border: #1e2330;
    --gold: #c9a84c;
    --gold-dim: #8a6e2f;
    --text: #e8eaf0;
    --text-dim: #6b7280;
    --text-muted: #3d4452;
    --green: #2dd4a0;
    --red: #f87171;
    --blue: #60a5fa;
    --radius: 12px;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-weight: 300;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -20%, rgba(201,168,76,0.08) 0%, transparent 60%);
  }

  header {
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(10,12,16,0.8);
    backdrop-filter: blur(12px);
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .logo-icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, var(--gold) 0%, var(--gold-dim) 100%);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'DM Serif Display', serif;
    font-size: 16px;
    color: #0a0c10;
    font-weight: 700;
  }

  .logo-text {
    font-family: 'DM Serif Display', serif;
    font-size: 20px;
    color: var(--gold);
    letter-spacing: 0.02em;
  }

  .logo-sub {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 1px;
  }

  .sub-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--gold-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid var(--gold-dim);
    padding: 5px 12px;
    border-radius: 20px;
  }

  .sub-dot {
    width: 6px;
    height: 6px;
    background: var(--gold);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  main {
    max-width: 860px;
    margin: 0 auto;
    padding: 48px 24px 80px;
  }

  .page-title {
    font-family: 'DM Serif Display', serif;
    font-size: 42px;
    color: var(--text);
    margin-bottom: 8px;
    line-height: 1.1;
  }

  .page-title span { color: var(--gold); }

  .page-subtitle {
    font-size: 14px;
    color: var(--text-dim);
    margin-bottom: 40px;
    line-height: 1.6;
  }

  .query-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
    margin-bottom: 32px;
  }

  .shell-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
  }

  .shell-tab {
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 12px;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.06em;
    cursor: pointer;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
    transition: all 0.15s;
  }

  .shell-tab.active {
    background: var(--gold);
    color: #0a0c10;
    border-color: var(--gold);
    font-weight: 500;
  }

  .shell-tab:hover:not(.active) {
    border-color: var(--gold-dim);
    color: var(--text);
  }

  textarea {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-size: 15px;
    font-weight: 300;
    padding: 16px;
    resize: vertical;
    min-height: 100px;
    outline: none;
    transition: border-color 0.2s;
    line-height: 1.6;
  }

  textarea:focus { border-color: var(--gold-dim); }
  textarea::placeholder { color: var(--text-muted); }

  .query-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 16px;
  }

  .model-pills {
    display: flex;
    gap: 8px;
  }

  .model-pill {
    font-size: 11px;
    font-family: 'DM Mono', monospace;
    padding: 4px 10px;
    border-radius: 4px;
    border: 1px solid var(--border);
    color: var(--text-dim);
  }

  .model-pill.sub {
    border-color: var(--gold-dim);
    color: var(--gold-dim);
  }

  button#submit-btn {
    background: var(--gold);
    color: #0a0c10;
    border: none;
    padding: 12px 28px;
    border-radius: 8px;
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    letter-spacing: 0.02em;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  button#submit-btn:hover { background: #d4b05a; transform: translateY(-1px); }
  button#submit-btn:active { transform: translateY(0); }
  button#submit-btn:disabled {
    background: var(--text-muted);
    cursor: not-allowed;
    transform: none;
  }

  .progress-bar {
    height: 2px;
    background: var(--border);
    border-radius: 2px;
    margin: 20px 0;
    overflow: hidden;
    display: none;
  }

  .progress-bar.active { display: block; }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--gold-dim), var(--gold));
    border-radius: 2px;
    width: 0%;
    transition: width 0.5s ease;
  }

  .step-indicator {
    font-size: 12px;
    font-family: 'DM Mono', monospace;
    color: var(--gold);
    margin-bottom: 12px;
    display: none;
    letter-spacing: 0.06em;
  }

  .step-indicator.active { display: block; }

  .result-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: none;
    animation: fadeUp 0.4s ease;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .result-card.visible { display: block; }

  .result-header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface2);
  }

  .result-label {
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-dim);
    font-family: 'DM Mono', monospace;
  }

  .confidence-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-family: 'DM Mono', monospace;
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid;
  }

  .confidence-badge.high { color: var(--green); border-color: var(--green); }
  .confidence-badge.medium { color: var(--gold); border-color: var(--gold); }
  .confidence-badge.low { color: var(--red); border-color: var(--red); }

  .result-body { padding: 28px 28px 24px; }

  .synthesized-answer {
    font-size: 15px;
    line-height: 1.8;
    color: var(--text);
    font-weight: 300;
    margin-bottom: 24px;
    white-space: pre-wrap;
  }

  .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-top: 20px;
  }

  .meta-block {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
  }

  .meta-block-title {
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-dim);
    font-family: 'DM Mono', monospace;
    margin-bottom: 10px;
  }

  .meta-block-content {
    font-size: 13px;
    color: var(--text);
    line-height: 1.6;
    font-weight: 300;
  }

  .rationale-block {
    background: var(--surface2);
    border-left: 3px solid var(--gold);
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin-top: 20px;
    font-size: 14px;
    color: #b0b8c8;
    line-height: 1.6;
    font-style: italic;
  }

  .result-footer {
    padding: 14px 24px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    font-family: 'DM Mono', monospace;
    color: #6b7280;
  }

  .model-status {
    display: flex;
    gap: 16px;
  }

  .model-status-item {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .status-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
  }

  .status-dot.ok { background: var(--green); }
  .status-dot.err { background: var(--red); }

  .error-card {
    background: rgba(248,113,113,0.05);
    border: 1px solid rgba(248,113,113,0.2);
    border-radius: var(--radius);
    padding: 20px 24px;
    display: none;
    color: var(--red);
    font-size: 14px;
  }

  .error-card.visible { display: block; }

  @media (max-width: 600px) {
    header { padding: 16px 20px; }
    main { padding: 32px 16px 60px; }
    .page-title { font-size: 32px; }
    .meta-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">M</div>
    <div>
      <div class="logo-text">MACIE</div>
      <div class="logo-sub">SageForge Core · Forge Factory</div>
    </div>
  </div>
  <div class="sub-badge">
    <div class="sub-dot"></div>
    {{ "CLAUDE SUBSTITUTED" if substitution_active else "Spec Roster" }}
  </div>
</header>

<main>
  <h1 class="page-title">Multi-AI <span>Consensus</span><br>Intelligence Engine</h1>
  <p class="page-subtitle">
    Ask a question. MACIE dispatches to both AI models simultaneously,
    compares their reasoning, and synthesizes a stronger unified answer
    with confidence scoring.
  </p>

  <div class="query-card">
    <div class="shell-tabs">
      <button class="shell-tab active" onclick="setShell('core', this)">Core Shell</button>
      <button class="shell-tab" onclick="setShell('production', this)">Production Shell</button>
    </div>

    <textarea id="query-input"
      placeholder="Enter your question, objective, or decision here..."
      onkeydown="handleKey(event)"></textarea>

    <div class="query-footer">
      <div class="model-pills">
        <div class="model-pill">claude</div>
        <div class="model-pill">chatgpt</div>
      </div>
      <button id="submit-btn" onclick="submitQuery()">
        <span id="btn-text">Ask MACIE</span>
      </button>
    </div>
  </div>

  <div class="progress-bar" id="progress-bar">
    <div class="progress-fill" id="progress-fill"></div>
  </div>
  <div class="step-indicator" id="step-indicator">Initializing...</div>

  <div class="result-card" id="result-card">
    <div class="result-header">
      <span class="result-label">Synthesized Consensus</span>
      <div class="confidence-badge" id="confidence-badge">
        <span id="confidence-dot">◆</span>
        <span id="confidence-text">—</span>
      </div>
    </div>
    <div class="result-body">
      <div class="synthesized-answer" id="synthesized-answer"></div>
      <div class="rationale-block" id="rationale-block"></div>
      <div class="meta-grid">
        <div class="meta-block">
          <div class="meta-block-title">Agreements</div>
          <div class="meta-block-content" id="agreements-content">—</div>
        </div>
        <div class="meta-block">
          <div class="meta-block-title">Divergences</div>
          <div class="meta-block-content" id="divergences-content">—</div>
        </div>
      </div>
    </div>
    <div class="result-footer">
      <span id="request-id-label">—</span>
      <div class="model-status" id="model-status"></div>
    </div>
  </div>

  <div class="error-card" id="error-card"></div>
</main>

<script>
let currentShell = 'core';

function setShell(shell, btn) {
  currentShell = shell;
  document.querySelectorAll('.shell-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
}

function handleKey(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitQuery();
}

function setProgress(pct, label) {
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('step-indicator').textContent = label;
}

async function submitQuery() {
  const query = document.getElementById('query-input').value.trim();
  if (!query) return;

  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  document.getElementById('btn-text').textContent = 'Running...';

  document.getElementById('result-card').classList.remove('visible');
  document.getElementById('error-card').classList.remove('visible');
  document.getElementById('progress-bar').classList.add('active');
  document.getElementById('step-indicator').classList.add('active');

  setProgress(10, 'Step 1/3 — Asking Claude...');

  try {
    const resp = await fetch('/macie/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, shell: currentShell })
    });

    setProgress(60, 'Step 2/3 — Asking ChatGPT...');
    await new Promise(r => setTimeout(r, 400));
    setProgress(90, 'Step 3/3 — Synthesizing consensus...');
    await new Promise(r => setTimeout(r, 400));

    const data = await resp.json();
    setProgress(100, 'Done');

    if (data.error) {
      document.getElementById('error-card').textContent = 'Error: ' + data.error;
      document.getElementById('error-card').classList.add('visible');
    } else {
      showResult(data);
    }
  } catch(e) {
    document.getElementById('error-card').textContent = 'Request failed: ' + e.message;
    document.getElementById('error-card').classList.add('visible');
  } finally {
    btn.disabled = false;
    document.getElementById('btn-text').textContent = 'Ask MACIE';
    document.getElementById('progress-bar').classList.remove('active');
    document.getElementById('step-indicator').classList.remove('active');
  }
}

function showResult(data) {
  const card = document.getElementById('result-card');
  const conf = (data.confidence || 'medium').toLowerCase();

  document.getElementById('synthesized-answer').textContent = data.synthesized_answer || '';
  document.getElementById('rationale-block').textContent = data.rationale || '';
  document.getElementById('agreements-content').textContent = data.agreements || '—';
  document.getElementById('divergences-content').textContent = data.divergences || '—';
  document.getElementById('request-id-label').textContent = 'req: ' + (data.request_id || '—');

  const badge = document.getElementById('confidence-badge');
  badge.className = 'confidence-badge ' + conf;
  document.getElementById('confidence-text').textContent = conf.toUpperCase();

  const statusEl = document.getElementById('model-status');
  statusEl.innerHTML = (data.model_statuses || []).map(s =>
    `<div class="model-status-item">
      <div class="status-dot ${s.ok ? 'ok' : 'err'}"></div>
      <span>${s.name}</span>
    </div>`
  ).join('');

  card.classList.add('visible');
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
</script>
</body>
</html>
"""

# ── API routes ─────────────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are the synthesis engine for MACIE, a Multi-AI Consensus Intelligence Engine.

Below are responses from two AI models answering the same question.
Your job is to:
1. Identify where they agree
2. Identify where they differ  
3. Produce ONE unified synthesized answer stronger than either alone
4. Give a confidence rating: high, medium, or low

USER QUESTION: {question}

MODEL A (Claude) RESPONSE:
{response_a}

MODEL B (ChatGPT) RESPONSE:
{response_b}

Respond in this exact format:
SYNTHESIZED ANSWER:
[your unified answer here]

CONFIDENCE: [high/medium/low]
RATIONALE: [one sentence]
AGREEMENTS: [key shared points]
DIVERGENCES: [key differences, or "None significant"]"""


def call_claude(query: str):
    provider = os.environ.get("CLAUDE_PROVIDER", "anthropic").lower()
    try:
        if provider == "openrouter":
            from openai import OpenAI
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return "", "OPENROUTER_API_KEY not set"
            model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
            client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": query}],
                max_tokens=2048,
            )
            return response.choices[0].message.content or "", None
        else:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                return "", "ANTHROPIC_API_KEY not set"
            model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": query}],
            )
            return message.content[0].text or "", None
    except Exception as e:
        return "", str(e)


def call_chatgpt(query: str):
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "", "OPENAI_API_KEY not set"
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": query}],
            max_tokens=2048, temperature=0.3)
        return response.choices[0].message.content or "", None
    except Exception as e:
        return "", str(e)


def synthesize(question: str, response_a: str, response_b: str):
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        prompt = SYNTHESIS_PROMPT.format(
            question=question, response_a=response_a, response_b=response_b)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048, temperature=0.2)
        return response.choices[0].message.content or ""
    except Exception:
        return None


def parse_synthesis(text: str) -> dict:
    """Parse the structured synthesis response into fields."""
    result = {
        "synthesized_answer": "",
        "confidence": "medium",
        "rationale": "",
        "agreements": "",
        "divergences": "",
    }
    if not text:
        return result

    sections = {
        "SYNTHESIZED ANSWER:": "synthesized_answer",
        "CONFIDENCE:": "confidence",
        "RATIONALE:": "rationale",
        "AGREEMENTS:": "agreements",
        "DIVERGENCES:": "divergences",
    }

    current_key = None
    current_lines = []

    for line in text.splitlines():
        matched = False
        for marker, field in sections.items():
            if line.strip().upper().startswith(marker):
                if current_key:
                    result[current_key] = "\n".join(current_lines).strip()
                current_key = field
                remainder = line[len(marker):].strip()
                current_lines = [remainder] if remainder else []
                matched = True
                break
        if not matched and current_key:
            current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()

    # Clean confidence to just the word
    conf = result["confidence"].lower().strip()
    if "high" in conf:
        result["confidence"] = "high"
    elif "low" in conf:
        result["confidence"] = "low"
    else:
        result["confidence"] = "medium"

    return result


@app.route("/macie")
def index():
    return render_template_string(
        HTML,
        substitution_active=cfg.SUBSTITUTION_ACTIVE,
    )


@app.route("/macie/query", methods=["POST"])
def query():
    data = request.get_json()
    if not data or not data.get("query"):
        return jsonify({"error": "No query provided"}), 400

    user_query = data["query"].strip()
    shell = data.get("shell", "core")
    request_id = str(uuid.uuid4())[:8]

    claude_text, claude_error = call_claude(user_query)
    chatgpt_text, chatgpt_error = call_chatgpt(user_query)

    if claude_error and chatgpt_error:
        return jsonify({
            "error": f"Both models failed. Claude: {claude_error}. ChatGPT: {chatgpt_error}"
        }), 500

    synthesis_text = None
    if claude_text and chatgpt_text:
        synthesis_text = synthesize(user_query, claude_text, chatgpt_text)

    if synthesis_text:
        parsed = parse_synthesis(synthesis_text)
    else:
        parsed = {
            "synthesized_answer": (
                (claude_text or "") + ("\n\n---\n\n" + chatgpt_text if chatgpt_text else "")
            ),
            "confidence": "low",
            "rationale": "Synthesis unavailable — showing raw model responses.",
            "agreements": "",
            "divergences": "",
        }

    log_run(
        request_id=request_id,
        user_prompt=user_query,
        roster=cfg.current_roster(),
        substitution_active=cfg.SUBSTITUTION_ACTIVE,
        substitution_summary=cfg.substitution_summary(),
        shell=shell,
        success=True,
        confidence=parsed["confidence"],
    )

    return jsonify({
        "request_id": request_id,
        "shell": shell,
        "substitution_active": cfg.SUBSTITUTION_ACTIVE,
        **parsed,
        "model_statuses": [
            {"name": "claude", "ok": not claude_error},
            {"name": "chatgpt", "ok": not chatgpt_error},
        ],
    })


@app.route("/macie/status")
def status():
    return jsonify({
        "substitution_active": cfg.SUBSTITUTION_ACTIVE,
        "roster": cfg.current_roster(),
        "summary": cfg.substitution_summary(),
    })


if __name__ == "__main__":
    print("=" * 60)
    print("  MACIE Web Server")
    print("  http://localhost:5000/macie")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False)
