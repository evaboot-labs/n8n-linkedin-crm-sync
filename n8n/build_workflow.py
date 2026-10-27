"""Builds n8n/n8n-linkedin-crm-sync.json. Run: python3 n8n/build_workflow.py

Evaboot runs your Sales Navigator search every week and posts the new people to the webhook. The workflow
looks each person up in HubSpot (LinkedIn id, then email), sends the new ones to Claude for a fit and a
first line, creates the ones that fit, updates the title and company of the ones that changed, and leaves
the rest alone. Same rules as sync.py.
"""
import json
import uuid
from pathlib import Path

ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
HUBSPOT_CRED = {"hubspotAppToken": {"id": "", "name": "HubSpot"}}
MODEL = "claude-sonnet-5-5"
PROPS = ["firstname", "lastname", "email", "jobtitle", "company", "hs_linkedin_url", "linkedin_change"]

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0, inp=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": inp})


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


def hubspot(name, method, url, body_expr, pos, **extra):
    node(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": method, "url": url, "authentication": "predefinedCredentialType",
        "nodeCredentialType": "hubspotAppToken", "sendBody": True, "specifyBody": "json", "jsonBody": body_expr,
        "options": {}}, pos, HUBSPOT_CRED, **extra)


PEOPLE_JS = r"""
// One item per person in the Evaboot run, keyed by the LinkedIn id that never changes.
const seen = new Set();
const words = (t, n) => String(t || '').split(/\s+/).join(' ').trim().slice(0, n);
return ($json.body.prospects || []).filter(p => {
  const id = p['Linkedin URL Unique ID'];
  if (!id || seen.has(id)) return false;
  seen.add(id); return true;
}).map(p => ({ json: {
  id: p['Linkedin URL Unique ID'], first_name: p['First Name'] || '', last_name: p['Last Name'] || '',
  title: words(p['Current Job'], 120), company: p['Company Name'] || '', domain: p['Company Domain'] || '',
  headline: words(p['Profile Headline'], 160), company_description: words(p['Company Description'], 300),
  email: p['Email'] || '', email_status: String(p['Email Status'] || '').toLowerCase(),
} }));
"""

MATCH_JS = r"""
// Same as sync.py match: LinkedIn id first, then email. Changed = same person, another title or company.
const byLi = {}, byMail = {};
for (const r of ($('Find by LinkedIn id').first().json.results || [])) byLi[String(r.properties.hs_linkedin_url || '').toLowerCase()] = r;
for (const r of ($('Find by email').first().json.results || [])) byMail[String(r.properties.email || '').toLowerCase()] = r;
const norm = s => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');
return $('One item per person').all().map(({ json: l }) => {
  const crm = byLi[l.id.toLowerCase()] || (l.email ? byMail[l.email.toLowerCase()] : null);
  if (!crm) return { json: { ...l, status: 'new' } };
  const p = crm.properties;
  const moved = (p.company || p.jobtitle) && (norm(p.company) !== norm(l.company) || norm(p.jobtitle) !== norm(l.title));
  return { json: { ...l, status: moved ? 'changed' : 'known', crm_id: crm.id, was: [p.jobtitle, p.company].filter(Boolean).join(' at ') } };
});
"""

CREATE_JS = r"""
// Same as sync.py plan: create the people who fit, with an email only when Evaboot rates it safe.
const notes = Object.fromEntries(($json.output.people || []).map(n => [n.id, n]));
const today = new Date().toISOString().slice(0, 10);
const out = [];
for (const { json: l } of $('Is new').all()) {
  const n = notes[l.id];
  if (!n || !['good', 'maybe'].includes(n.fit) || !n.first_line) continue;
  const properties = { firstname: l.first_name, lastname: l.last_name, jobtitle: l.title, company: l.company,
    hs_linkedin_url: l.id, ai_first_line: String(n.first_line).split(/\s+/).slice(0, 30).join(' '),
    linkedin_change: `Added from Sales Navigator on ${today}` };
  if (l.domain) properties.website = l.domain;
  if (l.email && l.email_status === 'safe') properties.email = l.email;
  out.push({ json: { properties } });
}
return out;
"""

NOTE_SYSTEM = """You add new LinkedIn leads to a CRM. For each person in the JSON (title, company, headline, company description), decide if they fit the buyers below and write one first line. Use only these facts; never invent anything.

Return {people: [{id, fit, first_line}]}:
- fit: good, maybe or no, from the buyers below. A no is not added to the CRM.
- first_line: one sentence under 30 words for the opening of a first email or a connection request, built only from their title, headline and company description.
- Never guess anyone's gender: no he, she, him or her. Use the first name, \"they\" or the role.

Buyers:
{{ $('Settings').first().json.buyers }}"""

