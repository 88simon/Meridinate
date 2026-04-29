# Architecture Docs

This directory contains architecture notes, approved design direction, and handoff documents for major Meridinate systems.

## Recommended Reading Order

1. [Project Blueprint](/mnt/c/Meridinate/PROJECT_BLUEPRINT.md)
2. [Intel Agent Bot-Operator Alignment](/mnt/c/Meridinate/docs/architecture/INTEL_AGENT_BOT_OPERATOR_ALIGNMENT.md)
3. [Intel Recommendation Activation and Notifications](/mnt/c/Meridinate/docs/architecture/INTEL_RECOMMENDATION_ACTIVATION_AND_NOTIFICATIONS.md)

## What Each Doc Covers

- [Project Blueprint](/mnt/c/Meridinate/PROJECT_BLUEPRINT.md)
  - Current system overview
  - Pipeline stages
  - Key tables, services, pages, and major product systems

- [Intel Agent Bot-Operator Alignment](/mnt/c/Meridinate/docs/architecture/INTEL_AGENT_BOT_OPERATOR_ALIGNMENT.md)
  - Why the Intel pipeline should evolve from narrative reporting to bot-operator intelligence
  - Housekeeper reliability-verification direction
  - Investigator trust/avoid/watch classification direction
  - Prompt, persistence, and metrics recommendations

- [Intel Recommendation Activation and Notifications](/mnt/c/Meridinate/docs/architecture/INTEL_RECOMMENDATION_ACTIVATION_AND_NOTIFICATIONS.md)
  - How structured Intel recommendations should be reviewed
  - Per-action approval model
  - Immediate bot activation on approval
  - Logging, reversibility, and notification requirements

- [Intel Pipeline Optimization Audit](/mnt/c/Meridinate/docs/architecture/INTEL_PIPELINE_OPTIMIZATION_AUDIT.md)
  - Assessment of the current exported Intel pipeline behavior
  - What is already working well
  - What is still inefficient
  - Recommended next optimization package

- [Top PnL Forensics and Trail Analysis](/mnt/c/Meridinate/docs/architecture/TOP_PNL_FORENSICS_AND_TRAIL_ANALYSIS.md)
  - How Housekeeper and Investigator can be used beyond Full Scan
  - Forensic interpretation of top-PnL leaderboard outliers
  - Chart-nature classification and trail continuation analysis

- [Response to Bot Reverse Engineering Intel Mode](/mnt/c/Meridinate/docs/architecture/RESPONSE_TO_BOT_REVERSE_ENGINEERING_INTEL_MODE.md)
  - Review of the reverse-engineering mode proposal
  - Recommended ontology and classification refinements
  - Guidance for handling profitable but non-trustworthy bots like omego

- [Response to Deep Bot Probe Design](/mnt/c/Meridinate/docs/architecture/RESPONSE_TO_DEEP_BOT_PROBE_DESIGN.md)
  - Review of the full deep bot probe specification
  - Recommended forensic, storage, and ontology refinements
  - Guidance on uncertainty, accounting semantics, and coverage

## Current vs Approved Direction

Some docs in this directory describe:

- current implementation details
- approved product/architecture direction that is not yet fully implemented

Where that distinction matters, the docs call it out explicitly.
