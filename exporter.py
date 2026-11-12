"""
exporter.py - turns an article (the editor's JSON) into Wiki wikitext.

    text, notes = export(doc)

doc = {"title", "summary", "toc", "categories": [...], "blocks": [...]}
Each block is a dict with a "type". Unfilled template prompts become hidden
<!-- TODO: ... --> comments, so nothing invented ever shows on the page.
"""
import re

import house_style as hs
import layout
import rich

OFFICIAL_CATEGORIES = [
    "Platform and Access", "Team Processes", "Reporting", "Reference Data", "Procedures", "Wiki Help",
]

BLOCK_NAMES = {
    "hero": "Page banner", "card": "Intro card", "h2": "Section heading", "h3": "Sub-heading", "text": "Text",
    "step": "Step", "callout": "Callout", "table": "Table", "cards": "Cards", "flow": "Flow",
    "code": "Code box", "collapse": "Expandable section", "image": "Picture", "divider": "Divider",
    "raw": "Wiki code", "email": "Email thread", "layout": "Layout from the wiki",
}


def _plain(s):
    """A plain one-line field (heading, title) -> safe wikitext."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return rich.esc_text(s)


def _pf(b, key, notes=None, idx=-1):
    """A plain field that may still be a template prompt (listed in b["ph"])."""
    cur = b
    for part in key.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                cur = ""
                break
        elif isinstance(cur, dict):
            cur = cur.get(part, "")
        else:
            cur = ""
    val = str(cur or "")
    if key in (b.get("ph") or {}):
        if notes is not None:
            notes.append({"level": "warn", "block": idx, "message": "Still to do: %s" % val})
        return rich.ph_comment(val)
    return _plain(val)


def _col(b, default="blue"):
    c = b.get("color") or default
    return c if c in hs.COLOURS else default


def _block(b, n_step, notes, idx):
    t = b.get("type")

    def note(level, msg):
        notes.append({"level": level, "block": idx, "message": msg})

    if t == "hero":
        title = _plain(b.get("title")) or b.get("_page_title", "")
        sub = rich.to_inline(b.get("sub", ""))
        pills = [_plain(p) for p in (b.get("pills") or []) if str(p).strip()]
        return "html", hs.hero(_plain(b.get("kicker")), title, sub, pills)
    if t == "card":
        body = rich.to_wiki(b.get("html", ""))
        if not body:
            note("info", "An intro card is empty.")
        return "html", hs.card(body)
    if t in ("h2", "h3"):
        text = _pf(b, "text", notes, idx)
        if not text:
            note("warn", "A heading has no text.")
            text = rich.ph_comment("heading")
        return "html", (hs.h2 if t == "h2" else hs.h3)(text, _col(b, "blue"))
    if t == "text":
        body = rich.to_wiki(b.get("html", ""))
        return "text", body
    if t == "step":
        body = rich.to_wiki(b.get("html", ""))
        if not body:
            note("info", "Step %d is empty." % n_step)
        return "html", hs.step(n_step, body, _col(b, "blue"))
    if t == "callout":
        kind = b.get("kind") if b.get("kind") in hs.CALLOUTS else "note"
        title = _pf(b, "title", notes, idx)
        src = b.get("html", "")
        if rich.is_simple(src) or not rich.plain(src):
            body = rich.to_inline(src)
            if title:
                body = ("'''%s''' %s" % (title, body)).strip()
            return "html", hs.callout(kind, body, inline=True)
        body = rich.to_wiki(src)
        if title:
            if body[:1] in ("*", "#") or body.startswith("<!--"):
                body = "'''%s'''\n\n%s" % (title, body)
            else:
                body = "'''%s''' %s" % (title, body)
        return "html", hs.callout(kind, body, inline=False)
    if t == "table":
        rows = b.get("rows") or []
        rows = [[rich.to_inline(c, cell=True) for c in r] for r in rows if isinstance(r, list)]
        if not rows:
            note("warn", "A table has no rows.")
            return None, ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        return "html", hs.table(rows, header=bool(b.get("header", True)), keyval=bool(b.get("keyval")), c=_col(b, "navy"))
    if t == "cards":
        items = []
        for n, it in enumerate(b.get("items") or []):
            c = it.get("color") if it.get("color") in hs.COLOURS else None
            items.append((_pf(b, "items.%d.title" % n, notes, idx), rich.to_wiki(it.get("html", "")), c))
        if not items:
            return None, ""
        return "html", hs.cards(items, _col(b, "blue"))
    if t == "flow":
        stages = []
        for n, sg in enumerate(b.get("stages") or []):
            parts = []
            for kind, val in rich.to_chunks(sg.get("html", "")):
                if kind == "p":
                    parts.append("<br />".join(val))
                elif kind == "list":
                    parts += [re.sub(r"^[*#]+\s*", "", l) for l in val]
                elif kind == "todo":
                    parts.append(rich.ph_comment(val))
            c = sg.get("color") if sg.get("color") in hs.COLOURS else None
            stages.append((_pf(b, "stages.%d.title" % n, notes, idx), parts, c))
        if not stages:
            return None, ""
        return "html", hs.flow(stages, _col(b, "blue"))
    if t == "code":
        code = b.get("code", "")
        if not code.strip():
            note("info", "A code box is empty.")
        return "html", hs.codebox(str(b.get("title") or "").strip(), code, "sql" if b.get("lang", "sql") == "sql" else "text")
    if t == "collapse":
        title = _pf(b, "title", notes, idx) or "Details"
        return "html", hs.collapse(title, rich.to_wiki(b.get("html", "")), bool(b.get("collapsed", True)), _col(b, "navy"))
    if t == "image":
        name = re.sub(r"^\s*(File|Image)\s*:", "", str(b.get("file") or ""), flags=re.I).strip()
        full = re.sub(r"^\s*(File|Image)\s*:", "", str(b.get("full") or ""), flags=re.I).strip()
        if not name:
            note("warn", "A picture has no file name yet.")
            cap = re.sub(r"[()]", "", str(b.get("caption") or "")).strip()
            return "html", rich.ph_comment("add a picture here" + (" (%s)" % cap if cap else ""))
        return "html", hs.figure(name, full, _plain(b.get("caption")))
    if t == "email":
        ems = b.get("emails") or []
        if not ems:
            return None, ""
        msgs, colours, subjects = [], {}, []
        for n, em in enumerate(ems):
            f = lambda k: _pf(b, "emails.%d.%s" % (n, k), notes, idx)
            frm_plain = "" if "emails.%d.from" % n in (b.get("ph") or {}) else re.sub(r"\s+", " ", str(em.get("from") or "")).strip()
            if frm_plain not in colours:
                colours[frm_plain] = hs.BADGE_COLOURS[len(colours) % len(hs.BADGE_COLOURS)]
            people = lambda k: ([f(k)] if "emails.%d.%s" % (n, k) in (b.get("ph") or {}) else
                                [_plain(x) for x in re.split(r"\s*[;,]\s*", str(em.get(k) or "")) if x.strip()])
            subjects.append("" if "emails.%d.subject" % n in (b.get("ph") or {}) else str(em.get("subject") or ""))
            body = []
            for kind, val in rich.to_chunks(em.get("html", "")):
                if kind == "p":
                    body.append('<p style="%s">%s</p>' % (hs.S["ol_p"], "<br />".join(val)))
                elif kind == "list":
                    body.append('<ul style="%s">%s</ul>' % (hs.S["ol_ul"], "".join("<li>%s</li>" % re.sub(r"^[*#]+\s*", "", l) for l in val)))
                elif kind == "todo":
                    body.append(rich.ph_comment(val))
            msgs.append({"from": f("from"), "sent": f("sent"), "to": people("to"), "cc": people("cc"),
                         "subject": f("subject"), "body": "".join(body), "badge": hs.initials(frm_plain) if frm_plain else "?",
                         "colour": colours[frm_plain]})
        subject = _plain(b.get("caption")) or _plain(hs.thread_subject(subjects)) or rich.ph_comment("thread subject")
        first_sent = str(ems[0].get("sent") or "")
        dm = re.search(r"\b(\d{1,2} [A-Z][a-z]+ \d{4})\b", first_sent)
        meta = "%d message%s%s &middot; newest first" % (len(msgs), "" if len(msgs) == 1 else "s", (" &middot; " + dm.group(1)) if dm else "")
        return "html", hs.email(subject, meta, msgs)
    if t == "divider":
        return "html", hs.divider()
    if t == "raw":
        return "text", str(b.get("wiki") or "").strip("\n")
    if t == "layout":
        return "text", layout.export(b).strip("\n")
    note("warn", "A block of an unknown kind (%s) was left out." % t)
    return None, ""


def _prompts(b):
    fields = []
    for k in ("html", "sub"):
        if k in b:
            fields.append(b.get(k) or "")
    for it in (b.get("items") or []) + (b.get("stages") or []) + (b.get("emails") or []):
        fields.append(it.get("html", ""))
    for r in b.get("rows") or []:
        fields += [c for c in r if isinstance(c, str)]
    out = layout.prompts(b) if b.get("type") == "layout" else []
    for f in fields:
        if rich.has_ph(f):
            out += rich.ph_texts(f)
    return out


def export(doc):
    notes = []
    title = re.sub(r"\s+", " ", str(doc.get("title") or "")).strip()
    summary = re.sub(r"\s+", " ", str(doc.get("summary") or "")).strip()
    if not title:
        notes.append({"level": "error", "block": -1, "message": "The page has no title. Add one at the top of the page."})
    if not summary:
        notes.append({"level": "warn", "block": -1, "message": "Add a search summary (Page panel). It becomes the hidden first line."})
    elif re.search(r"[<>\[\]{}|=]", summary + title):
        notes.append({"level": "info", "block": -1, "message": "The characters < > [ ] { } | = were taken out of the hidden first line."})
    parts = []
    blocks = doc.get("blocks") or []
    tocv = doc.get("toc", True)          # True: __TOC__, False: __NOTOC__, None: neither (the wiki decides)
    toc, notoc = tocv is True, tocv is False
    toc_done = False
    n_step = 0
    # the contents box goes before the first section heading (or the first sub-heading on a page without sections)
    heads = [i for i, b in enumerate(blocks) if isinstance(b, dict) and b.get("type") == "h2"] or \
            [i for i, b in enumerate(blocks) if isinstance(b, dict) and b.get("type") == "h3"]
    toc_at = heads[0] if heads else -1
    for idx, b in enumerate(blocks):
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "h2":
            n_step = 0
        if toc and not toc_done and idx == toc_at:
            parts.append(("html", "__TOC__"))
            toc_done = True
        if t == "step":
            try:
                start = int(b.get("start")) if b.get("start") not in (None, "") else None
            except (TypeError, ValueError):
                start = None
            n_step = start if start else n_step + 1
        if t == "hero":
            b = dict(b, _page_title=rich.esc_text(title))
        kind, text = _block(b, n_step, notes, idx)
        for p in _prompts(b):
            notes.append({"level": "warn", "block": idx, "message": "Still to do: %s" % p})
        if kind and text.strip():
            parts.append((kind, text))
    if notoc:
        parts.append(("html", "__NOTOC__"))
    cats = [re.sub(r"^\s*Category\s*:", "", str(c), flags=re.I).strip() for c in doc.get("categories") or []]
    cats = list(dict.fromkeys(c for c in cats if c))
    if not cats:
        notes.append({"level": "warn", "block": -1, "message": "Add at least one category (Page panel)."})
    for c in cats:
        if c not in OFFICIAL_CATEGORIES:
            notes.append({"level": "info", "block": -1, "message": "\"%s\" is not one of the wiki's main categories. Check it exists." % c})
    if cats:
        parts.append(("html", "\n".join("[[Category:%s]]" % c for c in cats)))
    text = hs.hidden_line(title or "Untitled page", summary)
    prev = "html"
    for kind, chunk in parts:
        text += ("\n" if (kind == "html" and prev == "html") else "\n\n") + chunk
        prev = kind
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text, notes
