# Run it in n8n

[`n8n/n8n-linkedin-crm-sync.json`](../n8n/n8n-linkedin-crm-sync.json) is the sync for n8n. Evaboot runs your Sales Navigator search every week and posts the new people to the webhook; the workflow sorts them and updates HubSpot.

## What runs

1. **New people from Evaboot** (Webhook) and **Settings** (who fits).
2. **One item per person**: one item per LinkedIn id.
3. **Find by LinkedIn id** and **Find by email**: two HubSpot searches, one call each.
4. **New, changed or known**: the LinkedIn id first, then the email. Changed = same person, another title or company.
5. **Is new**, then **Fit and first line** (Claude), **Build the new contacts** and **Create in HubSpot**: the people who fit are created with their first line, an email only when Evaboot rates it safe.
6. **Has changed**, then **Update title and company**: the new title and company, and `linkedin_change` records what they were.

Known people go nowhere: nothing is written for them.

## Set it up

1. **Create two contact properties in HubSpot:** `ai_first_line` and `linkedin_change` (multi-line text).
2. **Import** the JSON in n8n: *Workflows > Import from file*.
3. **Add two credentials:** **HubSpot Service Key** on the three HubSpot nodes (a private app or service key with contact read and write), and **Anthropic** on the Claude node.
4. **Fill in Settings:** `buyers`, who fits for you.
5. **Publish** the workflow. Open **New people from Evaboot** and copy its production URL. It looks like `https://<you>.app.n8n.cloud/webhook/evaboot-linkedin-sync`.
6. **Connect Evaboot,** from your AI Agent with the Evaboot MCP, or in Evaboot's Integrations page: add an n8n destination with that URL.
7. **Make the search repeat:** save your Sales Navigator search, export it once with Evaboot, then create a weekly recurring export and attach it to the n8n destination.
8. **Test:** push the first export to the destination (no credits), then open HubSpot.

## Good to know

- A search built on a temporary company list (what Evaboot's search builder does when you ask for an industry or a company size) cannot repeat: the list is deleted after the first export. Save a plain search instead.
- Pushing the same run twice creates nothing the second time: everyone is known.
- HubSpot's search can take a minute to see a contact created a moment ago.

Back to the [README](../README.md).
