# DOMAIN_SCHEMA.md
## Domain: Municipal Transit Incidents (DOMAIN_ID = 2)

### Entity: TransitIncident

| Field           | Type     | Required | Description                                      |
|-----------------|----------|----------|---------------------------------------------------|
| routeId         | text     | yes      | Route number or line name (e.g., "Line 22", "BART Red") — PRIMARY FIELD |
| location        | text     | yes      | Stop, station, or intersection where incident occurred — SECONDARY FIELD |
| reporterEmail   | email    | yes      | Email address of the person submitting the report |
| description     | textarea | yes      | Free-text description of what happened            |
| category        | dropdown | yes      | One of: Delay, Breakdown, Accident, Service Change |
| agreeToTerms    | checkbox | yes      | Submitter agrees to terms and conditions           |

### Category Values
- **Delay** — service running behind schedule
- **Breakdown** — vehicle/equipment mechanical failure
- **Accident** — collision or safety incident
- **Service Change** — route detour, cancellation, or schedule change
