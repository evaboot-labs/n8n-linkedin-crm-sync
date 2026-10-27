# Connect your agent by hand

The prompt in the README does all of this for you. These are the same steps, for when you want to do them yourself.

1. **Create your Evaboot account** at [dash.evaboot.com](https://dash.evaboot.com/accounts/signup/?last_click_origin=n8n-linkedin-crm-sync-repo). Install the [Chrome extension](https://dash.evaboot.com/install/) and keep an active Sales Navigator seat.
2. **Get the repo:**
   ```bash
   git clone https://github.com/evaboot-labs/n8n-linkedin-crm-sync.git
   cd n8n-linkedin-crm-sync
   ```
3. **Add your keys.** Copy your Evaboot API key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). In HubSpot, create a private app or a service key with the scopes `crm.objects.contacts.read`, `crm.objects.contacts.write` and `crm.schemas.contacts.write`. Then:
   ```bash
   cp .env.example .env          # paste both keys
   ```
4. **Create the two HubSpot properties** the sync writes, once:
   ```bash
   set -a; . ./.env; set +a
   for p in ai_first_line:"AI first line" linkedin_change:"LinkedIn change"; do
     curl -s -X POST https://api.hubapi.com/crm/v3/properties/contacts -H "Authorization: Bearer $HUBSPOT_TOKEN" \
       -H 'Content-Type: application/json' \
       -d "{\"name\":\"${p%%:*}\",\"label\":\"${p#*:}\",\"type\":\"string\",\"fieldType\":\"textarea\",\"groupName\":\"contactinformation\"}"; echo; done
   ```
5. **Describe who fits** in [`BUYERS.md`](../BUYERS.md), or let your agent ask you.
6. **Check** (Python 3.9+, no packages to install): `python3 sync.py -h` lists the commands.

Then ask your agent: **"Sync my Sales Navigator search into HubSpot."**

Your agent uses the Evaboot MCP server (`https://mcp.evaboot.com/mcp`, in `.mcp.json`) to build and export the search. Export `EVABOOT_API_KEY` before you start Claude Code. For Codex: `codex mcp add evaboot --url https://mcp.evaboot.com/mcp --bearer-token-env-var EVABOOT_API_KEY`.

Back to the [README](../README.md).

