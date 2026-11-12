#!/usr/bin/env python3
"""
selftest.py - checks the Wiki Style Tool without a browser.

    python selftest.py        (Windows: py selftest.py)

It builds every template, turns each into wikitext, checks the wikitext against
the house rules, reads it back in and makes sure nothing changes. It then
starts the tool on a spare port and checks the web parts, including the
security checks. Nothing is left behind.
"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import doc_import  # noqa: E402
import exporter  # noqa: E402
import fake_wiki  # noqa: E402
import importer  # noqa: E402
import layout  # noqa: E402
import rich  # noqa: E402
import templates  # noqa: E402
import wiki_api  # noqa: E402
import wiki_lint  # noqa: E402
import wiki_style_tool as tool  # noqa: E402

PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok    " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  -> " + str(detail)[:300] if detail else ""))


def test_rich():
    print("Rich text to wikitext and back")
    samples = [
        '<p>Run <b>the job</b> then <i>check</i> <code>dbo.t[1]|x</code> and see <a href="wiki:Sample Data Hub">the hub</a>.</p>',
        '<ul><li>one<ul><li>two</li></ul></li><li data-ph="1">Add an item</li></ul><ol><li>first</li></ol>',
        '<p>Status <span data-pill="amber">In progress</span></p><p data-ph="1">Prompt</p>',
        '<p>* starts with a star &amp; has &lt;tags&gt; ~~~~ __TOC__</p>',
    ]
    for s in samples:
        w = rich.to_wiki(s)
        back = rich.to_wiki(rich.wiki_to_html(w))
        ok("round trip: " + s[:50], back == w, (w, back))
    ok("leading star is escaped", rich.to_wiki("<p>* not a list</p>").startswith("&#42;"))
    ok("prompt becomes a hidden TODO", rich.to_wiki('<p data-ph="1">Say what</p>') == "<!-- TODO: Say what -->")
    ok("magic words are neutralised", "__TOC__" not in rich.to_wiki("<p>__TOC__</p>"))


def test_regressions():
    print("Fixes from team feedback")
    ok("list items keep a leading or trailing B or R",
       rich.to_wiki("<ul><li>Run it</li><li>Build the DB</li></ul><ol><li>Review</li></ol>") == "* Run it\n* Build the DB\n\n# Review")
    h = rich.inline_to_html("<code><nowiki>Dim_Area</nowiki></code> and <nowiki>[[not a link]]</nowiki>")
    ok("<nowiki> inside code reads as plain code", h.startswith("<code>Dim_Area</code>") and "nowiki" not in h, h)
    ok("<nowiki> text stays text on export", "[[not a link]]" not in rich.to_inline(h), rich.to_inline(h))
    ok("<DATA_NAME> style placeholders are text, not tags", rich.plain(rich.inline_to_html("Run <DATA_NAME> now")) == "Run <DATA_NAME> now")
    ok("a shown <!-- TODO --> example is text", "TODO" in rich.plain(rich.inline_to_html("<code><nowiki><!-- TODO --></nowiki></code>")))
    d = importer.import_wiki('<div style="display:none">T. s</div>\n__TOC__\n<h3 style="x">Only sub-headings</h3>\n\nText.\n\n[[Category:Wiki Help]]\n')
    ok("contents box goes before the first sub-heading when there are no sections", "__TOC__\n<h3" in exporter.export(d)[0])
    d = importer.import_wiki('<div style="display:none">T. s</div>\n== One ==\nText.\n')
    ok("a page without __TOC__ does not gain one when opened and exported", "__TOC__" not in exporter.export(d)[0] and d["toc"] is None)
    fig = ('<div style="display:none">T. s</div>\n<div style="max-width:710px;margin:.4em 0 .2em;">[[File:A.png|A.png]]</div>\n'
           '<div style="background:#fff;border:1px solid #dfe3e7;border-radius:6px;padding:.9em 1.2em;margin:0 0 .8em;">Hi</div>\n')
    ok("a picture's file name is not turned into a caption", "color:#54595d" not in exporter.export(importer.import_wiki(fig))[0])
    issues = wiki_lint.check('<div style="display:none">T. s</div>\n<div style="font:bold 90%% sans-serif;">x</div>')
    ok("Check flags %% in a style", any(i["id"] == "style-percent" for i in issues))
    ok("Fix changes %% to %", "%%" not in wiki_lint.fix('<div style="font:bold 90%% sans-serif;">x</div>')[0])


LAYOUT_PAGE = """<div style="display:none">Layout test. Older and nested layouts.</div>
<div style="display:flex;flex-wrap:wrap;gap:.6em;align-items:flex-start;margin:.6em 0 1em;">
<div style="flex:0 1 300px;min-width:370px;background:#fff;border:1px solid #cfd6de;border-top:6px solid #13806a;border-radius:6px;overflow:hidden;"><div style="font:bold 100% sans-serif;color:#fff;background:#13806a;padding:.35em .6em;">dbo.SOPD</div>
<div style="display:flex;justify-content:space-between;gap:.6em;padding:.12em .6em;"><span style="flex:1 1 auto;"><span style="color:#1f5fa8;font-weight:bold;">FK</span>Facility_Code</span><span style="color:#6b7785;">VARCHAR2 (20)</span></div>
</div>
</div>