node("New people from Evaboot", "n8n-nodes-base.webhook", 2, {
    "httpMethod": "POST", "path": "evaboot-linkedin-sync", "responseMode": "onReceived", "options": {},
}, [0, 0], webhookId=str(uuid.uuid4()))
node("Settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "buyers", "type": "string",
     "value": "good: people who lead or run sales, business development or growth (Heads, Directors, VPs, CROs) "
              "at B2B software companies of 51 to 5,000 employees. maybe: customer success or account management "
              "leaders. no: anyone else."}]},
    "includeOtherFields": True, "options": {}}, [200, 0])
code("One item per person", PEOPLE_JS, [400, 0])
hubspot("Find by LinkedIn id", "POST", "https://api.hubapi.com/crm/v3/objects/contacts/search",
        "={{ JSON.stringify({ limit: 100, properties: " + json.dumps(PROPS) + ", filterGroups: [{ filters: [{ "
        "propertyName: 'hs_linkedin_url', operator: 'IN', values: $input.all().map(i => i.json.id).slice(0, 100) }] }] }) }}",
        [600, 0], executeOnce=True)
hubspot("Find by email", "POST", "https://api.hubapi.com/crm/v3/objects/contacts/search",
        "={{ JSON.stringify({ limit: 100, properties: " + json.dumps(PROPS) + ", filterGroups: [{ filters: [{ "
        "propertyName: 'email', operator: 'IN', values: $('One item per person').all().map(i => i.json.email.toLowerCase()).filter(Boolean).slice(0, 100).concat(['-']) }] }] }) }}",
        [800, 0], executeOnce=True)
code("New, changed or known", MATCH_JS, [1000, 0], executeOnce=True)
node("Is new", "n8n-nodes-base.filter", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2}, "combinator": "and",
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.status }}", "rightValue": "new",
                    "operator": {"type": "string", "operation": "equals"}}]}, "options": {}}, [1220, -140])
node("Has changed", "n8n-nodes-base.filter", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2}, "combinator": "and",
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.status }}", "rightValue": "changed",
                    "operator": {"type": "string", "operation": "equals"}}]}, "options": {}}, [1220, 160])
node("Fit and first line", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "hasOutputParser": True,
    "text": "={{ JSON.stringify($input.all().map(i => ({ id: i.json.id, first_name: i.json.first_name, title: i.json.title, "
            "company: i.json.company, headline: i.json.headline, company_description: i.json.company_description }))) }}",
    "options": {"systemMessage": "=" + NOTE_SYSTEM, "maxIterations": 3},
}, [1460, -140], executeOnce=True, retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 4000},
}, [1420, 80], ANTHROPIC_CRED)
node("Notes", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["people"], "properties": {"people": {
        "type": "array", "items": {"type": "object", "required": ["id", "fit", "first_line"], "properties": {
            "id": {"type": "string"}, "fit": {"type": "string"}, "first_line": {"type": "string"}}}}}}, indent=2),
}, [1580, 80])
code("Build the new contacts", CREATE_JS, [1800, -140])
hubspot("Create in HubSpot", "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/create",
        "={{ JSON.stringify({ inputs: $input.all().map(i => ({ properties: i.json.properties })) }) }}",
        [2020, -140], executeOnce=True)
hubspot("Update title and company", "PATCH", "=https://api.hubapi.com/crm/v3/objects/contacts/{{ $json.crm_id }}",
        "={{ JSON.stringify({ properties: { jobtitle: $json.title, company: $json.company, linkedin_change: "
        "new Date().toISOString().slice(0, 10) + ': was ' + ($json.was || 'unknown') + ', now ' + $json.title + ' at ' + $json.company } }) }}",
        [1700, 200])

for a, b in [("New people from Evaboot", "Settings"), ("Settings", "One item per person"),
             ("One item per person", "Find by LinkedIn id"), ("Find by LinkedIn id", "Find by email"),
             ("Find by email", "New, changed or known"), ("New, changed or known", "Is new"),
             ("New, changed or known", "Has changed"), ("Is new", "Fit and first line"),
             ("Fit and first line", "Build the new contacts"), ("Build the new contacts", "Create in HubSpot"),
             ("Has changed", "Update title and company")]:
    link(a, b)
link("Claude", "Fit and first line", "ai_languageModel")
link("Notes", "Fit and first line", "ai_outputParser")

workflow = {"name": "LinkedIn to HubSpot sync (Evaboot + Claude)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("n8n-linkedin-crm-sync.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
