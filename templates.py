"""
templates.py - the page templates people can start from.

Grey italic text in a template is a prompt. It disappears when you click it
and start typing. Anything left unfilled is exported as a hidden
<!-- TODO: ... --> note, never as visible text, and the Check panel lists it.
"""
import html as _html
import uuid


def _id():
    return uuid.uuid4().hex[:10]


def e(s):
    return _html.escape(s, quote=False)


# ------------------------------------------------------------ content helpers
def p(*parts):
    return "".join("<p>%s</p>" % x for x in parts)


def ph(*prompts):
    return "".join('<p data-ph="1">%s</p>' % e(x) for x in prompts)


def phi(prompt):
    return '<span data-ph="1">%s</span>' % e(prompt)


def ul(*items):
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % i for i in items)


def ul_ph(*prompts):
    return "<ul>%s</ul>" % "".join('<li data-ph="1">%s</li>' % e(x) for x in prompts)


def a(page, text=None):
    return '<a href="wiki:%s">%s</a>' % (e(page), e(text or page))


def pill(text, c="green"):
    return '<span data-pill="%s">%s</span>' % (c, e(text))


# ------------------------------------------------------------ block helpers
def blk(type_, **kw):
    d = {"id": _id(), "type": type_}
    d.update(kw)
    return d


def hero(kicker, sub, pills=()):
    return blk("hero", kicker=kicker, title="", sub=sub, pills=list(pills))


def card(html):
    return blk("card", html=html)


def h2(text, color="blue", prompt=False):
    b = blk("h2", text=text, color=color)
    if prompt:
        b["ph"] = {"text": True}
    return b


def h3(text, color="blue", prompt=False):
    b = blk("h3", text=text, color=color)
    if prompt:
        b["ph"] = {"text": True}
    return b


def text(html):
    return blk("text", html=html)


def step(html, color="blue", start=None):
    b = blk("step", html=html, color=color)
    if start:
        b["start"] = start
    return b


def steps(prompts, color="blue"):
    return [step(ph(x), color) for x in prompts]


def callout(kind, html, title="", title_prompt=False):
    b = blk("callout", kind=kind, title=title, html=html)
    if title_prompt:
        b["ph"] = {"title": True}
    return b


def table(rows, header=True, keyval=False, color="navy"):
    return blk("table", rows=[list(r) for r in rows], header=header, keyval=keyval, color=color)


def facts(rows):
    """Key facts table: [(label, prompt or html)]."""
    out = []
    for k, v in rows:
        out.append([e(k), v if v.startswith("<") else phi(v)])
    return table(out, header=False, keyval=True)


def cards(items, color="blue"):
    """items: (title, html) or (title, html, colour) or (title prompt, html, None, True)."""
    b = blk("cards", color=color, items=[])
    for n, it in enumerate(items):
        d = {"title": it[0], "html": it[1]}
        if len(it) > 2 and it[2]:
            d["color"] = it[2]
        if len(it) > 3 and it[3]:
            b.setdefault("ph", {})["items.%d.title" % n] = True
        b["items"].append(d)
    return b


def flow(stages, color="blue"):
    """stages: (title, [prompts]) or (title, [prompts], colour)."""
    b = blk("flow", color=color, stages=[])
    for st in stages:
        d = {"title": st[0], "html": ph(*st[1]) if st[1] else ""}
        if len(st) > 2 and st[2]:
            d["color"] = st[2]
        b["stages"].append(d)
    return b


def collapse(title, html, title_prompt=False, collapsed=True, color="navy"):
    b = blk("collapse", title=title, html=html, collapsed=collapsed, color=color)
    if title_prompt:
        b["ph"] = {"title": True}
    return b


def code(lang="sql", title="", body=""):
    return blk("code", lang=lang, title=title, code=body)


def image(caption=""):
    return blk("image", file="", full="", caption=caption)


def related(*prompts):
    return [h2("Related pages", "navy"), text(ul_ph(*(prompts or ("Link a related page",))))]


def owner():
    return [h2("Owner and last reviewed", "navy"),
            facts([("Owner", "Team or role title (not a person's name)"), ("Last reviewed", "Month and year")])]


# ------------------------------------------------------------ the templates
def t_blank():
    return []


