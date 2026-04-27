# NetSuite JE Schema

The customer's JE form configuration determines which fields are mandatory.
Tiers activate based on their NetSuite setup.

## Tier 1 — Core (minimum viable)

| Field | Level | Notes |
|-------|-------|-------|
| External ID | Header | Groups lines into one JE |
| Date | Header | Transaction date. Never omit |
| Account | Line | If "Use Account Numbers" is on: `11000 Accounts Payable` or `11000`. Must match exact capitalization |
| Debit | Line | Max 10 digits + 2 decimal. Populate DR OR CR, never both |
| Credit | Line | Same format. Min 2 lines with balancing DR/CR |

## Tier 2 — OneWorld & Multi-Currency

| Field | Level | Notes |
|-------|-------|-------|
| Subsidiary | Header | Required for OneWorld. Must match Setup > Company > Subsidiaries |
| Currency | Header | Required if multi-currency. Defaults to subsidiary base if omitted |
| Exchange Rate | Header | Defaults to 1.00 if omitted |
| To Subsidiary | Header | Intercompany only. IC JEs need min 4 lines |
| Line Subsidiary | Line | Intercompany only. Must match Subsidiary or To Subsidiary |

## Tier 3 — Classification Segments (form-dependent)

Header OR line level based on customer preference.

| Field | Level | Notes |
|-------|-------|-------|
| Department | Header or Line | Full hierarchy: `500 S&M : 520 Sales : 5201 AEs` |
| Class | Header or Line | Must match Setup > Company > Classes |
| Location | Line | Must match Setup > Company > Locations |

## Tier 4 — Optional (always include Memo)

| Field | Level | Notes |
|-------|-------|-------|
| Memo | Header | 999 chars. JE description |
| Memo | Line | 4000 chars. Line detail |
| Reversal Date | Header | Auto-reversal for accruals |
| Approved | Header | Boolean. Needs Journal Approval permission |
| Name | Line | Associated vendor/employee |

## CSV column naming

NetSuite CSV import uses prefixed names:
- Header fields: plain name (`External ID`, `Subsidiary`)
- Line fields: `Journal Entry -Line:` prefix (`Journal Entry -Line: Account`)
- IC line fields: `Intercompany Journal Entry -Line:` prefix

Use exact prefixes for CSV output.
