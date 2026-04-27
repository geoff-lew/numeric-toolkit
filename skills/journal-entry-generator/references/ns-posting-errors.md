# NetSuite JE Posting Errors

Common errors when posting journal entries via `ns_createRecord` or CSV import,
with root causes and fixes. Consult this when a post fails in Phase 4.

## 1. "This record has been changed since the last update" / Concurrent modification

**Root cause:** Another user or process modified the record between read and write.
**Fix:** Retry the post. If it persists, check whether another integration is
touching the same External ID.

## 2. "Invalid account reference" / Account not found

**Root cause:** Account number or name doesn't match what's in NS. Common causes:
account was renamed, deactivated, or the "Use Account Numbers" preference was
toggled.
**Fix:** Run `SELECT id, acctnumber, isinactive FROM account WHERE acctnumber = '{code}'`
to verify. If inactive, ask user for replacement account. If name mismatch,
update COA cache in config.

## 3. "Please enter a value for Department/Class/Location"

**Root cause:** The JE form has a mandatory classification field that wasn't
populated on every line (or at header level).
**Fix:** Check config `form_required_fields`. Populate the missing field on all
lines. If the field requirement is new, update config.

## 4. "Transaction is not in balance"

**Root cause:** DR != CR at the entry level. Can happen due to floating-point
rounding in CSV generation, or a line was dropped during serialization.
**Fix:** Re-run `validate_je.py` to confirm balance. Check that CSV export
preserved all decimal places (NS needs exactly 2). Regenerate the entry.

## 5. "You cannot post to a closed period" / "Period is locked"

**Root cause:** The target accounting period has been closed or locked in NS.
**Fix:** Ask user whether to: (a) change the posting date to the current open
period, (b) request the period be re-opened, or (c) skip this entry.

## 6. "Duplicate External ID" / "A record with this External ID already exists"

**Root cause:** A transaction with the same External ID is already in NS.
**Fix:** Ask user whether to: skip (already posted), overwrite (re-post with
updated data), or generate a new External ID.

## 7. "Invalid subsidiary reference" / "Subsidiary does not exist"

**Root cause:** The subsidiary string doesn't exactly match NS. Common issues:
trailing spaces, wrong hierarchy separator (should be ` : `), or subsidiary
was renamed.
**Fix:** Run `SELECT id, name FROM subsidiary WHERE isinactive = 'F'` and
compare. Update subsidiary_map in config.

## 8. "You can only use one subsidiary for this transaction type"

**Root cause:** A standard (non-IC) JE has lines referencing multiple
subsidiaries.
**Fix:** Either split into separate JEs (one per subsidiary) or convert to an
intercompany JE with `To Subsidiary` and clearing account lines.

## 9. "This transaction requires approval"

**Root cause:** The JE form has an approval workflow enabled, and the posting
user doesn't have auto-approve permission.
**Fix:** Set `Approved` field to `F` (false) in the JE data — this creates the
entry in pending-approval status. Inform user that the JE needs manual approval
in NS. Alternatively, if user has approval rights, set to `T`.

## 10. "Currency mismatch" / "Exchange rate is required"

**Root cause:** The JE's currency doesn't match the subsidiary's base currency,
and no exchange rate was provided.
**Fix:** Add `Exchange Rate` field to the JE header. Pull rate from config or
ask user. If subsidiary is multi-currency, ensure `Currency` field is set.

## General troubleshooting

If the error message is opaque ("An error occurred during the request"):
1. Simplify: try posting a minimal 2-line JE (one DR, one CR) with only
   Tier 1 fields to isolate whether it's a field-level or structural issue.
2. Check permissions: the API user may lack the Journal Entry create permission
   for the target subsidiary.
3. Check for custom scripts: NS SuiteScript `beforeSubmit` or validation
   scripts can reject records with custom error messages. These are outside
   this skill's control — surface the raw error to the user.
