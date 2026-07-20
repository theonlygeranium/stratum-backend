---
source_title: "STRATUM Intake Scoring Logic"
source_url: "STRATUM_BUILD_SPECS.md"
service_area: "ai_strategy"
content_type: "intake_logic"
freshness_date: "2026-07-19"
topics: "intake,readiness_snapshot,assessment,high_intent,canvas_usage,data_quality,engineering_capacity,timeline,success_metric"
---

# STRATUM Intake Scoring Logic

The intake flow assesses whether a visitor has a concrete AI or Canvas implementation opportunity. The fixed questions cover organization type, Canvas usage, problem to solve, current data quality, engineering capacity, timeline, and the six-month definition of success.

## Readiness Signals

High readiness appears when the visitor can name a workflow, data source, owner, target users, timeline, and success metric. Lower readiness appears when the visitor asks for generic AI adoption without a workflow, has unclear data access, lacks an integration path, or cannot describe the outcome they need.

## Capability Mapping

Canvas usage and LMS workflow answers map toward Canvas Integration or LTI Development. Knowledge base, hallucination, grounded response, and evaluation concerns map toward RAG Engineering. Roadmap, ROI, governance, vendor, or build-versus-buy concerns map toward AI Implementation Strategy. Reporting, learner events, and intervention signals map toward Learning Analytics.

## Escalation Signals

High-intent escalation is appropriate when the visitor has a near-term timeline, clear problem, institutional or product ownership, and a measurable pilot target. Confidence escalation is appropriate when retrieval cannot ground the answer in the knowledge base. Direct escalation is appropriate when the visitor asks to talk with the Founding leadership team, schedule a call, start a project, or get pricing.

## Snapshot Content

The readiness snapshot should synthesize the situation in plain language, identify the one or two most relevant EdStratum capabilities, and recommend a realistic first step. The snapshot should avoid promising a full build before discovery validates data, permissions, workflow fit, and evaluation criteria.