{| class="wikitable" style="float:right;"
! colspan="2" style="background:#cedff2" | Access to services
|-
! Reference
| Item 046 with <code><nowiki>a|b</nowiki></code>
|}

<div style="display:flex;flex-wrap:wrap;gap:.6em;margin:.5em 0;">
<div style="flex:1 1 230px;min-width:0;background:#fff;border:1px solid #dfe3e7;border-top:5px solid #13806a;border-radius:6px;padding:.3em .9em .6em;">
'''Controller'''
* Runs every hour
</div>
<div style="flex:1 1 230px;min-width:0;background:#fff;border:1px solid #dfe3e7;border-top:5px solid #1f5fa8;border-radius:6px;padding:.3em .9em .6em;">
'''Workers'''
* Four of them
</div>
</div>

<div style="display:flex;flex-wrap:wrap;align-items:stretch;gap:.4em;margin:.6em 0;">
<div style="flex:1 1 140px;background:#eef7ff;border:1px solid #b6d4f0;border-top:4px solid #1f5fa8;border-radius:6px;padding:.45em .7em;">Build</div>
<div style="align-self:center;color:#6b7785;font:bold 130% sans-serif;">&rarr;</div>
<div style="flex:1 1 140px;background:#eef7ff;border:1px solid #b6d4f0;border-top:4px solid #1f5fa8;border-radius:6px;padding:.45em .7em;">Report</div>
</div>
<div></div>

==== A deeper heading ====

<div style="font:13px/1.6 Consolas,monospace;white-space:pre-wrap;">PROD Server:     server-x<br />PORT:            3901</div>

