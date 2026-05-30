"""
MACIE Core Shell.

For Pete (admin/owner) and Pete Jr. (tester) use only. Wraps the shared
engine with Cloudflare Access protection, MFA, audit logging, project memory,
and Forge Factory integration.

This package may import from engine. It must NEVER be importable from
engine or from prod-shell.
"""

__version__ = "0.1.0"