def t_hub():
    return [
        hero("Your Team &middot; Topic hub", phi("One line on what this topic covers and who it is for."), ["Start here"]),
        card(ph("Two or three sentences: what this topic is, where its data comes from and what it is used for.")
             + p("<b>New to this topic?</b> Work through the cards below from left to right.")),
        h2("The pages in this set", "navy"),
        cards([("Understand it", ul_ph("Link the page that explains how it works")),
               ("Run it", ul_ph("Link the load procedure or runbook")),
               ("Check and fix it", ul_ph("Link the checks or troubleshooting page"))], "blue"),
        h2("How the pieces fit", "blue"),
        flow([("Source", ["Where the data starts"], "grey"), ("Load", ["How it gets in"], "blue"),
              ("Warehouse", ["Where it is stored"], "purple"), ("Reports", ["Who uses it"], "green")]),
        h2("Pages at a glance", "blue"),
        table([["Page", "What it covers", "Use it when"],
               [phi("Page name"), phi("One line"), phi("When someone needs it")],
               [phi("Page name"), phi("One line"), phi("When someone needs it")]]),
    ] + owner() + related()


def t_overview():
    return [
        hero("Your Team &middot; How it works", phi("One line on what this is and why it matters."), ["Overview"]),
        card(ph("What this is, in one short paragraph. Say who uses it and what decisions it supports.")),
        h2("At a glance", "blue"),
        facts([("Purpose", "What it is for"), ("Source system", "Where the data comes from"),
               ("Refresh", "How often it updates"), ("Main objects", "Key tables, views or apps"),
               ("Used by", "Reports or teams that rely on it"), ("Owner", "Team or role title")]),
        h2("How the data flows", "blue"),
        flow([("Source", ["System or file"], "grey"), ("Staging", ["Load step"], "blue"),
              ("Warehouse", ["Tables and views"], "purple"), ("Report", ["Dashboard or extract"], "green")]),
        image("Diagram of the data flow"),
        h2("Business rules", "purple"),
        text(ul_ph("A rule that changes the numbers, in plain words", "Where the rule lives (procedure or view name)")),
        h2("Known issues and limitations", "amber"),
        callout("warning", ph("Anything the reader must know before relying on the numbers.")),
    ] + related()


def t_runbook():
    return [
        hero("Your Team &middot; Data load", phi("Step-by-step load for this dataset: receive, load, publish and check."), ["Procedure", "Monthly"]),
        card(ph("What this load does and when it runs. Link the page that explains the data.")),
        h2("At a glance", "green"),
        facts([("Frequency", "Monthly, weekly or on request"), ("File arrives from", "Supplier team or system (no names)"),
               ("File name", "Exact file name or pattern"), ("Drop folder", "Folder path"),
               ("Jobs to run", "Agent jobs or packages, in order"), ("Time needed", "Rough time to complete"),
               ("Owner", "Team or role title")]),
        h2("Before you start", "amber"),
        callout("warning", ph("What must be true before you start, for example last month is published.")),
        text(ul_ph("Access you need", "Anything to check in the file first")),
        h2("Steps", "green"),
        h3("Prepare the file", "green"),
    ] + steps(["Receive the file. Say how it arrives and what it is called.", "Check the file matches the expected layout."], "green") + [
        h3("Load and publish", "green"),
    ] + steps(["Run the load job. Give its exact name.", "Check the job finished with no errors, then run the publish job."], "green") + [
        h3("Set the dates and refresh", "green"),
    ] + steps(["Update the latest data date and refresh the reports that use it."], "green") + [
        h2("Checks", "blue"),
        text(ph("What to run after the load to prove it worked.")),
        code("sql", "Check.sql", ""),
        table([["Check", "Expected result", "If it doesn't match"],
               [phi("What to look at"), phi("What good looks like"), phi("What to do")]], color="blue"),
        h2("If something goes wrong", "red"),
        table([["Problem", "What to do"], [phi("What you see"), phi("How to fix it, or who to raise it with")]], color="red"),
    ] + related()


