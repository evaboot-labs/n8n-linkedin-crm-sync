# Agent instructions

This repo syncs LinkedIn leads into HubSpot. Each run of the user's Sales Navigator search, exported by Evaboot, is matched against HubSpot by LinkedIn id and email: new people who fit get a one-line opener and are created, people whose title or company changed are updated, and everyone already known is left alone. When the user asks to automate LinkedIn leads into the CRM, sync Sales Navigator with HubSpot, or avoid duplicate contacts from LinkedIn:

1. Follow the skill in `skills/n8n-linkedin-crm-sync/SKILL.md` step by step.
2. Read `BUYERS.md` for who fits and the first-line rules. If it says `Status: EXAMPLE`, ask the user and update it.
3. Use `sync.py` for every HubSpot call. The Evaboot MCP server (`.mcp.json`) builds and exports the Sales Navigator search.
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
5. If the user wants n8n (the main use of this repo), follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Exports cost 1 Evaboot credit per lead. Confirm before every export and before creating a recurring export. Never write to HubSpot before the user has read `sync.py review` and said yes. Never contact anyone. Never ask for or handle a key: the user writes it into `.env`. Never commit `.env`, `data/` or `queue/`.