[[Category:Wiki Help]]
"""


def test_layout():
    print("Layouts the tool has no block for")
    d = importer.import_wiki(LAYOUT_PAGE)
    types = [b["type"] for b in d["blocks"]]
    ok("nothing is left as plain wiki code", "raw" not in types, types)
    ok("older side-by-side boxes become cards with titles",
       any(b["type"] == "cards" and [i["title"] for i in b["items"]] == ["Controller", "Workers"] for b in d["blocks"]), types)
    ok("older boxes joined by arrows become a flow", any(b["type"] == "flow" and len(b["stages"]) == 2 for b in d["blocks"]), types)
    ok("a table with merged cells keeps its layout (not restyled)", not any(b["type"] == "table" for b in d["blocks"]), types)
    lays = [b for b in d["blocks"] if b["type"] == "layout"]
    ok("nested boxes, merged-cell tables and deep headings become layouts", len(lays) == 4, len(lays))
    text, _ = exporter.export(d)
    for chunk in ('<span style="color:#1f5fa8;font-weight:bold;">FK</span>Facility_Code</span>', '! colspan="2" style="background:#cedff2" | Access to services',
                  "==== A deeper heading ====", "PROD Server:     server-x<br />PORT:            3901"):
        ok("untouched layout comes back exactly: " + chunk[:40], chunk in text)
    lf = next(l for b in lays for l in b["leaves"] if "Facility_Code" in l["html"])
    lf["html"] = lf["html"].replace("Facility_Code", "Facility_Key")
    cell = next(l for b in lays for l in b["leaves"] if "Item 046" in l["html"])
    cell["html"] = cell["html"].replace("Item 046", "Item 047 a|b")
    pre = next(l for b in lays for l in b["leaves"] if "3901" in l["html"])
    pre["html"] = pre["html"].replace("3901", "3902")
    text2, _ = exporter.export(d)
    ok("an edit changes only that text", "</span>Facility_Key</span>" in text2 and text2.count("Facility_Code") == text.count("Facility_Code") - 1
       and text2.count("<span") == text.count("<span"))
    ok("edited table cell text keeps the table valid", "| Item 047 a&#124;b" in text2, text2[text2.find("PM 04"):text2.find("PM 04") + 40])
    ok("edited text in a lined-up box keeps its spaces", "PORT:            3902" in text2)
    ok("edited layouts still pass Check", not [i for i in wiki_lint.check(text2) if i["level"] == "error"])
    ok("nothing changes on a second trip", exporter.export(importer.import_wiki(text2))[0] == text2)
    hl = ('<div style="display:none">T. s</div>\n<div style="margin:.4em 0 1em;border:1px solid #3c3c3c;border-radius:6px;overflow:hidden;background:#1e1e1e;">'
          '<div style="flex:1 0 auto;white-space:pre;"><span style="display:block;min-height:20px;padding:0 1em;">SELECT 1</span>'
          '<span style="display:block;min-height:20px;padding:0 1em;background:#1f3d27;">WHERE x = 2</span></div></div></div>\n')
    ok("a code box with highlighted lines loses no lines", "WHERE x = 2" in exporter.export(importer.import_wiki(hl))[0])
    ok("templates and special tags are left as wiki code", layout.build("<div>{{Draft\n|x=1}}</div>") is None and layout.build("<syntaxhighlight>x</syntaxhighlight>") is None)


def test_templates():
    print("Templates")
    ok("there are templates", len(templates.TEMPLATES) >= 19, len(templates.TEMPLATES))
    for t in templates.TEMPLATES:
        d = templates.build(t["id"])
        d["title"] = "Example " + t["name"]
        d["summary"] = "An example page."
        d["categories"] = d["categories"] or ["Wiki Help"]
        text, notes = exporter.export(d)
        errors = [i for i in wiki_lint.check(text) if i["level"] == "error"]
        back, _ = exporter.export(importer.import_wiki(text))
        raw = [b for b in importer.import_wiki(text)["blocks"] if b["type"] == "raw"]
        ok("%-28s exports cleanly, reads back the same" % t["id"], not errors and back == text and not raw,
           (errors, back == text, len(raw)))
        ok("%-28s starts with the hidden line" % t["id"], text.startswith('<div style="display:none">Example '))
        ok("%-28s has no image widths" % t["id"], "px|" not in text and "px]]" not in text)


def test_import_old_pages():
    print("Reading older pages")
    sample = ('<div style="display:none">Old page. A page written by hand.</div>\n'
              "== Purpose ==\nWhy it exists, with a [[Link]] and '''bold'''.\n\n"
              "{{SomeTemplate|x=1}}\n\n* one\n* two\n\n<pre>\nSELECT 1\n</pre>\n\n[[Category:Wiki Help]]\n")
    d = importer.import_wiki(sample)
    types = [b["type"] for b in d["blocks"]]
    ok("title and summary come from the hidden line", d["title"] == "Old page" and d["summary"] == "A page written by hand.", d)
    ok("unknown markup is kept as wiki code", "raw" in types and any("{{SomeTemplate|x=1}}" in b.get("wiki", "") for b in d["blocks"]), types)
    ok("headings, text and code are editable", {"h2", "text", "code"} <= set(types), types)
    ok("category kept", d["categories"] == ["Wiki Help"], d["categories"])


def test_files():
    print("Word and email files")
    tf = os.path.join(HERE, "test_files")
    docx = os.path.join(tf, "example_process.docx")
    if os.path.exists(docx):
        d = importer.import_plain(doc_import.docx_to_text(open(docx, "rb").read()))
        types = [b["type"] for b in d["blocks"]]
        ok("Word: numbered lines become steps", types.count("step") >= 3, types)
        ok("Word: tables and code come through", "table" in types and "code" in types, types)
    eml = os.path.join(tf, "outlook_style_thread.eml")
    if os.path.exists(eml):
        emails, _ = doc_import.parse_eml(open(eml, "rb").read(), "split")
        blk = tool.mail_to_block(emails)
        ok("Email: thread split into separate emails", len(blk["emails"]) >= 2, len(blk["emails"]))
        ok("Email: names replaced by role prompts", all(e["from"] == "Role to be added" for e in blk["emails"]))
        doc = {"title": "T", "summary": "s", "categories": ["Wiki Help"], "blocks": [blk]}
        text, notes = exporter.export(doc)
        ok("Email: no email addresses in the export", not wiki_lint.EMAIL_RE.search(text))
        ok("Email: Outlook-style thread, as on the modern layout page", "Conversation view" in text and "newest first" in text)
        back, _ = exporter.export(importer.import_wiki(text))
        ok("Email: thread reads back the same", back == text)


def request(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": "127.0.0.1:%d" % port}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        h["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw.decode("utf-8"))
    except ValueError:
        return r.status, raw


def test_server():
    print("The local web server")
    tmp = tempfile.mkdtemp(prefix="wst_selftest_")
    old_out, old_drafts = tool.OUTPUT, tool.DRAFTS
    tool.OUTPUT, tool.DRAFTS = tmp, os.path.join(tmp, "drafts")
    port = tool.free_port(18765)
    httpd = tool.ThreadingHTTPServer(("127.0.0.1", port), tool.Handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        s, body = request(port, "GET", "/")
        ok("editor page loads", s == 200 and b"Wiki Style Tool" in body, s)
        s, body = request(port, "GET", "/static/editor.js")
        ok("editor script loads", s == 200)
        s, st = request(port, "GET", "/api/style")
        ok("house styles are served", s == 200 and "h2" in st["S"] and st["categories"])
        s, tl = request(port, "GET", "/api/templates")
        ok("template list is served", s == 200 and len(tl) == len(templates.TEMPLATES))
        s, d = request(port, "GET", "/api/template?id=howto")
        ok("a template can be fetched", s == 200 and d["blocks"])
        d["title"], d["summary"], d["categories"] = "Self test page", "A test.", ["Wiki Help"]
        s, r = request(port, "POST", "/api/export", d)
        ok("export works", s == 200 and r["text"].startswith('<div style="display:none">Self test page.'), r if s != 200 else "")
        s, r2 = request(port, "POST", "/api/import", {"text": r["text"]})
        ok("import works", s == 200 and r2["title"] == "Self test page")
        s, r3 = request(port, "POST", "/api/save", {"name": "../../evil.txt", "text": "x"})
        ok("saving stays inside the output folder", s == 200 and os.path.dirname(r3["path"]) == tmp, r3)
        s, r4 = request(port, "POST", "/api/draft", {"doc": d})
        ok("a draft can be saved", s == 200 and os.path.exists(r4["path"]))
        s, lst = request(port, "GET", "/api/drafts")
        ok("drafts are listed", s == 200 and any(x["name"] == r4["name"] for x in lst))
        s, dd = request(port, "GET", "/api/draft?name=" + r4["name"])
        ok("a draft can be opened", s == 200 and dd.get("title") == "Self test page")
        s, _ = request(port, "GET", "/api/draft?name=../../wiki_style_tool.py")
        ok("draft names can't reach other files", s == 404, s)
        s, _ = request(port, "GET", "/api/ping", headers={"Host": "evil.example.com"})
        ok("requests for other host names are refused", s == 403, s)
        s, _ = request(port, "POST", "/api/save", {"name": "x", "text": "x"}, headers={"Origin": "http://evil.example.com"})
        ok("requests from other web sites are refused", s == 403, s)
        s, cb = request(port, "POST", "/api/codebox", {"title": "", "code": "SELECT 1", "lang": "sql"})
        ok("code box preview works", s == 200 and "#569cd6" in cb["html"])
        s, cb = request(port, "POST", "/api/codebox", {"title": "", "code": "SELECT TOP 10 @x, DATEADD(DAY,1,GETDATE()) FROM sys.objects", "lang": "sql"})
        ok("code box uses the full SSMS colours", all(c in cb["html"] for c in ("#b5cea8", "#9cdcfe", "#d670d6", "#4ec9b0")))
        s, lb = request(port, "POST", "/api/layout", {"wiki": '<div style="color:red">Hello <span style="color:blue">there</span></div>'})
        ok("wiki code can be shown as a layout", s == 200 and lb["block"] and len(lb["block"]["leaves"]) == 2, lb)
        s, bw = request(port, "POST", "/api/blockwiki", {"block": lb["block"]})
        ok("a layout can be shown as wiki code again", s == 200 and bw["wiki"] == '<div style="color:red">Hello <span style="color:blue">there</span></div>', bw)
    finally:
        httpd.shutdown()
        httpd.server_close()
        tool.OUTPUT, tool.DRAFTS = old_out, old_drafts
        shutil.rmtree(tmp, ignore_errors=True)


def test_wiki():
    print("Opening and publishing on the wiki (against a stand-in wiki)")
    for slots in (False, True):
        fw = fake_wiki.sample_wiki()
        fw.slots = slots
        wport = tool.free_port(18950 + 10 * slots)
        wsrv = fake_wiki.serve(fw, wport)
        api = "http://127.0.0.1:%d/w/api.php" % wport
        kind = "newer wiki" if slots else "older wiki"
        tmp = tempfile.mkdtemp(prefix="wst_wiki_")
        old = (tool.OUTPUT, tool.DRAFTS, tool.BACKUPS, dict(tool.WIKI))
        tool.OUTPUT, tool.DRAFTS, tool.BACKUPS = tmp, os.path.join(tmp, "drafts"), os.path.join(tmp, "wiki_backups")
        tool.WIKI.update({"api": api, "session": None, "reader": None})
        port = tool.free_port(18980 + slots)
        httpd = tool.ThreadingHTTPServer(("127.0.0.1", port), tool.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        H = {"X-WST": "1"}
        try:
            s, st = request(port, "GET", "/api/wiki/status")
            ok("%s: starts not connected" % kind, s == 200 and not st["connected"] and st["defaultApi"] == api, st)
            s, r = request(port, "GET", "/api/wiki/search?q=sample")
            ok("%s: search titles" % kind, s == 200 and "Sample Data Hub" in r["titles"], r)
            s, r = request(port, "GET", "/api/wiki/open?title=" + "Sample%20Data%20Hub")
            ok("%s: open a page into blocks" % kind, s == 200 and r["doc"]["title"] == "Sample Data Hub" and r["source"]["revid"] == 101
               and any(b["type"] == "card" for b in r["doc"]["blocks"]), r if s != 200 else r["source"])
            doc = r["doc"]
            s, r2 = request(port, "GET", "/api/wiki/open?title=Old%20Sample")
            ok("%s: a redirect is reported, not opened" % kind, s == 200 and r2.get("redirect") == "Sample Data Hub", r2)
            s, r2 = request(port, "GET", "/api/wiki/open?title=Not%20Yet")
            ok("%s: a missing page can be started" % kind, s == 200 and r2.get("missing"), r2)
            s, r2 = request(port, "POST", "/api/wiki/login", {"username": "Tester@StyleTool", "password": "test-bot-password"})
            ok("%s: wiki actions need the editor's own header" % kind, s == 403, s)
            s, r2 = request(port, "POST", "/api/wiki/login", {"username": "Tester@StyleTool", "password": "wrong"}, headers=H)
            ok("%s: a wrong bot password is refused in plain English" % kind, s == 401 and "bot password" in r2["error"], r2)
            s, r2 = request(port, "POST", "/api/wiki/preview", {"doc": doc}, headers=H)
            ok("%s: publishing needs a connection" % kind, s == 401 and r2["code"] == "notloggedin", r2)
            s, st = request(port, "POST", "/api/wiki/login", {"username": "Tester@StyleTool", "password": "test-bot-password"}, headers=H)
            ok("%s: log in with a bot password" % kind, s == 200 and st["connected"] and st["user"] == "Tester" and st["canEdit"], st)
            doc["blocks"].append({"id": "x1", "type": "text", "html": "<p>Added in the tool.</p>"})
            s, pv = request(port, "POST", "/api/wiki/preview", {"doc": doc}, headers=H)
            ok("%s: preview shows what will change" % kind, s == 200 and pv["samePage"] and pv["added"] > 0 and "Added in the tool." in pv["diff"]
               and not pv["changedSinceOpen"], pv if s != 200 else (pv["samePage"], pv["added"]))
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": doc, "summary": "Self test"}, headers=H)
            ok("%s: publish saves the page" % kind, s == 200 and pb["result"]["newrevid"] > 101 and "Added in the tool." in fw.pages["Sample Data Hub"]["text"]
               and fw.edits[-1][2] == "Self test", pb)
            ok("%s: the old version is backed up" % kind, os.path.isfile(pb.get("backup", "")))
            doc["_wiki"] = pb["source"]
            fw.other_person_edits("Sample Data Hub", fw.pages["Sample Data Hub"]["text"] + "\nTheir change.")
            s, pv = request(port, "POST", "/api/wiki/preview", {"doc": doc}, headers=H)
            ok("%s: preview warns when someone else changed the page" % kind, s == 200 and pv["changedSinceOpen"], pv.get("changedSinceOpen"))
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": doc, "summary": "Mine"}, headers=H)
            ok("%s: their change is not overwritten without asking" % kind, s == 409 and pb["code"] == "editconflict"
               and "Their change." in fw.pages["Sample Data Hub"]["text"], pb)
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": doc, "summary": "Mine", "force": True}, headers=H)
            ok("%s: publishing over it works once asked" % kind, s == 200 and "Their change." not in fw.pages["Sample Data Hub"]["text"], pb)
            new = {"title": "Brand new page", "summary": "A test.", "categories": ["Wiki Help"], "blocks": [
                {"id": "a", "type": "text", "html": "<p>Hello</p>"},
                {"id": "b", "type": "image", "file": "Missing_700.png", "full": "Missing_full.png", "caption": "x"}]}
            s, pv = request(port, "POST", "/api/wiki/preview", {"doc": new}, headers=H)
            ok("%s: a new page and its missing pictures are reported" % kind, s == 200 and not pv["exists"]
               and set(pv["missingFiles"]) == {"Missing_700.png", "Missing_full.png"}, pv if s != 200 else pv["missingFiles"])
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": new, "summary": "New"}, headers=H)
            ok("%s: a new page is created" % kind, s == 200 and pb["result"]["new"] and "Brand new page" in fw.pages, pb)
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": {"title": "Sample Data Hub", "blocks": []}, "summary": "x"}, headers=H)
            ok("%s: an existing page is not replaced unless it was opened" % kind, s == 400 and pb["code"] == "articleexists", pb)
            s, r3 = request(port, "GET", "/api/wiki/open?title=Navigation%20Page")
            s, pb = request(port, "POST", "/api/wiki/publish", {"doc": r3["doc"], "summary": "x"}, headers=H)
            ok("%s: protected pages are refused with a reason" % kind, s == 400 and pb["code"] == "protectedpage" and "admin" in pb["error"], pb)
            s, st = request(port, "POST", "/api/wiki/logout", {}, headers=H)
            ok("%s: disconnect" % kind, s == 200 and not st["connected"], st)
            leaked = []
            for base, _, files in os.walk(tmp):
                for f in files:
                    if "test-bot-password" in open(os.path.join(base, f), encoding="utf-8", errors="ignore").read():
                        leaked.append(f)
            ok("%s: the bot password is never written to disk" % kind, not leaked, leaked)
        finally:
            httpd.shutdown()
            httpd.server_close()
            wsrv.shutdown()
            wsrv.server_close()
            tool.OUTPUT, tool.DRAFTS, tool.BACKUPS = old[0], old[1], old[2]
            tool.WIKI.clear()
            tool.WIKI.update(old[3])
            shutil.rmtree(tmp, ignore_errors=True)
    try:
        wiki_api.check_api_url("http://wiki.example.com/api.php")
        ok("only https addresses are accepted for a real wiki", False)
    except wiki_api.WikiError:
        ok("only https addresses are accepted for a real wiki", True)


def main():
    test_rich()
    test_regressions()
    test_layout()
    test_templates()
    test_import_old_pages()
    test_files()
    test_server()
    test_wiki()
    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
