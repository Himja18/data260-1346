# Part 3.1 - Tool contracts and the Part 2B rejected calls

All three tools return the same envelope `{ok, data, error}`. A rejected call is still a
successful MCP call (the Inspector shows *Tool Result: Success*); the rejection is
carried inside the envelope as `ok: false` with a message naming the broken rule.

## search_incidents

**Expected input schema**
```json
{
  "type": "object",
  "properties": {
    "category": {
      "type": "string",
      "enum": [
        "Delay",
        "Breakdown",
        "Accident",
        "Service Change"
      ]
    },
    "line_code": {
      "type": "string",
      "pattern": "^L-\\d{3}$"
    },
    "text": {
      "type": "string",
      "minLength": 2,
      "maxLength": 100
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50,
      "default": 10
    }
  },
  "additionalProperties": false
}
```

**Rejected input**
```json
{"category": "Flood", "limit": 10}
```

**Returned output**
```json
{
  "ok": false,
  "data": null,
  "error": "invalid input: category must be one of ['Delay', 'Breakdown', 'Accident', 'Service Change'], got 'Flood'"
}
```

**Why it was rejected:** `category` is an enum. 'Flood' is not one of Delay / Breakdown / Accident / Service Change, so validation rejects it before any query runs.

## get_incident

**Expected input schema**
```json
{
  "type": "object",
  "properties": {
    "incident_code": {
      "type": "string",
      "pattern": "^INC-\\d{6}$"
    }
  },
  "required": [
    "incident_code"
  ],
  "additionalProperties": false
}
```

**Rejected input**
```json
{"incident_code": "INC-12"}
```

**Returned output**
```json
{
  "ok": false,
  "data": null,
  "error": "invalid input: incident_code must look like 'INC-000123' (pattern ^INC-\\d{6}$), got 'INC-12'"
}
```

**Why it was rejected:** `incident_code` must match ^INC-\d{6}$ (six digits). 'INC-12' has two, so it fails the format check; the database is never queried.

## incident_stats

**Expected input schema**
```json
{
  "type": "object",
  "properties": {
    "line_code": {
      "type": "string",
      "pattern": "^L-\\d{3}$"
    }
  },
  "additionalProperties": false
}
```

**Rejected input**
```json
{"line_code": "Line5"}
```

**Returned output**
```json
{
  "ok": false,
  "data": null,
  "error": "invalid input: line_code must look like 'L-005' (pattern ^L-\\d{3}$), got 'Line5'"
}
```

**Why it was rejected:** `line_code` must match ^L-\d{3}$. 'Line5' is a free-text name, not a line code, so the pattern check rejects it.
