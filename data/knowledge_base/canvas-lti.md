---
source_title: "Canvas LTI and Developer Key Context"
source_url: "https://developerdocs.instructure.com/services/canvas/external-tools/lti/file.tools_intro"
service_area: "canvas"
content_type: "technical_doc"
freshness_date: "2026-07-19"
topics: "canvas,lti,lti_1.3,lti_advantage,developer_key,oauth,placements,gradebook,roster,canvas_data_2,deep_linking,ags,nrps"
---

# Canvas LTI Integration Context

Canvas external tools use LTI placements as entry points into the learning platform. Placements determine where a tool is visible to users, such as course navigation, assignments, editor buttons, modules, homework submission flows, and assignment selection workflows.

## LTI 1.3 and LTI Advantage

For LTI Advantage and LTI 1.3 integrations, Canvas uses Developer Keys to store tool configuration. Tools need Canvas-specific settings to accept launches and use LTI Advantage services. A successful launch involves OpenID Connect login initiation, an authentication request, an authentication response containing a signed ID token, nonce and state validation, and resource display. Tools must verify that signed launch data comes from Canvas before trusting user, course, assignment, or role claims.

### LTI Advantage Services

The most common LTI Advantage services in EdTech product work are:

- **Deep Linking** — Lets a tool return selected content or activities into Canvas. Instructors can select specific resources from the tool and place them in modules, assignments, or pages.
- **Assignment and Grade Services (AGS)** — Supports grade passback and line-item workflows. Tools can create assignments, submit scores, and sync grades back to the Canvas gradebook.
- **Names and Role Provisioning Services (NRPS)** — Supports roster-aware experiences when the institution permits that access. Tools can retrieve the list of course members and their roles.

## Canvas API and OAuth2

Canvas API work relies on OAuth2 developer keys. Institution administrators issue developer keys for hosted Canvas environments. Scoped keys can limit access to specific API endpoints. Canvas REST API responses are JSON and API access should happen over HTTPS.

### Developer Key Configuration
Developer keys are issued by Canvas administrators at the institution level. They define the OAuth2 client credentials, redirect URIs, and API scopes. Scoped keys limit access to specific API endpoints, which is important for security in production integrations.

## Canvas Data 2

Canvas Data 2 is the reporting and analytics data pipeline for Canvas. It provides access to institutional data beyond what the real-time REST API offers. For reporting pipelines, learning analytics, or large-scale data extraction, Canvas Data 2 is the right tool. For real-time workflow automation, the REST API or LTI services are typically more appropriate.

## Data and Permission Boundaries

Canvas integration discovery should identify the placement, user role, required claims, API scopes, gradebook or roster needs, and whether Canvas Data 2 is needed for reporting beyond real-time API calls. The integration plan should separate admin configuration, launch security, runtime API access, data retention, and observability.

## STRATUM Guidance

An EdStratum Canvas engagement should begin by identifying the placement, user role, data flow, permission boundary, and evaluation metric. AI is appropriate only when the workflow can be grounded in reliable Canvas data and a maintainable integration path.

### Good First-Fit Canvas Questions
- Which workflow is blocked by the current LMS?
- Which users are affected?
- Does the tool need LTI launch data, REST API access, Canvas Data 2, or all three?
- Who owns Developer Key approval?
- What metric will prove that the integration improved the learning or operational workflow?

## What EdStratum Builds for Canvas

EdStratum builds custom LTI 1.3 tools, Canvas API workflows, gradebook automation, roster sync, SSO configuration, and Canvas Data 2 pipelines. The work covers the full integration lifecycle: placement design, Developer Key configuration, launch security, runtime API access, data pipelines, and operational handoff.