def t_procedure():
    return [
        hero("Your Team &middot; Procedure", phi("One line on the change this procedure makes, and to what."), ["Procedure"]),
        card(ph("What this procedure changes and why it needs care.") + p("Work through the steps in order.")),
        h2("Pre-requisites", "blue"),
        card(ul_ph("Access you need (AD group or role)", "Approvals you need, by role")),
        h2("Before the change", "blue"),
    ] + steps(["Check the latest backup is available.", "Get approval from the roles listed above.",
               "Agree the day, time window and rollback plan with the people affected."], "blue") + [
        h2("Change steps", "green"),
    ] + steps(["First change step. Name the server or application.", "Next step.", "Confirm the change finished."], "green") + [
        h2("After the change", "purple"),
    ] + steps(["Check it works. Say exactly what to test.", "Tell the people affected that it is done."], "purple") + [
        h2("Rollback", "amber"),
        callout("warning", ph("When to roll back, and what it switches off while it runs.")),
    ] + steps(["First rollback step.", "Confirm the old version is back and working."], "amber") + [
        h2("Key considerations", "navy"),
        facts([("Outage expected?", "Yes or no, and for how long"), ("Rollback time", "Roughly how long"),
               ("Data at risk", "What could be lost if you roll back")]),
    ] + related()


def t_dbobjects():
    return [
        hero("Your Team &middot; Database objects", phi("Every table, view, procedure and job behind this dataset."), ["Reference"]),
        card(ph("Which database and server these live on, and how they connect.")),
        h2("Tables", "navy"),
        table([["Object", "Database", "What it holds", "Loaded by"], [phi("schema.table"), phi("Database"), phi("One line"), phi("Job or procedure")]]),
        h2("Views", "blue"),
        table([["View", "Reads from", "Used by"], [phi("schema.view"), phi("Tables"), phi("Report or app")]], color="blue"),
        h2("Stored procedures", "purple"),
        table([["Procedure", "What it does", "Called by"], [phi("schema.procedure"), phi("One line"), phi("Job or person")]], color="purple"),
        h2("Jobs and schedules", "green"),
        table([["Job", "Schedule", "Steps"], [phi("Agent job name"), phi("When it runs"), phi("What it runs")]], color="green"),
        h2("Useful queries", "blue"),
        callout("tip", p("Keep these read-only (SELECT only) so anyone can run them safely.")),
        code("sql", "Useful queries.sql", ""),
    ] + owner()


def t_checks():
    def check(n):
        return [
            h2("C%d – name this check" % n, "green", prompt=True),
            text(p("<b>What it checks:</b> " + phi("One or two sentences."))),
            code("sql", "C%d.sql" % n, ""),
            callout("tip", ph("The result you expect."), title="What good looks like."),
            text(p("<b>If it fails:</b> " + phi("What it usually means and what to do. Link the troubleshooting page."))),
        ]
    out = [
        hero("Your Team &middot; Checks", phi("Read-only checks to run after a load or when numbers look wrong."), ["Read-only checks"]),
        card(ph("When to run these checks and where (server and database).")),
        callout("tip", p("Every check here is read-only: SELECT statements only, so anyone can run them safely.")),
    ]
    return out + check(1) + check(2) + related()


def t_troubleshoot():
    return [
        hero("Your Team &middot; Troubleshooting", phi("What to do when this dataset or report looks wrong."), ["Troubleshooting"]),
        card(ph("Start with the quick reference. Each row points to the check that confirms it.")),
        h2("Quick reference", "red"),
        table([["What you see", "Likely cause", "What to do", "Related check"],
               [phi("Symptom"), phi("Cause"), phi("Fix"), phi("Check number")],
               [phi("Symptom"), phi("Cause"), phi("Fix"), phi("Check number")]], color="red"),
        h2("Problems in more detail", "amber"),
        collapse("Describe the problem", ph("What you see, why it happens and the steps to fix it."), title_prompt=True),
        collapse("Describe the problem", ph("What you see, why it happens and the steps to fix it."), title_prompt=True),
        h2("Still stuck?", "blue"),
        callout("note", ph("Who to raise it with (team or role), and what to include.")),
    ] + related()


