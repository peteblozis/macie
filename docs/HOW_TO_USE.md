# MACIE — How to Install and Use It Today

**For:** Pete (local Windows)
**Status:** Semi-production, Phase A
**Estimated time to first working query:** 20–30 minutes

---

## What you're getting

A working MACIE v1 system you can run on your Windows machine today.
Type a question, MACIE asks both Gemini (substituting for Claude) and
ChatGPT, compares their answers, and gives you back a synthesized
result with a confidence reading and a substitution banner.

Pete Jr.'s remote web access through `core.actionforgelabs.com` is
**Phase B**, a separate build session.

---

## Part 1 — One-Time Installation (do this once)

### Step 1.1: Copy the files into place

Open PowerShell (no admin needed). Paste these commands one at a time,
hit Enter after each. Replace `<extract_path>` with the folder you
extracted this package to (probably your Downloads folder).

```powershell
# Copy Gemini adapter into the existing adapters folder
Copy-Item "<extract_path>\engine\src\adapters\gemini_adapter.py" `
          "C:\SageForge\macie\engine\src\adapters\"

# Copy the project-level files
Copy-Item "<extract_path>\macie_config.py"        "C:\SageForge\macie\"
Copy-Item "<extract_path>\audit_log.py"           "C:\SageForge\macie\"
Copy-Item "<extract_path>\cli.py"                 "C:\SageForge\macie\"
Copy-Item "<extract_path>\macie_interactive.py"   "C:\SageForge\macie\"
Copy-Item "<extract_path>\macie.ps1"              "C:\SageForge\macie\"
Copy-Item "<extract_path>\SPEC_AMENDMENT.md"      "C:\SageForge\macie\docs\"
```

### Step 1.2: Install the Gemini SDK

```powershell
pip install google-generativeai
```

If pip says "not recognized", try `py -m pip install google-generativeai`.

### Step 1.3: Set your API keys permanently

Replace the bracketed parts with your real keys. The `setx` command
saves them permanently so you don't have to set them every time you
open PowerShell.

```powershell
setx OPENAI_API_KEY "<your OpenAI key>"
setx GEMINI_API_KEY "<your Gemini key from aistudio.google.com>"
```

**IMPORTANT:** After running `setx`, **close PowerShell and reopen a
fresh window.** The new keys only show up in newly-opened PowerShell
sessions.

### Step 1.4: Pre-flight check (no API calls yet)

In a fresh PowerShell window:

```powershell
cd C:\SageForge\macie
python cli.py --status
```

You should see something like this:

```
============================================================
MACIE v1 — Current Configuration
============================================================
Spec roster:       ['claude', 'chatgpt']
Current roster:    ['gemini', 'chatgpt']
Substitution:      ACTIVE

Summary: CLAUDE SUBSTITUTED → gemini

Environment keys:
  gemini   needs GEMINI_API_KEY         ✓ set
  chatgpt  needs OPENAI_API_KEY         ✓ set
============================================================
```

**Both keys must say `✓ set`.** If either says `✗ MISSING`, you
either typed setx wrong or didn't open a fresh PowerShell window.
Go back to Step 1.3.

### Step 1.5: Verify your existing tests still pass

This is critical — proves we didn't break anything.

```powershell
cd C:\SageForge\macie
pytest engine/tests/
```

You should see all 19 tests pass (green). If anything fails, **stop
and tell me what failed before continuing.**

### Step 1.6: (Optional) Create a desktop shortcut

So you don't have to navigate to the folder every time:

1. Right-click your desktop → New → Shortcut
2. Location: `powershell.exe -NoExit -Command "cd C:\SageForge\macie; python macie_interactive.py"`
3. Name: `MACIE`
4. Click Finish

Now double-clicking the MACIE shortcut opens PowerShell already in the
right folder, already running MACIE interactive mode.

---

## Part 2 — How to Use It (the daily workflow)

### The fast way: interactive mode

**From PowerShell:**

```powershell
cd C:\SageForge\macie
python macie_interactive.py
```

**Or:** Double-click the MACIE desktop shortcut you made in Step 1.6.

You'll see this welcome screen:

```
======================================================================
  MACIE — Multi-AI Consensus Intelligence Engine
  Interactive Mode

  Type your question and hit Enter. MACIE will ask both AI models,
  compare their answers, and give you a synthesized result.

  Commands:  /help  /status  /audit  /shell core  /shell prod  /quit
======================================================================

  ⚠  CLAUDE SUBSTITUTED — Gemini
     CLAUDE SUBSTITUTED → gemini

  [core] Your question (or /help):
```

### Entering a prompt and getting an execution

This is the part you asked me to make crystal clear:

**1. Wait until you see this exact line:**

```
  [core] Your question (or /help):
```

**2. Just type your question.** No quotes, no `python`, no `cli.py`.
Just type the question naturally as if you were asking a person.

Example — type this exactly:

```
Should I use Cloudflare Access or Cloudflare Tunnel for SageForge Core?
```

**3. Press Enter.** That's it. You'll see:

```
  Asking gemini and chatgpt ... (this takes 5-30 seconds)
