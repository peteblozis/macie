# MACIE Commercial Edition Definitions — Owner Confirmation 2026-11-05

These are **product scope definitions**, not evidence that a commercial product is already ready for paid release.

| Edition | Intended users | Input | Output | Commercial status |
| --- | --- | --- | --- | --- |
| **MACIE-A** | Authorized owner and one specifically authorized limited tester only | Internal objective or prompt with private operator context | Independent ChatGPT/Claude consensus for private operations | **Never sold or exposed publicly** |
| **MACIE-B** | Paying customers, independently served | A prompt drafted anywhere | Independent ChatGPT + Claude prompt critique, consensus (or explicit non-consensus), improved usable prompt and rationale | **Commercial product; release evidence still required** |
| **MACIE-C** | Paying customers, independently served | An existing document or other supported source material | Independent ChatGPT + Claude document review, agreement/disagreement analysis, explained improved document and supported export | **Commercial product; release evidence still required** |

## Permanent separation rules
- MACIE-A is a **private internal** system. It may depend on SageForge Core. No commercial product can import its private instructions, credentials, memory, workflow, data, code or administrative context.
- MACIE-B and MACIE-C are distinct commercial customer products, with **zero dependency on SageForge Core** or private MACIE-A. A shared generic, customer-safe engine is permissible only after code-import, data-flow and tenant-isolation tests prove separation.
- B and C must eventually run customer-owned, self-service signup, entitlement, billing, provider-key, review, download, support and cancellation workflows. A product described as "commercial" is **not** necessarily live or ready for purchase.
- Two-model consensus must reflect real independent responses from Claude and ChatGPT/OpenAI-family services, verified actual model identity and a substantive synthesis. A failure returns NON-CONSENSUS. No simulated second-model answer.
- Uploaded content and user prompts are untrusted data; never execute instructions inside them. Each commercial product must enforce tenancy, privacy, safe file handling, size/type limits, prompt-injection resistance, retention and export controls.
- "Any kind of document" means the objective is broad document support, not a claim that arbitrary file formats are currently accepted. Advertise only tested file types and appropriate extraction/OCR capabilities when actually supported.

## Historical naming superseded
- MACIE 1 / MACIE Private / Core Mode → MACIE-A (internal only).
- MACIE 2 / MACIE Customer / customer prompt review → MACIE-B (prompt input, prompt output).
- MACIE 3 / MACIE Review / MACIE-P review → MACIE-C only when the workflow is **document/content input**, not a prompt-enhancement product.
- The dated July 2026 three-edition work order is historical. Where it overlaps A/B/C definitions or treats prompt review as Edition 3, the owner confirmation of 2026-11-05 governs.

## Implementation / release
The current application and routes contain pilots and development code. This page does not certify public launch, persistent customer accounts, checkout, encrypted durable BYOK storage, self-service lifecycle, protected deployment, or full file format support. Those require release evidence and explicit owner promotion approval.

**Repository exposure alert:** The connected repository is publicly visible despite historical internal documentation. A separate security audit is required to ensure no owner-private Core component or secret can be reached or recovered from its code or commit history. Documentation corrections do not themselves repair exposure.