def t_tool():
    return [
        hero("Your Team &middot; Tools", phi("What the tool does, in one line."), ["Tool"]),
        card(ph("What it is, who it is for and what problem it solves.", "Where it runs, and what it can and can't change.")),
        facts([("Purpose", "One line"), ("Current version", "Version and date"), ("Owner", "Team or role title"),
               ("Download", "Folder or library name (no sharing links)"), ("Runs on", "Where it runs"), ("Needs", "What has to be installed")]),
        h2("Quick start", "green"),
    ] + steps(["Get the tool. Say where from.", "Start it. Say exactly what to double-click or run.", "What you see first, and what to do next."], "green") + [
        h2("How it works", "blue"),
        flow([("Input", ["Where it reads from"], "grey"), ("The tool", ["What it does"], "blue"), ("Output", ["What you get"], "green")]),
        h2("Using it", "blue"),
        text(ph("The main things people do with it.")),
        image("Screenshot of the main screen"),
        h2("Troubleshooting", "amber"),
        table([["Problem", "What to do"], [phi("Message or symptom"), phi("Fix")]], color="amber"),
        h2("Versions and change log", "navy"),
        table([["Version", "Date", "Summary"], [phi("1.0"), phi("Date"), phi("What changed")]]),
        h2("Help and contact", "navy"),
        card(ph("Questions, problems or ideas: name the team and how to reach it (for example the team inbox).")),
    ]


def t_archive():
    return [
        hero("Your Team &middot; Archive", phi("Older notes kept for reference."), ["Archived", "Not current"]),
        callout("old", p("<b>Not current.</b> This page keeps older notes for reference.") + ph("Link the page that replaces it.")),
        h2("Why this is archived", "navy"),
        text(ph("What changed, and when.")),
        h2("Older notes", "navy"),
        collapse("Name this set of notes, e.g. design notes from a year", ph("Paste or summarise the older notes here."), title_prompt=True),
        callout("old", ph("Anything superseded that people still ask about.")),
    ]


def t_dataspec():
    return [
        hero("Your Team &middot; Data specification", phi("Fields, rules and quality checks for this dataset."), ["Data specification"]),
        card(ph("What the dataset is and what one row means.")),
        facts([("Dataset", "Name"), ("Source", "System or supplier"), ("Grain", "One row per ..."),
               ("Refresh", "How often"), ("Owner", "Team or role title"), ("Version", "Specification version and date")]),
        h2("Fields", "purple"),
        table([["Field", "Type", "Description", "Rules or allowed values"],
               [phi("FieldName"), phi("int, varchar(50) ..."), phi("What it holds"), phi("Rules")],
               [phi("FieldName"), phi("Type"), phi("What it holds"), phi("Rules")]], color="purple"),
        h2("Business rules", "blue"),
        text('<ol><li data-ph="1">First rule, in plain words</li><li data-ph="1">Next rule</li></ol>'),
        h2("Data quality", "green"),
        table([["Check", "Threshold", "What happens if it fails"], [phi("Check"), phi("Limit"), phi("Action")]], color="green"),
        h2("Change history", "navy"),
        table([["Date", "Change", "Changed by (role)"], [phi("Date"), phi("What changed"), phi("Role")]]),
    ]


def t_links():
    return [
        hero("Your Team &middot; Links", phi("The links the team uses every day, in one place."), ["Links"]),
        h2("Name this group of links", "blue", prompt=True),
        cards([("Name this card", ul_ph("Add a link", "Add a link"), None, True),
               ("Name this card", ul_ph("Add a link"), None, True),
               ("Name this card", ul_ph("Add a link"), None, True)], "blue"),
        h2("Name this group of links", "green", prompt=True),
        cards([("Name this card", ul_ph("Add a link"), None, True),
               ("Name this card", ul_ph("Add a link"), None, True)], "green"),
    ]


def t_process():
    return [
        hero("Your Team &middot; Team process", phi("How the team handles this kind of work."), ["Team process"]),
        card(ph("What this process covers and why it exists.")),
        h2("Who does what", "navy"),
        table([["Activity", "Responsible", "Accountable", "Consulted", "Informed"],
               [phi("Activity"), phi("Role"), phi("Role"), phi("Role"), phi("Role")],
               [phi("Activity"), phi("Role"), phi("Role"), phi("Role"), phi("Role")]]),
        h2("How it works", "blue"),
        flow([("Request arrives", ["Where from"], "grey"), ("Triage", ["Who looks at it"], "blue"),
              ("Do the work", ["Where it is tracked"], "purple"), ("Close", ["How it is closed"], "green")]),
        h2("Steps", "green"),
    ] + steps(["First step.", "Next step.", "How the work is closed off."], "green") + [
        h2("Service levels", "amber"),
        table([["Priority", "Response", "Resolution"], [phi("P1"), phi("Time"), phi("Time")]], color="amber"),
    ] + owner() + related()


