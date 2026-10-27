---
name: n8n-linkedin-crm-sync
description: Sync LinkedIn Sales Navigator leads into HubSpot without duplicates - export a Sales Navigator search with Evaboot (once or every week), match each person to HubSpot by LinkedIn id then email, write a one-line opener and a fit for the new people, create the ones that fit, update the title and company of the ones that changed jobs, and leave known contacts alone. Use when the user asks to automate LinkedIn with n8n, sync Sales Navigator to HubSpot, add LinkedIn leads to the CRM, or catch job changes.
---

# LinkedIn to HubSpot sync

This skill runs inside a clone of https://github.com/evaboot-labs/n8n-linkedin-crm-sync: it uses the repo's `sync.py`, `BUYERS.md` and `docs/`. If `sync.py` is not in the working directory, clone the repo and work from there.

The Evaboot MCP server (`https://mcp.evaboot.com/mcp`) builds and exports the search. `sync.py` does every HubSpot call. You write the fit and the first line.

## Rules

- **You never contact anyone.** The first line is for the user's outreach.
- Confirm before `export_sn_search_or_list` and `create_recurring_export`: show the count and the cost (1 credit per lead).
- Write each note only from the person's row and `BUYERS.md`. Never invent a fact. Never guess gender.
- Nothing is written to HubSpot before the user reads `sync.py review` and says yes.

## Step 0: check the setup

1. If the Evaboot MCP tools are missing, or `.env` has no `HUBSPOT_TOKEN`, walk the user through `docs/connect-your-agent.md`.
2. Call `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to open any Sales Navigator search with the Evaboot extension and click Export with Evaboot.
3. HubSpot needs two contact properties: `ai_first_line` and `linkedin_change` (multi-line text). `docs/connect-your-agent.md` creates them; ask first.
4. Run `mkdir -p data queue` and read `BUYERS.md`. If it says `Status: EXAMPLE`, ask who the user sells to, rewrite it and set `Status: yours`.

## Step 1: the search

- Build it with `build_sn_search_from_prompt`, **people only** (roles, seniority, geography). Add industry and company size to the URL yourself: asking the builder for them starts a company-first search on a temporary company list, and Evaboot deletes that list after the first export, so the search cannot repeat.
- Save the search in Sales Navigator (the user clicks Save search), then export it with `export_sn_search_or_list` and `max_results`.
- Save the run: `curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<id>/ > data/run-$(date +%F).json`

## Step 2: match and note

```bash
python3 sync.py facts data/run-2026-10-27.json > queue/leads.json
python3 sync.py match queue/leads.json > queue/matched.json
```

Write `queue/notes.json` for every `new` person: `{"id", "fit": "good|maybe|no", "first_line", "reason"}` (`reason` only for a no).

```bash
python3 sync.py check queue/matched.json queue/notes.json
python3 sync.py review queue/matched.json queue/notes.json
```

## Step 3: write and repeat

On a yes: `python3 sync.py push queue/matched.json queue/notes.json --apply`.

Offer `create_recurring_export` (weekly) on the saved search's export, attached to the n8n workflow (`docs/n8n.md`): every run then syncs on its own, and only people new to the search are exported.
