"""LinkedIn to HubSpot sync: new Sales Navigator leads in, duplicates out, job changes caught, a first line added.

    python3 sync.py facts data/run.json > queue/leads.json
        one row per person from an Evaboot export (a recurring run of your Sales Navigator search)
    python3 sync.py match queue/leads.json > queue/matched.json
        looks each person up in HubSpot by LinkedIn id, then by email: new, unchanged or changed
    python3 sync.py check queue/matched.json queue/notes.json
        your agent's fit and first line for every new person
    python3 sync.py review queue/matched.json queue/notes.json
        what will be created and updated in HubSpot
    python3 sync.py push queue/matched.json queue/notes.json [--apply]
        creates the new contacts, updates the changed ones; dry run unless --apply

Needs HUBSPOT_TOKEN in the environment or in .env (the Evaboot export is read from a file). Python 3.9+.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

HUBSPOT = "https://api.hubapi.com/crm/v3/objects/contacts"
PROPS = ["firstname", "lastname", "email", "jobtitle", "company", "hs_linkedin_url", "linkedin_change"]
FITS = {"good", "maybe", "no"}
MAX_WORDS = 30
GENDERED = re.compile(r"\b(he|she|him|her|his|hers)\b", re.I)


def env(name):
    if os.environ.get(name):
        return os.environ[name]
    if os.path.exists(".env"):
        m = re.search(rf"^{name}=(.*)$", open(".env").read(), re.M)
        if m and m.group(1).strip():
            return m.group(1).strip().strip("'\"")
    sys.exit(f"{name} is missing: add it to .env")


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {env('HUBSPOT_TOKEN')}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def clean(v, n=200):
    return " ".join(str(v or "").split())[:n]


def facts(run_path):
    out, seen = [], set()
    for p in json.load(open(run_path)).get("prospects") or []:
        lid = p.get("Linkedin URL Unique ID") or ""
        if not lid or lid in seen:
            continue
        seen.add(lid)
        out.append({"id": lid, "first_name": p.get("First Name") or "", "last_name": p.get("Last Name") or "",
                    "title": clean(p.get("Current Job"), 120), "company": p.get("Company Name") or "",
                    "domain": p.get("Company Domain") or "", "employees": p.get("Company Employee Range") or "",
                    "growth_1y_pct": p.get("Company Employee Growth 1 Year (%)") or "",
                    "headline": clean(p.get("Profile Headline"), 160),
                    "company_description": clean(p.get("Company Description"), 300),
                    "email": p.get("Email") or "", "email_status": (p.get("Email Status") or "").lower(),
                    "linkedin": p.get("Linkedin URL Public") or ""})
    print(f"{len(out)} people in the run", file=sys.stderr)
    return out


def search(prop, values):
    found = {}
    for i in range(0, len(values), 100):
        chunk = values[i:i + 100]
        status, d = call("POST", f"{HUBSPOT}/search", {"limit": 100, "properties": PROPS, "filterGroups": [
            {"filters": [{"propertyName": prop, "operator": "IN", "values": chunk}]}]})
        if status != 200:
            sys.exit(f"HubSpot search failed ({status}): {d.get('message')}")
        for r in d.get("results", []):
            found[(r["properties"].get(prop) or "").lower()] = {"id": r["id"], **r["properties"]}
    return found


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def match(leads):
    """LinkedIn id first (it never changes), then email. Changed = same person, another title or company."""
    by_li = search("hs_linkedin_url", [l["id"] for l in leads])
    by_mail = search("email", [l["email"].lower() for l in leads if l["email"]])
    counts = {"new": 0, "unchanged": 0, "changed": 0}
    for l in leads:
        crm = by_li.get(l["id"].lower()) or (by_mail.get(l["email"].lower()) if l["email"] else None)
        if not crm:
            l["status"], l["crm"] = "new", None
        else:
            l["crm"] = crm
            moved = norm(crm.get("company")) != norm(l["company"]) or norm(crm.get("jobtitle")) != norm(l["title"])
            l["status"] = "changed" if moved and (crm.get("company") or crm.get("jobtitle")) else "unchanged"
        counts[l["status"]] += 1
    print(f"{len(leads)} people: {counts['new']} new, {counts['changed']} changed, {counts['unchanged']} already "
          "in HubSpot", file=sys.stderr)
    return leads


def load(matched_path, notes_path):
    return json.load(open(matched_path)), {n.get("id"): n for n in json.load(open(notes_path))}


def check(matched_path, notes_path):
    """Every new person gets a fit and a first line; nothing else needs a note."""
    leads, notes = load(matched_path, notes_path)
    problems = []
    for l in leads:
        if l["status"] != "new":
            continue
        who = f"{l['first_name']} {l['last_name']} ({l['company']})"
        n = notes.get(l["id"])
        if not n:
            problems.append(f"{who}: no note")
            continue
        if n.get("fit") not in FITS:
            problems.append(f"{who}: fit must be good, maybe or no")
        line = n.get("first_line") or ""
        if n.get("fit") != "no" and (not line or len(line.split()) > MAX_WORDS):
            problems.append(f"{who}: first line is missing or longer than {MAX_WORDS} words")
        if GENDERED.search(line):
            problems.append(f"{who}: first line guesses a gender, use the first name, they or the role")
    for nid in set(notes) - {l["id"] for l in leads}:
        problems.append(f"unknown person {nid}")
    return problems


def plan(matched_path, notes_path):
    """Creates for new people who fit (an email only when Evaboot rates it safe), updates for changed ones."""
    leads, notes = load(matched_path, notes_path)
    creates, updates = [], []
    for l in leads:
        n = notes.get(l["id"]) or {}
        if l["status"] == "new" and n.get("fit") in ("good", "maybe"):
            props = {"firstname": l["first_name"], "lastname": l["last_name"], "jobtitle": l["title"],
                     "company": l["company"], "hs_linkedin_url": l["id"], "ai_first_line": n.get("first_line", ""),
                     "linkedin_change": f"Added from Sales Navigator on {date.today().isoformat()}"}
            if l["domain"]:
                props["website"] = l["domain"]
            if l["email"] and l["email_status"] == "safe":
                props["email"] = l["email"]
            creates.append({"name": f"{l['first_name']} {l['last_name']}", "properties": props})
        elif l["status"] == "changed":
            crm = l["crm"]
            was = " at ".join(x for x in (crm.get("jobtitle"), crm.get("company")) if x)
            props = {"jobtitle": l["title"], "company": l["company"],
                     "linkedin_change": f"{date.today().isoformat()}: was {was or 'unknown'}, now {l['title']} at {l['company']}"}
            updates.append({"id": crm["id"], "name": f"{l['first_name']} {l['last_name']}", "properties": props})
    return creates, updates


def review(matched_path, notes_path):
    leads, notes = load(matched_path, notes_path)
    creates, updates = plan(matched_path, notes_path)
    skipped = [l for l in leads if l["status"] == "new" and (notes.get(l["id"]) or {}).get("fit") == "no"]
    lines = [f"create {len(creates)}, update {len(updates)}, skip {len(skipped)} not a fit, "
             f"{sum(l['status'] == 'unchanged' for l in leads)} already in HubSpot"]
    for c in creates:
        p = c["properties"]
        lines.append(f"+ {c['name']} | {p['jobtitle']} | {p['company']} | {'email' if 'email' in p else 'no safe email'}")
        lines.append(f"    {p['ai_first_line']}")
    for u in updates:
        lines.append(f"~ {u['name']} | {u['properties']['linkedin_change']}")
    for l in skipped:
        lines.append(f"- {l['first_name']} {l['last_name']} | {l['title']} | {(notes.get(l['id']) or {}).get('reason', 'not a fit')}")
    return "\n".join(lines) + "\n"


def push(matched_path, notes_path, apply):
    creates, updates = plan(matched_path, notes_path)
    if not apply:
        print(f"dry run: {len(creates)} to create, {len(updates)} to update. Add --apply to write them.")
        return
    made = 0
    if creates:
        status, d = call("POST", f"{HUBSPOT}/batch/create", {"inputs": [{"properties": c["properties"]} for c in creates]})
        if status not in (200, 201, 207):
            sys.exit(f"HubSpot create failed ({status}): {d.get('message')}")
        made = len(d.get("results", []))
    changed = 0
    if updates:
        status, d = call("POST", f"{HUBSPOT}/batch/update", {"inputs": [{"id": u["id"], "properties": u["properties"]} for u in updates]})
        if status not in (200, 207):
            sys.exit(f"HubSpot update failed ({status}): {d.get('message')}")
        changed = len(d.get("results", []))
    print(f"created {made} contacts, updated {changed}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("facts").add_argument("run")
    sub.add_parser("match").add_argument("leads")
    for name in ("check", "review", "push"):
        s = sub.add_parser(name)
        s.add_argument("matched")
        s.add_argument("notes")
        if name == "push":
            s.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.cmd == "facts":
        json.dump(facts(a.run), sys.stdout, indent=1, ensure_ascii=False); print()
    elif a.cmd == "match":
        json.dump(match(json.load(open(a.leads))), sys.stdout, indent=1, ensure_ascii=False); print()
    elif a.cmd == "check":
        problems = check(a.matched, a.notes)
        for p in problems:
            print("FAIL", p)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        sys.exit(1 if problems else 0)
    elif a.cmd == "review":
        sys.stdout.write(review(a.matched, a.notes))
    else:
        push(a.matched, a.notes, a.apply)


if __name__ == "__main__":
    main()