# ---- knowledge base templates
def t_howto():
    return [
        hero("Knowledge base &middot; How-to", phi("What the reader will be able to do after reading this."), ["How-to"]),
        facts([("Applies to", "System, app or process"), ("Time needed", "About how long"),
               ("Access you need", "Role or group"), ("Owner", "Team or role title"), ("Last reviewed", "Month and year")]),
        h2("Before you start", "amber"),
        text(ul_ph("Something the reader needs first", "Something to check first")),
        h2("Steps", "green"),
    ] + steps(["First step. Start with a verb: Open, Run, Check.", "Next step. One action per step.",
               "Next step. Say what the reader should see.", "Last step."], "green") + [
        callout("tip", ph("How to tell it worked."), title="Check it worked."),
        h2("Frequently asked questions", "blue"),
        collapse("A question people often ask", ph("The answer, in a few sentences."), title_prompt=True, color="blue"),
        collapse("Another question", ph("The answer."), title_prompt=True, color="blue"),
    ] + related("Link a related article")


def t_troubleshoot_kb():
    return [
        hero("Knowledge base &middot; Troubleshooting", phi("Fix: describe the problem in the reader's words."), ["Troubleshooting"]),
        card(p("<b>Use this article when:</b>") + ul_ph("The symptom the reader sees", "Any other symptom")),
        h2("Symptoms", "red"),
        text(ul_ph("What the reader sees, in their words", "Where they see it")),
        h2("Error codes and messages", "amber"),
        table([["Error code or message", "What it means", "What to do"],
               [phi("Exact text of the error"), phi("Plain explanation"), phi("Fix, or which step to go to")],
               [phi("Exact text of the error"), phi("Plain explanation"), phi("Fix")]], color="amber"),
        h2("Diagnostic path", "blue"),
    ] + steps(["First thing to check. Say what to do if it passes and if it fails.",
               "Next check. If it fails, say which fix to use.",
               "Next check.", "If none of the checks found the problem, go to Still stuck."], "blue") + [
        h2("Known issues", "purple"),
        collapse("Name a known issue", ph("What causes it and the workaround."), title_prompt=True, color="purple"),
        h2("Still stuck?", "navy"),
        callout("note", p("Raise a fault in ServiceNow and include what you tried and any error messages.")
                + ph("Name the queue or assignment group to use.")),
    ] + related("Link a related article")


def t_known_error():
    return [
        hero("Knowledge base &middot; Known error", phi("Known error: describe the fault in one line."), ["Known error"]),
        facts([("Known error ID", "ID from ServiceNow"), ("Status", pill("Workaround available", "amber")),
               ("Affected service", "System or service"), ("First reported", "Date"),
               ("Problem record", "Problem number"), ("Owner", "Team or role title"), ("Last reviewed", "Date")]),
        h2("Symptoms", "red"),
        text(ul_ph("What users see", "When it happens")),
        h2("Cause", "purple"),
        text(ph("The root cause, if known. If not known yet, say so.")),
        h2("Workaround", "amber"),
        callout("warning", p("This keeps things running until the permanent fix is in place."), title="Temporary."),
    ] + steps(["First workaround step.", "Next step.", "How to confirm the workaround worked."], "amber") + [
        h2("Permanent fix", "green"),
        text(ph("What will fix it for good.")),
        table([["Change or release", "Planned date", "Status"], [phi("Change number"), phi("Date"), pill("Planned", "blue")]], color="green"),
        h2("Who is affected", "blue"),
        text(ph("Which users, sites or reports.")),
        h2("Change history", "navy"),
        table([["Date", "What changed"], [phi("Date"), phi("Created")]]),
    ]


