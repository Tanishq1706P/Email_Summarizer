# MongoDB Schema — Email Summarizer

**Database:** `email_summarizer`

---

## 1. `emails` — Raw email documents

```json
{
  "_id":      "ObjectId",
  "id":       "string (UUID)",
  "text":     "string (extracted plain text, max 50k chars)",
  "raw":      "string (original MIME content, optional)",
  "user_id":  "string (optional)",
  "metadata": {
    "subject":  "string",
    "has_raw":  true
  },
  "summary_result": {
    "session_id":       "UUID",
    "email_id":         "string",
    "user_id":          "string",
    "type":             "string",
    "category":         "Work | Personal | Newsletter | Finance | HR | Other",
    "subject":          "string",
    "summary":          "string",
    "action_items":     [{ "action": "...", "owner": "...", "deadline": "..." }],
    "open_questions":   ["string"],
    "priority":         "Urgent | Important | Normal | Low",
    "urgency":          "string",
    "sentiment":        "string",
    "key_details":      { "dates": [], "amounts": [], "ids_and_references": [], "attachments": [] },
    "key_entities":     { "people": [], "organizations": [], "dates": [] },
    "type_enrichment":  {},
    "flags":            { "confidential": false, "context_gap": false, "context_gap_note": null, "multilingual": null, "attachments_unretrieved": [] },
    "confidence":       0.0,
    "eval":             { "passed": true, "skipped": true },
    "pipeline":         { "latency_ms": 0.0, "learned_rules": 0, "eval_skipped": true }
  },
  "updated_at": "ISODate (set on update)"
}
```

---

## 2. `summaries` — Processed email summaries

Populated by `/summarize` and `/batch_summarize` endpoints. Keyed by email `id` (upsert).

```json
{
  "_id":        "ObjectId",
  "id":         "string (email ID, upsert key)",
  "summary_result": {
    "session_id":       "UUID",
    "email_id":         "string",
    "user_id":          "string",
    "type":             "string",
    "category":         "Work | Personal | Newsletter | Finance | HR | Other",
    "subject":          "string",
    "summary":          "string",
    "action_items":     [{ "action": "...", "owner": "...", "deadline": "..." }],
    "open_questions":   ["string"],
    "priority":         "Urgent | Important | Normal | Low",
    "urgency":          "string",
    "sentiment":        "string",
    "key_details":      { "dates": [], "amounts": [], "ids_and_references": [], "attachments": [] },
    "key_entities":     { "people": [], "organizations": [], "dates": [] },
    "type_enrichment":  {},
    "flags":            { "confidential": false, "context_gap": false, "context_gap_note": null, "multilingual": null, "attachments_unretrieved": [] },
    "confidence":       0.0,
    "eval":             { "passed": true, "skipped": true },
    "pipeline":         { "latency_ms": 0.0, "learned_rules": 0, "eval_skipped": true }
  },
  "updated_at": "ISODate (set on update)"
}
```

---

## 3. `sessions` — Summarization session records

```json
{
  "_id":              "ObjectId",
  "session_id":       "UUID (unique key)",
  "email_id":         "string",
  "email_type":       "string",
  "subject":          "string",
  "summary":          "string",
  "vector_embedding": "string (optional)",
  "priority":         "Urgent | Important | Normal | Low",
  "urgency":          "string",
  "sentiment":        "string",
  "confidence":       0.0,
  "eval": {
    "answer_relevance": 0.0,
    "faithfulness":     0.0,
    "overall":          0.0,
    "passed":           false,
    "issues":           []
  },
  "timestamp":        "ISO 8601 UTC string"
}
```

---

## 4. `feedback` — User feedback on summaries

```json
{
  "_id":              "ObjectId",
  "session_id":       "UUID",
  "email_type":       "string",
  "rating":           "int (1–5)",
  "correction":       "string (optional)",
  "missing_items":    ["string"],
  "tone_off":         false,
  "wrong_priority":   false,
  "wrong_type":       false,
  "note":             "string (optional)",
  "original_summary": "string",
  "timestamp":        "ISO 8601 UTC string"
}
```

---

## 5. `learned_rules` — Adaptive learning instructions

```json
{
  "_id":          "current",
  "instructions": "string (consolidated learned rules)",
  "updated_at":   "ISODate"
}
```

---

## 6. `stats` — Global counters

```json
{
  "_id":                 "global",
  "total_feedback":      0,
  "consolidation_count": 0
}
```

---

## Enum Values

| Field        | Allowed Values                                          |
|--------------|---------------------------------------------------------|
| `priority`   | `Urgent`, `Important`, `Normal`, `Low`                  |
| `category`   | `Work`, `Personal`, `Newsletter`, `Finance`, `HR`, `Other` |