```

**4. Wait 5–30 seconds.** Don't type anything. Don't close the window.
MACIE is sending your question to both AI models in parallel, waiting
for both responses, then synthesizing the answer.

**5. Read the result.** You'll see:

```
======================================================================
  ⚠  CLAUDE SUBSTITUTED — Gemini

[the synthesized answer goes here — multiple paragraphs typically]

----------------------------------------------------------------------
  Request: a1b2c3d4   Confidence: high   Shell: core
    [OK] gemini     1842 ms
    [OK] chatgpt    2103 ms
======================================================================

  [core] Your question (or /help):
```

**6. Ask another question, or exit.** The prompt comes back
automatically. Type another question to keep going, or type `/quit`
to exit.

### What the output is telling you

- **The text between the banner lines** is MACIE's synthesized answer.
  This is the consensus result drawing from both models.
- **Confidence: high** means both models responded successfully and
  their answers agree on the key points. `medium` means partial
  agreement, `low` means one failed or they disagreed significantly.
- **The [OK] lines** show that each model responded successfully.
  If you see `[ERR]` instead, that model failed (the other still ran).
- **The request ID** is in the audit log — useful if you ever need
  to look up a past run.

### Special commands you can type at the prompt

Instead of a question, type any of these:

| You type | What happens |
|----------|--------------|
| `/help` | Shows the command list |
| `/status` | Shows which models are wired up right now |
| `/audit` | Shows your last 10 MACIE runs from the log |
| `/shell prod` | Switches to Production Shell tone for the next queries |
| `/shell core` | Switches back to Core Shell (default) |
| `/quit` | Exits MACIE |

---

## Part 3 — Troubleshooting Cheat Sheet

### "I don't see the prompt — it's just sitting there"

Wait a few seconds longer. The first query of a session can take
30+ seconds because Python is loading the SDK packages. Subsequent
queries are faster.

### "It says GEMINI_API_KEY not set"

You either didn't run `setx` correctly, or you ran it but didn't
**close and reopen PowerShell**. Try Step 1.3 again, then open a
brand new PowerShell window.

### "It says google-generativeai SDK not installed"

You forgot Step 1.2. Run `pip install google-generativeai`.

### "It says ANTHROPIC_API_KEY not set"

This shouldn't happen while substitution is active — MACIE knows it
doesn't need Anthropic right now. If you see this, check
`macie_config.py` — `SUBSTITUTION_ACTIVE` should be `True`.

### "The answer cut off mid-sentence"

The default token limit is 2048. For longer answers, you can edit
the adapters to raise `max_tokens`. Or just ask MACIE to continue:
type `please continue` as your next question.

### "It crashed with an ImportError"

Run from inside `C:\SageForge\macie` — not from elsewhere. If you're
in `C:\Users\peteb`, your imports will fail.

### "I want to see the raw answers from each model separately, not just the synthesis"

Use the JSON output mode in the CLI version:

```powershell
python cli.py --json "your question" > result.json
notepad result.json
```

The JSON shows each model's raw text plus the synthesis.

### "Something else is wrong"

Run `python cli.py --status` and `python cli.py --audit 5` — those two
together usually point at the problem. Then tell me what they show.

---

## Part 4 — When Anthropic Fixes Your Account

The day support resolves the PeteAI, LLC reclassification:

1. Open `C:\SageForge\macie\macie_config.py` in Notepad
2. Find this line:
   ```python
   SUBSTITUTION_ACTIVE = True
   ```
3. Change it to:
   ```python
   SUBSTITUTION_ACTIVE = False
   ```
4. Save the file
5. Your next MACIE run uses the spec roster `[claude, chatgpt]`. The
   substitution banner disappears. Audit log entries go back to
   `substitution_active: false`.

**One line. That's it.**

---

## Part 5 — What's Next (Phase B)

Pete Jr. doesn't have access yet. To give him remote access via
`core.actionforgelabs.com`, we need:

1. A thin web wrapper (Flask or FastAPI) that exposes MACIE as a
   simple form-and-answer page
2. Deployment behind your existing Cloudflare Access policy
3. Pete Jr.'s email added to the allowed users list

That's a separate work session — probably 1–2 hours. Tell me when
you're ready and I'll build it.

In the meantime, you can use MACIE locally starting today.

---

## File map (for reference)

```
C:\SageForge\macie\
├── macie_config.py             ← edit this to flip substitution off
├── cli.py                       ← command-line interface
├── macie_interactive.py         ← interactive mode (recommended)
├── macie.ps1                    ← PowerShell wrapper
├── audit_log.py                 ← append-only logger
├── docs\
│   └── SPEC_AMENDMENT.md        ← amendment authorizing substitution
└── engine\
    └── src\
        └── adapters\
            └── gemini_adapter.py    ← the only new file inside engine/
```

Everything else in `C:\SageForge\macie\` was already there and was
not modified.