def t_hr_hub():
    return [
        hero("Knowledge base &middot; People and culture", phi("Policies, benefits and onboarding guides for the team, in one place."),
             ["Policies", "Benefits", "Onboarding"]),
        card(p("Start with the area you need. Each card links to the articles in that area.")),
        callout("note", p("Keep personal details off these pages: no names, phone numbers or email addresses. Name the team or role to contact instead.")),
        h2("Browse by area", "purple"),
        cards([("Policies", ul_ph("Link a policy page", "Link a policy page")),
               ("Leave", ul_ph("Link a leave guide")),
               ("Pay and conditions", ul_ph("Link a pay or conditions page")),
               ("Benefits", ul_ph("Link a benefits page")),
               ("Onboarding", ul_ph("Link the onboarding guide")),
               ("Wellbeing", ul_ph("Link a wellbeing page"))], "purple"),
        h2("New starters", "green"),
    ] + steps(["Before day one: what happens and who arranges it (role).", "First day: what to expect.",
               "First week: accounts, access and training.", "First month: check-ins and next steps."], "green") + [
        h2("Popular articles", "blue"),
        table([["Article", "What it answers"], [phi("Link an article"), phi("The question it answers")],
               [phi("Link an article"), phi("The question it answers")]], color="blue"),
        h2("Need help?", "navy"),
        callout("note", ph("Name the team or role to contact, and how (team inbox or a ServiceNow request).")),
    ]


def t_writing():
    rows = [["Page type", "Use it for"]]
    for t in TEMPLATES:
        if t["id"] in ("blank", "writing"):
            continue
        rows.append([e(t["name"]), e(t["use"])])
    return [
        hero("Knowledge base &middot; Writing guidelines", "How we write and lay out pages so every article reads the same way.",
             ["Voice", "Layout", "Rules"]),
        card(p("These are the content patterns, voice and standards for our knowledge articles. They follow the %s." % a("Wiki Style Guide"))),
        h2("Voice and tone", "blue"),
        table([["Do", "Don't"],
               ["Write in plain words and short sentences.", "Use jargon or acronyms nobody has explained."],
               ["Spell out an acronym the first time you use it.", "Assume the reader knows the history."],
               ["Use descriptive link text.", "Write \"click here\"."],
               ["Say what is current: the environment and the date or version.", "Leave out which server or version you mean."],
               ["Name people by role title.", "Put people's names, phone numbers or email addresses on a page."]], color="blue"),
        h2("Page patterns", "purple"),
        text(p("Start every new page from the template that matches what it is for. They are all in the %s." % a("Wiki Style Tool"))),
        table(rows, color="purple"),
        h2("Building blocks", "green"),
        table([["Block", "Use it for"],
               ["Numbered steps", "Procedures. One action per step, starting with a verb."],
               ["Callouts", "<b>Note</b> for useful context, <b>Warning</b> for things that can go wrong, <b>Stop</b> for things that cause harm, <b>Tip</b> for good practice."],
               ["Table", "Lists of fields, jobs or servers. Keep to a few columns."],
               ["Code box", "SQL, commands and file paths."],
               ["Expandable section", "FAQs and long detail most readers can skip."],
               ["Picture", "700px wide or less, no width set, with a link to a full-size copy."]], color="green"),
        h2("Rules we always keep", "red"),
        text(ul("The first line is the hidden summary: the page title and one or two plain sentences.",
                "One clear, sentence-case title. No Test, Temp, New, Old, Copy or v2.",
                "At least one category, from the wiki's list.",
                "Never passwords, keys, tokens or connection strings with passwords. Say where the credential is held instead.",
                "No SharePoint sharing links. Name the library and folder instead.",
                "Use the contents box (__TOC__) on content pages.",
                "If something isn't known, leave a hidden TODO note. Don't guess.",
                "Link text and page titles are case sensitive.")),
        h2("Before you publish", "amber"),
    ] + [step(p(x), "amber") for x in [
        "Fill in or remove every grey prompt.",
        "Add the search summary and at least one category in the Page panel.",
        "Press Check and fix what it finds.",
        "Link the new page from at least one other page.",
        "Add the owner (role) and the month it was last reviewed.",
    ]] + [
        h2("Related pages", "navy"),
        text(ul(a("Wiki Style Guide"), a("Wiki page templates (modern layout)"), a("Wiki Style Tool"))),
    ]


