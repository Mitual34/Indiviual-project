"""Builds docs/kyb-os-overview.md (images by relative path) and docs/kyb-os-overview.html (images embedded)."""
import base64, html, pathlib
H = pathlib.Path(__file__).parent
TITLE = "Inside KYB-OS: One Console for UK Business Due Diligence"
DEK = "A walk through the platform, tab by tab, from the first screening score to the registry lookup behind it."
META = "Platform · 19 November 2026 · 6 min read"
INTRO = [
 "Know-your-business work usually lives in a drawer of tools: a registry search in one window, a sanctions screen in another, a spreadsheet of who is waiting for review, and a model score nobody can trace. KYB-OS puts those steps in one console. Every view reads the same set of case records, so a flag raised on one tab shows up on the others, and a case moved in the pipeline changes the count on the dashboard.",
 "KYB-OS is a research prototype built for an individual project on UK KYB, KYC and AML screening. Everything on the demo screens runs over synthetic cases. None of it is customer data, and the scores show that the workflow runs, not how well anything performs on real companies.",
]
TABS_INTRO = ("One console, eight tabs", "The tabs follow the order of the work. Dashboard gives the overview. Map and Lookup answer where a company is and what the register says about it. Cases and Network carry the review itself. Models and Vault hold the evidence and the controls behind it, and Settings connects the platform to its data sources.")
TABS = [
 ("dashboard", "Dashboard", "What is waiting, and can the team clear it", "1-dashboard",
  "Dashboard. Review capacity, flag counts, the screening funnel, the riskiest cases and live signals.",
  ["The console opens on the question a team lead asks first. Of the 300 cases screened, how many need a person, and is that more than the team can review? A capacity bar sets 60 review slots against the queue, which here fills exactly: 5 cases to escalate, 15 for enhanced due diligence and 40 for review. Beside it sit the counts that drive the queue: 15 cases with a sanctions-proximity flag, 19 with a PEP flag, 53 with a jurisdiction flag and 49 with two or more late filings. Eight cases have no late-filing data and stay marked unknown, not zero.",
   "A nine-step funnel runs from intake to cleared, with the share that moves on at each step. The adverse-media step is greyed out and labelled not connected, because that source is not wired in yet. Below the funnel, the riskiest cases are listed by model score, and a signals panel turns the sharpest flags into alerts, such as a sanctions name hit that needs corroboration before anyone escalates it."]),
 ("map", "Map", "Where the cases sit, and who shares an address", "2-map",
  "Map. Local authority shading, risk-coloured pins, shared-address rings and a drawn selection area.",
  ["The map draws Great Britain's 380 local authority areas as vector shapes, shaded by how many cases each holds or by their average score. Pins are coloured by risk band and sized by score. Dashed rings mark registered offices shared by several companies, an old shell-company signal: in the demo, one address holds 25 companies.",
   "Filters narrow the view by score, stage and flag. The area tool lets the user drag a box and get the list of cases inside it, with their average score and a button that copies the IDs. Searching zooms to the matches, and a company checked on the Lookup tab appears as a diamond at its registered postcode.",
   "The locations in the demo are simulated, so the pattern tests the interface and carries no meaning. The boundary set covers Great Britain only; Northern Ireland is not included."]),
 ("cases", "Cases", "From screening to a decision", "3-cases",
  "Cases. Five stages from Screening to Cleared, with scores and flags on every card.",
  ["Cases move across five columns: Screening, Review, EDD, Decision and Cleared. Each card shows the model score, the company's sector, status and authority, and its flags as chips. Buttons move a case one stage forward or back, open its ownership network, or show it on the map.",
   "Stages come from the logistic regression ranking on the synthetic holdout. The top five cases sit in Decision, the next fifteen in EDD, the next forty in Review, fifty in Screening and the remaining 190 in Cleared. Moves are kept in the browser only, and each one is written to the audit trail on the Vault tab."]),
 ("lookup", "Lookup", "One company, checked live", "4-lookup",
  "Lookup. Registry facts, model features and flags for one company. The screen shows a fictional demonstration company.",
  ["The Lookup tab is where the platform meets the real register. Entering a company number, or part of a name, calls Companies House through the local server and returns the features the model uses: age, late filings in the last three years, officer changes in the last twelve months, and flags for jurisdiction, sanctions proximity and PEP status. Officers and persons with significant control are listed below.",
   "One rule runs through the tab. A source that is not loaded leaves its flag as unknown, never clear, and a name-only match against a sanctions or PEP list stays an unresolved candidate until an identifier, a country or a birth year backs it up. A Show on map button places the company at its registered postcode. Live lookups need the local server and a Companies House key."]),
 ("network", "Network", "Who owns and runs the company", "5-network",
  "Network. The company at the centre, with officers, controllers, a corporate owner and flagged entities around it.",
  ["For any case, the Network tab draws the company at the centre with its officers, people with significant control and corporate owner around it. A jurisdiction flag adds a node for a policy-listed country, and a sanctions flag adds a sanctions-list entity two steps out. Clicking a node opens its evidence: where the data comes from, whether a match is corroborated and which rule decided it.",
   "In the demo the links are generated from each case's flags, so they illustrate the view and are not ownership data. With live data the same picture would be drawn from Companies House control records and, where they exist, parent links from the LEI register."]),
 ("models", "Models", "Which scoring method deserves trust", "6-models",
  "Models. Holdout average precision for five methods, and five checks against a published review.",
  ["Five methods are scored on the same 300 held-out cases: a rules scorecard, logistic regression, an explainable boosting machine, a random forest and gradient boosting. On average precision, logistic regression leads at 0.308, against 0.247 for the rules and 0.137 for a random ranking. The tab then says what that does not show. Every confidence interval for the gap to the rules includes zero, because the holdout has only 41 true cases, so no model has been shown to beat the rules.",
   "A second panel tests five recommendations from a published review of machine learning for anti-money laundering. Accuracy is a poor measure here, since a model that flags nothing scores 86.3 percent. The interpretable and post-hoc explanations rank features in close agreement. And the models rank cases usably, but their probabilities are not usable: they predict a 27 percent risk where the observed rate is 13.7 percent."]),
 ("vault", "Vault", "Sources, scopes and the audit trail", "7-vault",
  "Vault. The source registry, the access-scope switch and the audit trail.",
  ["Vault holds three things. The first is the source registry: 21 UK and global data sources, each marked implemented, planned, manual, deferred or excluded, with what it feeds and what its access terms look like. Six are implemented today.",
   "The second is the access-scope switch. Choosing Partner or Regulator masks company names in every view, a demonstration of how each audience would see its own slice. The third is the audit trail, which records exports, stage changes, scope changes, area queries, live lookups and settings changes. In this prototype the scope switch is a display control, and the server does not enforce it."]),
 ("config", "Settings", "Keys and reference lists, kept local", "8-settings",
  "Settings. API keys, reference-list paths and options, with a plain-language connection test.",
  ["Settings connects the platform to the outside world. The user pastes a Companies House API key and presses Save and test, and the page answers in plain language: connected, or the reason it is not, such as a key with stray spaces, a stream key where a REST key is needed, or a blocked IP address. An optional OpenCorporates token sits below it, followed by paths to the sanctions, PEP and jurisdiction-policy files.",
   "Keys go only to the local server. They stay in its memory, never travel back to the page, and show afterwards as the last four characters. A Remember option writes them to a plain-text file on the user's own computer, and Forget everything removes the keys, the paths and that file."]),
]
OUTRO = [
 ("Why it exists", ["Because every tab reads the same records, the dashboard, the map and the pipeline cannot drift apart. The research behind the prototype points the same way. A published review of machine learning for anti-money laundering splits the field into client risk profiling and suspicious-behaviour flagging, and a scan of six vendors' public pages found their screening and onboarding tools leaning on configurable rules, with machine learning appearing mostly where the data is images or text. KYB-OS puts a transparent rules baseline and four learned models side by side, so the gain, or the lack of one, is visible."]),
 ("What it is, and is not", ["KYB-OS is a research prototype. Every case on the demo screens is synthetic, the map locations and ownership links are simulated, and the scores show that the workflow runs, not how it would perform on real companies. The Companies House, OpenCorporates and postcode calls have not been run against the live services in this build, and 10 of the 21 listed sources are planned and have no code yet. Northern Ireland is missing from the map.",
  "To run it, install the requests package, start the local server with python ui/serve.py, and open Settings to add a Companies House key."]),
]
e = html.escape
# ---- markdown
md = [f"# {TITLE}", "", f"*{DEK}*", "", META, ""] + [p + "\n" for p in INTRO] + [f"## {TABS_INTRO[0]}", "", TABS_INTRO[1], ""]
for _, name, head, img, cap, paras in TABS:
    md += [f"## {name}: {head}", "", f"![{cap}](img/{img}.jpg)", f"*{cap}*", ""] + [p + "\n" for p in paras]
