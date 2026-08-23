# ResolveAI domain language

ResolveAI is a staff workspace for handling support tickets and producing
bounded, reviewable ticket summaries. This glossary keeps the product concepts
precise while implementation details stay in the architecture and workflow
documents.

## Ticket work

**Ticket**:
A support issue that staff members own, discuss, route, and resolve.
_Avoid_: Case, request, conversation (unless referring to a specific external system).

**Staff role**:
An application role that determines what a person may do with tickets,
settings, and administration.
_Avoid_: Permission (a permission is an individual capability, not the role itself).

**Analysis result**:
A reviewable summary produced for one ticket, with its lifecycle and origin
preserved for later inspection.
_Avoid_: AI answer, recommendation, classification (the current contract is summary-only).

## AI configuration

**Provider selection**:
The currently chosen AI provider and model for new analysis requests.
_Avoid_: Analyzer configuration (too broad; credentials and timeouts are not selected here).

**Analysis provenance**:
The provider, model, and prompt version associated with one analysis result.
It is part of that result's identity and does not change when the global
provider selection changes.
_Avoid_: Current provider (that refers only to the global selection).

**Provider test**:
A deliberate administrator check of a candidate provider/model using synthetic
input; it does not change the global provider selection or create a ticket
analysis result.
_Avoid_: Preview, dry run (those terms do not state the privacy and mutation guarantees).

**Synthetic verification**:
Testing with fabricated ticket content that contains no customer or private
operational data.
_Avoid_: Safe data (too vague to describe what is actually sent).