def t_faq():
    return [
        hero("Knowledge base &middot; FAQ", phi("Answers to the questions people ask most about this topic."), ["FAQ"]),
        card(ph("What this FAQ covers. Click a question to see the answer.")),
        h2("Getting started", "blue"),
        collapse("A question", ph("The answer."), title_prompt=True, color="blue"),
        collapse("A question", ph("The answer."), title_prompt=True, color="blue"),
        h2("Access and permissions", "purple"),
        collapse("A question", ph("The answer."), title_prompt=True, color="purple"),
        collapse("A question", ph("The answer."), title_prompt=True, color="purple"),
        h2("Still have a question?", "navy"),
        callout("note", ph("Who to ask (team or role) and how.")),
    ]


def t_release():
    return [
        hero("Knowledge base &middot; What's new", phi("Changes to this system, newest first."), ["Release notes"]),
        card(ph("What these notes cover and how often they are updated.")),
        h2("Latest release", "green"),
        facts([("Version", "Version number"), ("Date", "Release date"), ("Status", pill("Released", "green"))]),
        table([["Change", "Type", "Who it affects"],
               [phi("What changed"), pill("New", "green"), phi("Users or teams")],
               [phi("What changed"), pill("Fixed", "blue"), phi("Users or teams")]], color="green"),
        h2("Earlier releases", "navy"),
        collapse("Version and date", ph("The changes in that release."), title_prompt=True),
    ]