for h, ps in OUTRO: md += [f"## {h}", ""] + [p + "\n" for p in ps]
(H / "kyb-os-overview.md").write_text("\n".join(md), encoding="utf-8")
# ---- html
def b64(n): return "data:image/jpeg;base64," + base64.b64encode((H / "img" / f"{n}.jpg").read_bytes()).decode()
body = [f'<p class="kick">{e(META)}</p><h1>{e(TITLE)}</h1><p class="dek">{e(DEK)}</p>'] + [f"<p>{e(p)}</p>" for p in INTRO]
body.append(f'<h2 class="sec">{e(TABS_INTRO[0])}</h2><p>{e(TABS_INTRO[1])}</p><nav class="tabs" aria-label="Tabs">' + "".join(f'<a href="#tab-{k}">{e(n)}</a>' for k, n, *_ in TABS) + "</nav>")
for k, name, head, img, cap, paras in TABS:
    body.append(f'<section id="tab-{k}"><p class="lab">{e(name)}</p><h2>{e(head)}</h2>' + "".join(f"<p>{e(p)}</p>" for p in paras[:1]) +
                f'<figure><img src="{b64(img)}" alt="{e(cap)}" loading="lazy"><figcaption>{e(cap)}</figcaption></figure>' + "".join(f"<p>{e(p)}</p>" for p in paras[1:]) + "</section>")
