# Binding documents

This repository's behavior is governed by two documents that live outside the
codebase. They take precedence over any code or comment in this repo.

## 1. Core/Product Separation Charter v1.0

Defines the rules that separate Core (private infrastructure) from Products
(customer-facing offerings). Establishes the engine-plus-shells pattern that
this repository implements.

**Location:** SageForge Core document archive (admin-only).

## 2. MACIE v1 Specification

The binding build target for Phase 1 of this product. Defines the engine
interface, both shells, acceptance criteria, and the nine-step build order.

**Location:** SageForge Core document archive (admin-only).

## Precedence rule

If anything in this repository conflicts with either document, the documents
win. The code must be corrected, not the documents.

## Amendments

Either document may only be amended by Pete, in writing, with a new version
number. When amended, this repository's behavior may change accordingly and a
matching code change must be made before the next stage transition.