TEMPLATES = [
    {"id": "blank", "group": "Start", "name": "Blank page", "colour": "grey", "icon": "□",
     "use": "Anything that doesn't fit a template.", "desc": "An empty page. Add blocks with the + button or by typing / in the page.",
     "categories": [], "build": t_blank},
    # Page types
    {"id": "hub", "group": "Page types", "name": "Topic hub", "colour": "navy", "icon": "◎",
     "use": "The start-here page for a set of pages.", "desc": "Cards for each part of the set, a flow of how the pieces fit, and a table of the pages. Like Sample Data Hub and PPH.",
     "categories": [], "build": t_hub},
    {"id": "overview", "group": "Page types", "name": "How it works", "colour": "blue", "icon": "⚙",
     "use": "Explaining a dataset, process or system.", "desc": "Key facts, a data flow, business rules and known issues. Like MOTT - How it works.",
     "categories": [], "build": t_overview},
    {"id": "runbook", "group": "Page types", "name": "Data load procedure", "colour": "green", "icon": "▶",
     "use": "Step-by-step loads and refreshes.", "desc": "Key facts, before you start, numbered steps in stages, checks and what to do if it fails.",
     "categories": ["Data Load Procedures"], "build": t_runbook},
    {"id": "procedure", "group": "Page types", "name": "Change or upgrade procedure", "colour": "purple", "icon": "⇅",
     "use": "Upgrades, changes and anything with a rollback.", "desc": "Pre-requisites, steps before, during and after the change, rollback and key considerations. Like the Power BI Gateway upgrade.",
     "categories": ["Platform and Access"], "build": t_procedure},
    {"id": "dbobjects", "group": "Page types", "name": "Database objects", "colour": "navy", "icon": "▦",
     "use": "Listing the tables, views, procedures and jobs behind something.", "desc": "One table per object type and a box of useful read-only queries. Like MOTT - Database objects.",
     "categories": ["ETL and Data Warehouse"], "build": t_dbobjects},
    {"id": "checks", "group": "Page types", "name": "Checks", "colour": "green", "icon": "✓",
     "use": "Read-only checks to run after a load.", "desc": "Numbered checks, each with what it checks, the query, what good looks like and what to do if it fails. Like MOTT - Checks.",
     "categories": [], "build": t_checks},
    {"id": "troubleshoot", "group": "Page types", "name": "Troubleshooting (by symptom)", "colour": "red", "icon": "⚠",
     "use": "When a dataset or report looks wrong.", "desc": "A quick-reference table from symptom to fix, with expandable detail. Like MOTT - Troubleshooting.",
     "categories": [], "build": t_troubleshoot},
    {"id": "tool", "group": "Page types", "name": "Tool or application", "colour": "blue", "icon": "⌘",
     "use": "A tool the team built or uses.", "desc": "Key facts, quick start, how it works, troubleshooting and versions.",
     "categories": [], "build": t_tool},
    {"id": "dataspec", "group": "Page types", "name": "Data specification", "colour": "purple", "icon": "≡",
     "use": "Fields, rules and quality checks for a dataset.", "desc": "Key facts, a field table, business rules, data quality and change history. Like PPH Data Specifications.",
     "categories": [], "build": t_dataspec},
    {"id": "process", "group": "Page types", "name": "Team process", "colour": "green", "icon": "⟳",
     "use": "How the team handles a kind of work.", "desc": "Who does what (RACI), the flow, the steps and service levels. Like the RACI and ServiceNow Queue Management pages.",
     "categories": ["Team Processes"], "build": t_process},
    {"id": "links", "group": "Page types", "name": "Useful links", "colour": "blue", "icon": "↗",
     "use": "A page of grouped links.", "desc": "Groups of link cards. Like Useful Links.",
     "categories": ["Platform and Access"], "build": t_links},
    {"id": "archive", "group": "Page types", "name": "Archive or superseded notes", "colour": "grey", "icon": "⌛",
     "use": "Keeping old notes without confusing anyone.", "desc": "A clear not-current banner, why it was archived, and the old notes folded away. Like MOTT - Archive.",
     "categories": [], "build": t_archive},
    # Knowledge base templates
    {"id": "howto", "group": "Knowledge base", "name": "How-to article", "colour": "green", "icon": "➜",
     "use": "Step-by-step instructions, runbooks and FAQs.", "desc": "Key facts, before you start, numbered steps, a check-it-worked tip and FAQs.",
     "categories": [], "build": t_howto},
    {"id": "troubleshoot-kb", "group": "Knowledge base", "name": "Troubleshooting article", "colour": "red", "icon": "✚",
     "use": "Known issues, error codes and a diagnostic path.", "desc": "Symptoms, an error code table, a step-by-step diagnostic path, known issues and where to go if still stuck.",
     "categories": [], "build": t_troubleshoot_kb},
    {"id": "known-error", "group": "Knowledge base", "name": "ITSM known error", "colour": "amber", "icon": "!",
     "use": "A known fault: the workaround now and the permanent fix later.", "desc": "Known error record with status, symptoms, cause, temporary workaround, permanent fix and change history.",
     "categories": [], "build": t_known_error},
    {"id": "hr-hub", "group": "Knowledge base", "name": "HR knowledge base hub", "colour": "purple", "icon": "♥",
     "use": "A central place for policies, benefits and onboarding guides.", "desc": "Cards for each area, new-starter steps, popular articles and who to ask.",
     "categories": ["Team Processes"], "build": t_hr_hub},
    {"id": "writing", "group": "Knowledge base", "name": "Writing guidelines", "colour": "navy", "icon": "✎",
     "use": "Your team's content patterns, voice and documentation standards.", "desc": "Voice and tone, page patterns, building blocks and the rules we always keep, filled in from the Wiki Style Guide.",
     "categories": ["Wiki Help"], "build": t_writing},
    {"id": "faq", "group": "Knowledge base", "name": "FAQ page", "colour": "blue", "icon": "?",
     "use": "Answers to common questions.", "desc": "Questions grouped under headings. Each answer folds away until clicked.",
     "categories": [], "build": t_faq},
    {"id": "release", "group": "Knowledge base", "name": "Release notes", "colour": "green", "icon": "★",
     "use": "What changed and when.", "desc": "The latest release with a table of changes, and earlier releases folded away.",
     "categories": [], "build": t_release},
]
BY_ID = {t["id"]: t for t in TEMPLATES}


def listing():
    return [{k: t[k] for k in ("id", "group", "name", "colour", "icon", "use", "desc", "categories")} for t in TEMPLATES]


def build(tid):
    t = BY_ID.get(tid)
    if not t:
        return None
    blocks = t["build"]()
    for b in blocks:
        if b["type"] == "hero":
            b["kicker"] = _html.unescape(b["kicker"])
    return {"title": "", "summary": "", "toc": True, "categories": list(t["categories"]),
            "template": tid, "blocks": blocks}