for h, ps in OUTRO: body.append(f'<section><h2 class="sec">{e(h)}</h2>' + "".join(f"<p>{e(p)}</p>" for p in ps) + "</section>")
page = """<title>Inside KYB-OS</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">
<style>
/* Concept: a long-form article in the console's own voice. Paper ground, serif body, terracotta for links and labels, one wide figure per tab. */
:root{--bg:#fbf9f6;--panel:#fffefc;--line:#e5dcd1;--fg:#201b17;--muted:#6c6158;--accent:#b04a27;--accent-soft:#f7e4dc;--serif:'Source Serif 4',Georgia,'Times New Roman',serif;--mono:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#171310;--panel:#1f1a16;--line:#3c332b;--fg:#f2ebe3;--muted:#a99d91;--accent:#e98a65;--accent-soft:#3d241b;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#171310;--panel:#1f1a16;--line:#3c332b;--fg:#f2ebe3;--muted:#a99d91;--accent:#e98a65;--accent-soft:#3d241b;color-scheme:dark}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.62 var(--serif);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:48px 80px}
main{max-width:720px;margin:0 auto} .kick,.lab{font:500 11.5px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
h1{font:600 clamp(30px,5vw,44px)/1.12 var(--serif);letter-spacing:-.015em;margin:0 0 14px;text-wrap:balance} .dek{font-size:21px;line-height:1.45;color:var(--muted);margin:0 0 28px}
h2{font:600 26px/1.25 var(--serif);margin:0 0 12px;text-wrap:balance} h2.sec{margin-top:44px} section{margin-top:56px;padding-top:28px;border-top:1px solid var(--line)} p{margin:0 0 18px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 8px} .tabs a{font:500 12px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--fg);text-decoration:none;border:1px solid var(--line);background:var(--panel);padding:6px 11px;border-radius:3px} .tabs a:hover{border-color:var(--accent);color:var(--accent)}
figure{margin:24px 0 8px;min-width:0} figure img{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:3px;background:var(--panel)} figcaption{font:italic 15px/1.45 var(--serif);color:var(--muted);margin-top:10px}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
</style>
<main>""" + "".join(body) + "</main>\n"
(H / "kyb-os-overview.html").write_text(page, encoding="utf-8")
print("md words:", len(" ".join(md).split()), "| html KB:", len(page) // 1024)
