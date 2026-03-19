# CliniGraph AI Renaming Plan

## Goal

Migrate technical naming from legacy `AgentAI` patterns to `CliniGraph AI` without downtime or integration breakage.

## Phase 1: Brand-First (Completed)

- Product-facing docs and scripts use CliniGraph AI language.
- Technical paths and endpoint URLs remain stable.
- Existing workflows continue unchanged.

## Phase 2: Internal Alias Layer (Completed)

- Add non-breaking aliases:
  - `CliniGraphService` aliasing `AgentAIService`
  - `CliniGraphSettings` aliasing `AgentAISettings`
- Begin using aliases in new internal call sites.
- Keep old symbols available for backward compatibility.

## Phase 3: Contract Stabilization (Recommended Next)

- Introduce clear deprecation notices in docs for legacy symbol names.
- Add compatibility tests for both old and new imports.
- Keep endpoint paths stable while API docs highlight v2 generic medical routes.

## Phase 4: Repository and Folder Rename (In Progress)

- Rename repository from `phyton_chat` to a product-aligned name when CI/CD and deployment references are ready.
- Workspace folder rename completed: `chat-build` -> `clinigraph-ai`.
- Update all hardcoded paths in PowerShell scripts and documentation.

## Phase 5: Cleanup Window (Planned)

- Remove deprecated `AgentAI*` aliases after one planned release cycle.
- Keep migration notes and changelog entries for upgrade guidance.

## Risks and Controls

- Risk: Breaking local scripts due to path assumptions.
  - Control: Keep path-compatible wrappers during transition.
- Risk: Downstream imports tied to old class names.
  - Control: Keep aliases and add explicit deprecation timeline.
- Risk: Confusion between brand and code names.
  - Control: Maintain single source of truth in docs (`BRANDING.md`, this plan).
