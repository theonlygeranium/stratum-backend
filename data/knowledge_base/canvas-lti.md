---
source_title: "Canvas LTI and Developer Key Context"
source_url: "https://developerdocs.instructure.com/services/canvas/external-tools/lti/file.tools_intro"
service_area: "canvas"
content_type: "technical_doc"
freshness_date: "2026-07-19"
topics: "canvas,lti,lti_1_3,lti_advantage,developer_key,oauth,placements,gradebook,roster,canvas_data_2"
---

# Canvas LTI Integration Context

Canvas external tools use LTI placements as entry points into the learning platform. Placements determine where a tool is visible to users, such as course navigation, assignments, editor buttons, modules, homework submission flows, and assignment selection workflows.

For LTI Advantage and LTI 1.3 integrations, Canvas uses Developer Keys to store tool configuration. Tools need Canvas-specific settings to accept launches and use LTI Advantage services. A successful launch involves OpenID Connect login initiation, an authentication request, an authentication response containing a signed ID token, nonce and state validation, and resource display. Tools must verify that signed launch data comes from Canvas before trusting user, course, assignment, or role claims.

Canvas API work also relies on OAuth2 developer keys. Institution administrators issue developer keys for hosted Canvas environments. Scoped keys can limit access to specific API endpoints. Canvas REST API responses are JSON and API access should happen over HTTPS.

## LTI Advantage Services

The most common LTI Advantage services in EdTech product work are Deep Linking, Assignment and Grade Services, and Names and Role Provisioning Services. Deep Linking lets a tool return selected content or activities into Canvas. Assignment and Grade Services can support grade passback and line-item workflows. Names and Role Provisioning Services can support roster-aware experiences when the institution permits that access.

## Data and Permission Boundaries

Canvas integration discovery should identify the placement, user role, required claims, API scopes, gradebook or roster needs, and whether Canvas Data 2 is needed for reporting beyond real-time API calls. The integration plan should separate admin configuration, launch security, runtime API access, data retention, and observability.

## STRATUM Guidance

An EdStratum Canvas engagement should begin by identifying the placement, user role, data flow, permission boundary, and evaluation metric. AI is appropriate only when the workflow can be grounded in reliable Canvas data and a maintainable integration path.

Good first-fit Canvas questions include: Which workflow is blocked by the current LMS? Which users are affected? Does the tool need LTI launch data, REST API access, Canvas Data 2, or all three? Who owns Developer Key approval? What metric will prove that the integration improved the learning or operational workflow?
