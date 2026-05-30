"""
Core Shell — main entry point.

Phase 1, Step 4: Full Core Shell with audit logging, result persistence,
history view, and versioned artifact export.

Access: Pete (admin/owner) and Pete Jr. (tester, no admin) only.
All routes protected by Cloudflare Access + MFA (Step 5).
"""

from __future__ import annotations

from engine.src import consensus, ConsensusResult
from engine.src.consensus_types import Confidence
from core_shell.src import audit, result_store


# Phase 1 default roster
DEFAULT_ROSTER = ["claude", "chatgpt"]


def submit_query(
    user_email: str,
    query: str,
    project_context: dict | None = None,
    roster: list[str] | None = None,
    options: dict | None = None,
) -> dict:
    """
    Submit a consensus query from the Core Shell.

    Args:
        user_email: Authenticated user (verified upstream by Cloudflare Access).
        query: The query text.
        project_context: Optional Forge Factory project context to prepend.
        roster: Override the default model roster.
        options: Pass-through options for the engine.

    Returns:
        dict with keys:
            - artifact_id: The ID of the saved result artifact
            - result: The ConsensusResult object
    """
    if not user_email:
        raise PermissionError("user_email required; access must be authenticated upstream")

    # Log query submission
    audit.write("query_submitted", user_email, {
        "query_preview": query[:80],
        "roster": roster or DEFAULT_ROSTER,
        "has_project_context": bool(project_context),
    })

    # Apply project context as a prompt prefix
    if project_context:
        context_block = _format_context(project_context)
        full_query = f"{context_block}\n\nQuery:\n{query}"
    else:
        full_query = query

    try:
        result = consensus(
            full_query,
            roster or DEFAULT_ROSTER,
            options=options or {},
        )
    except Exception as e:
        audit.write("query_failed", user_email, {
            "query_preview": query[:80],
            "error": str(e),
        })
        raise

    # Save the result as a versioned artifact
    artifact_id = result_store.save(result, query, user_email, project_context)

    # Log completion
    audit.write("consensus_completed", user_email, {
        "artifact_id": artifact_id,
        "confidence": result.confidence.value,
        "divergence_count": len(result.divergences),
        "models_succeeded": result.telemetry.get("models_succeeded", 0),
        "total_latency_ms": result.telemetry.get("total_latency_ms", 0),
    })

    return {
        "artifact_id": artifact_id,
        "result": result,
    }


def get_history(user_email: str, n: int = 20) -> list[dict]:
    """
    Get the query history for a user.

    Args:
        user_email: The authenticated user.
        n: Maximum number of results to return (most recent first).

    Returns:
        List of artifact summary dicts.
    """
    if not user_email:
        raise PermissionError("user_email required")

    audit.write("history_viewed", user_email, {"n_requested": n})
    return result_store.list_recent(n=n, user_email=user_email)


def export_artifact(user_email: str, artifact_id: str) -> dict:
    """
    Export a single result artifact by ID.

    Args:
        user_email: The authenticated user requesting the export.
        artifact_id: The artifact to export.

    Returns:
        The full artifact dict including all model outputs and telemetry.

    Raises:
        PermissionError: If user_email is empty.
        FileNotFoundError: If the artifact does not exist.
    """
    if not user_email:
        raise PermissionError("user_email required")

    artifact = result_store.load(artifact_id)
    if artifact is None:
        raise FileNotFoundError(f"Artifact {artifact_id} not found")

    audit.write("artifact_exported", user_email, {
        "artifact_id": artifact_id,
    })

    return artifact


def get_audit_log(user_email: str, n: int = 50) -> list[dict]:
    """
    Return recent audit log entries. Admin use only.

    In Phase 1, this is accessible to Pete only (enforced by Cloudflare
    Access at the route level in Step 5). Pete Jr. does not have access
    to the raw audit log.

    Args:
        user_email: Must be the admin user (Pete).
        n: Maximum number of entries to return.
    """
    if not user_email:
        raise PermissionError("user_email required")

    # Audit the audit log access itself
    audit.write("audit_log_accessed", user_email, {"n_requested": n})
    return audit.read_recent(n=n)


def _format_context(context: dict) -> str:
    """Render a project context dict as a prompt prefix."""
    lines = ["Context for this query:"]
    for key, value in context.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
