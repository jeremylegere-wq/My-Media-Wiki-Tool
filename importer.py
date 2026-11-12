"""
importer.py - reads wikitext back into editor blocks.

    doc = import_wiki(text)     # an existing page's wikitext
    doc = import_plain(text)    # plain text, or text read from a Word document

Pages made with this tool come back exactly. For older pages, the parts that
match our house style become editable blocks. Other layouts (boxes inside
boxes, tables with merged or coloured cells, diagrams) become "layout" blocks:
the layout is kept exactly and the text inside it can be edited. Only what the
tool can't safely touch (templates, extension tags) is kept in a "Wiki code"
block, so nothing is ever lost.
"""
import html as _html
import re
import uuid

import house_style as hs
import layout
import rich

HEX = r"#[0-9a-fA-F]{6}"


def _id():
    return uuid.uuid4().hex[:10]


def _cname(hexv, default="blue"):
    return hs.COLOUR_NAMES.get((hexv or "").lower(), default)


def _plain(s):
    """Wiki/HTML fragment -> plain text for a one-line field."""
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def _pfield(raw):
    """A plain field from the page: (text, True) when it is an unfilled prompt."""
    m = rich.TODO_RE.fullmatch((raw or "").strip())
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(), True
    return _plain(raw), False


def _setpf(block, key, raw):
    text, isph = _pfield(raw)
    if isph:
        block.setdefault("ph", {})[key] = True
    return text


def _rich(body):
    """Block wikitext -> editor HTML, or None when it holds things we can't edit safely."""
    try:
        return rich.wiki_to_html(body)
    except rich.Unsupported:
        return None


def _inline(s):
    try:
        return rich.inline_to_html(s)
    except rich.Unsupported:
        return None


def B(type_, **kw):
    d = {"id": _id(), "type": type_}
    d.update(kw)
    return d


def keep(c):
    """Anything without a house-style block: a layout with editable text, or wiki code."""
    lb = layout.build(c)
    if lb:
        lb["id"] = _id()
        return lb
    return B("raw", wiki=c)


# ---------------------------------------------------------------- recognisers
def _strip_wrap(body):
    """Content of a block div: either inline, or wrapped in blank lines."""
    return body.strip("\n").strip()


def r_hero(c):
    if "linear-gradient(120deg,#0f2a4a" not in c[:200]:
        return None
    kick = re.search(r'<div style="[^"]*letter-spacing[^"]*">(.*?)</div>', c, re.S)
    title = re.search(r'<div style="[^"]*Georgia[^"]*">(.*?)</div>', c, re.S)
    sub = re.search(r'<div style="(?:font-size:1\d\d%;[^"]*)">(.*?)</div>', c, re.S)
    pills = re.findall(r'<span style="[^"]*border-radius:99px[^"]*">(.*?)</span>', c, re.S)
    rest = c
    for m in (kick, title, sub):
        if m:
            rest = rest.replace(m.group(0), "", 1)
    rest = re.sub(r'<span style="[^"]*border-radius:99px[^"]*">.*?</span>', "", rest, flags=re.S)
    rest = re.sub(r"<div[^>]*>|</div>", "", rest)
    if rest.strip():
        return None
    subh = _inline(sub.group(1)) if sub else ""
    if subh is None:
        return None
    return B("hero", kicker=_plain(kick.group(1)) if kick else "", title=_plain(title.group(1)) if title else "",
             sub=subh, pills=[_plain(p) for p in pills])


def r_card(c):
    m = re.fullmatch(r'<div style="background:#fff;border:1px solid #dfe3e7;border-radius:6px;padding:\.9em 1\.2em;[^"]*">(.*)</div>', c, re.S)
    if not m or "<div" in m.group(1):
        return None
    h = _rich(_strip_wrap(m.group(1)))
    return None if h is None else B("card", html=h)


def r_heading(c):
    m = re.fullmatch(r'<(h2|h3) style="([^"]*)">(.*?)</\1>', c.strip(), re.S)
    if not m or (not rich.TODO_RE.fullmatch(m.group(3).strip()) and "<" in m.group(3)):
        return None
    tag, style, text = m.groups()
    col = re.search(r"border-(?:left|bottom):\d+px solid (%s)" % HEX, style)
    b = B(tag, text="", color=_cname(col.group(1) if col else hs.NAVY, "navy"))
    b["text"] = _setpf(b, "text", text)
    return b


STEP_NEW = re.compile(r'<div style="display:flex;gap:\.8em;align-items:flex-start;margin:0 0 \.8em;"><div style="flex:0 0 2\.4em;"><div style="background:(%s);[^"]*">(\d+)</div></div><div style="[^"]*">(.*)</div></div>' % HEX, re.S)
STEP_OLD = re.compile(r'<div style="display:flex;gap:\.8em;align-items:flex-start;background:#fff;[^"]*"><div style="flex:0 0 auto;background:(%s);[^"]*">(\d+)</div><div style="flex:1 1 auto;min-width:0;">(.*)</div></div>' % HEX, re.S)


def r_step(c):
    m = STEP_NEW.fullmatch(c.strip()) or STEP_OLD.fullmatch(c.strip())
    if not m or "<div" in m.group(3):
        return None
    h = _rich(_strip_wrap(m.group(3)))
    if h is None:
        return None
    return B("step", html=h, color=_cname(m.group(1)), _num=int(m.group(2)))


CALLOUT_BG = {"#e6f0fb": "note", "#eef7ff": "note", "#fff1d6": "warning", "#fff8e1": "warning",
              "#fdecea": "danger", "#e9f7f1": "tip", "#e7f5ef": "tip", "#f4f5f7": "old"}


def r_callout(c):
    m = re.fullmatch(r'<div style="background:(%s);border:1px solid %s;border-left:[68]px solid (%s);[^"]*">(.*)</div>' % (HEX, HEX, HEX), c.strip(), re.S)
    if not m or m.group(1).lower() not in CALLOUT_BG or "<div" in m.group(3):
        return None
    kind = CALLOUT_BG[m.group(1).lower()]
    body = _strip_wrap(m.group(3))
    title = ""
    t = re.match(r"^'''([^']+?)'''(?:\s+|\n\n|$)", body)
    if t:
        title, body = t.group(1).strip(), body[t.end():]
    h = _rich(body)
    if h is None:
        return None
    b = B("callout", kind=kind, title="", html=h)
    b["title"] = _setpf(b, "title", title)
    return b


def _cells(line):
    """'| style="..." | text' or '! ... | text' -> text (also handles '||' runs)."""
    parts = re.split(r"\s*(?:\|\||!!)\s*", line[1:])
    out = []
    for p in parts:
        m = re.match(r'^\s*(?:[a-z-]+="[^"]*"\s*)+\|(?!\|)\s?(.*)$', p)
        out.append((m.group(1) if m else p).strip())
    return out


CELL_PROPS = {"padding", "padding-left", "padding-right", "padding-top", "padding-bottom", "vertical-align", "text-align",
              "width", "min-width", "max-width", "white-space", "border", "border-top", "border-bottom", "border-left",
              "border-right", "border-collapse", "border-color", "border-width", "border-style"}
HEAD_PROPS = CELL_PROPS | {"background", "background-color", "color", "font-weight", "font", "font-size", "font-family"}
ROW_PROPS = {"border", "border-top", "border-bottom", "vertical-align"}


def _style_ok(attrs, props, white_bg=False):
    """True when cell or row attributes hold nothing a house-style table would lose."""
    attrs = (attrs or "").strip()
    if not attrs:
        return True
    pairs = re.findall(r'([A-Za-z-]+)\s*=\s*"([^"]*)"', attrs)
    if re.sub(r'([A-Za-z-]+)\s*=\s*"([^"]*)"', "", attrs).strip():
        return False
    for name, val in pairs:
        if name.lower() == "scope":
            continue
        if name.lower() != "style":
            return False
        for decl in [d for d in val.split(";") if d.strip()]:
            if ":" not in decl:
                return False
            prop, v = [x.strip().lower() for x in decl.split(":", 1)]
            if prop in props:
                continue
            if white_bg and prop in ("background", "background-color") and v in ("#fff", "#ffffff", "white"):
                continue
            return False
    return True


def _table_attrs_ok(c):
    """House-style tables only. Merged cells, coloured cells, sortable or collapsible
    tables go to a layout block instead, so none of that is lost."""
    lines = c.strip().split("\n")
    if re.search(r"sortable|mw-collapsible|autocollapse", lines[0], re.I):
        return False
    for line in lines[1:-1]:
        s = line.strip()
        if s.startswith("|-"):
            if not _style_ok(s[2:], ROW_PROPS, white_bg=True):
                return False
            continue
        if not s or s[0] not in "|!" or s.startswith("|}"):
            continue
        sep = r"\s*(?:\|\||!!)\s*" if s[0] == "!" else r"\s*\|\|\s*"
        for p in re.split(sep, s[1:]):
            m = re.match(r'^\s*((?:[A-Za-z-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s|]+)\s*)+)\|(?!\|)', p)
            if m and not _style_ok(m.group(1), HEAD_PROPS if s[0] == "!" else CELL_PROPS, white_bg=True):
                return False
    return True


def r_table(c):
    lines = c.strip().split("\n")
    if not lines[0].startswith("{|") or lines[-1].strip() != "|}":
        return None
    if not _table_attrs_ok(c):
        return None
    hdr_col = re.search(r'^!\s*style="background:(%s);color:#fff' % HEX, c, re.M)
    rows, cur, kinds = [], None, []
    for line in lines[1:-1]:
        s = line.strip()
        if s.startswith("|+"):
            return None
        if s.startswith("|-"):
            cur = []
            rows.append(cur)
            kinds.append([])
            continue
        if not s:
            continue
        if s[0] in "|!":
            if cur is None:
                cur = []
                rows.append(cur)
                kinds.append([])
            for cell in _cells(s):
                cur.append(cell)
                kinds[-1].append(s[0])
        else:
            if not cur:
                return None
            cur[-1] += "\n" + s   # continuation lines
    rows = [r for r in rows if r]
    kinds = [k for k in kinds if k]
    if not rows:
        return None
    header = all(k == "!" for k in kinds[0]) and len(rows) > 1 and not all(
        len(k) > 1 and k[0] == "!" and all(x == "|" for x in k[1:]) for k in kinds)
    keyval = all(len(k) > 1 and k[0] == "!" and all(x == "|" for x in k[1:]) for k in (kinds[1:] if header else kinds))
    out = []
    for r in rows:
        row = []
        for cell in r:
            if "\n" in cell:
                return None
            h = _inline(cell.replace("&#124;", "|"))
            if h is None:
                return None
            row.append(h)
        out.append(row)
    return B("table", rows=out, header=header, keyval=keyval,
             color=_cname(hdr_col.group(1) if hdr_col else hs.NAVY, "navy"))


CARD_RE = re.compile(r'<div style="flex:1 1 \d+px;min-width:0;background:#fff;border:1px solid #dfe3e7;border-top:\d+px solid (%s);[^"]*">'
                     r'\s*(?:<div style="font:bold 112%% sans-serif;color:%s;margin:[^"]*">(.*?)</div>)?(.*?)</div>' % (HEX, HEX), re.S)


def r_cards(c):
    m = re.fullmatch(r'<div style="display:flex;flex-wrap:wrap;gap:[\d.]+em;margin:[^"]*">\s*(.*)\s*</div>', c.strip(), re.S)
    if not m:
        return None
    inner = m.group(1)
    items, pos = [], 0
    for cm in CARD_RE.finditer(inner):
        if inner[pos:cm.start()].strip():
            return None
        body = cm.group(3)
        if "<div" in body:
            return None
        title = cm.group(2) or ""
        if not cm.group(2):
            # older cards: the title is a bold first line
            tm = re.match(r"^\s*'''([^'\n]+?)'''[ \t]*\n", body)
            if tm:
                title, body = tm.group(1).strip(), body[tm.end():]
        h = _rich(_strip_wrap(body))
        if h is None:
            return None
        items.append({"title": title, "html": h, "color": _cname(cm.group(1))})
        pos = cm.end()
    if not items or inner[pos:].strip():
        return None
    cols = {i["color"] for i in items}
    col = items[0]["color"]
    if len(cols) == 1:
        for i in items:
            i.pop("color")
    b = B("cards", color=col, items=items)
    for n, it in enumerate(items):
        it["title"] = _setpf(b, "items.%d.title" % n, it["title"])
    return b


STAGE_RE = re.compile(r'<div style="flex:1 1 180px;min-width:0;background:#f8f9fa;[^"]*border-top:6px solid (%s);[^"]*">'
                      r'<div style="font:bold 105%% sans-serif;[^"]*">(.*?)</div>((?:<div style="background:#fff;border:1px solid #dfe3e7;border-left:5px solid %s;[^"]*">.*?</div>)*)</div>' % (HEX, HEX), re.S)


def r_flow(c):
    m = re.fullmatch(r'<div style="display:flex;flex-wrap:wrap;gap:\.5em;align-items:stretch;margin:\.4em 0 1em;">(.*)</div>', c.strip(), re.S)
    if not m:
        return None
    inner = re.sub(r'<div style="flex:0 0 auto;align-self:center;[^"]*">&rarr;</div>', "", m.group(1))
    stages, pos = [], 0
    for sm in STAGE_RE.finditer(inner):
        if inner[pos:sm.start()].strip():
            return None
        items = re.findall(r'<div style="background:#fff;[^"]*">(.*?)</div>', sm.group(3), re.S)
        hs_ = []
        for it in items:
            t = rich.TODO_RE.fullmatch(it.strip())
            if t:
                hs_.append('<p data-ph="1">%s</p>' % rich._h(t.group(1)))
                continue
            h = _inline(it)
            if h is None:
                return None
            hs_.append("<p>%s</p>" % h)
        stages.append({"title": sm.group(2), "html": "".join(hs_), "color": _cname(sm.group(1))})
        pos = sm.end()
    if not stages or inner[pos:].strip():
        return None
    col = stages[0]["color"]
    if len({s["color"] for s in stages}) == 1:
        for s in stages:
            s.pop("color")
    b = B("flow", color=col, stages=stages)
    for n, sg in enumerate(stages):
        sg["title"] = _setpf(b, "stages.%d.title" % n, sg["title"])
    return b


OLD_BOX = re.compile(r'<div style="flex:1 1 \d+px;(?:min-width:0;)?background:%s;border:1px solid %s;border-top:\d+px solid (%s);[^"]*">(.*?)</div>' % (HEX, HEX, HEX), re.S)
OLD_ARROW = re.compile(r'<div style="(?:flex:0 0 auto;)?align-self:center;[^"]*">\s*(?:&rarr;|&#8594;|&#x2192;|\u2192)\s*</div>', re.I)


def r_flow_old(c):
    """The flow diagram from earlier versions of the tool: boxes joined by arrows."""
    m = re.fullmatch(r'<div style="display:flex;flex-wrap:wrap;align-items:stretch;gap:[^"]*">\s*(.*?)\s*</div>', c.strip(), re.S)
    if not m:
        return None
    inner, pos, stages = m.group(1), 0, []
    want_box = True
    while pos < len(inner):
        ws = re.match(r"\s*", inner[pos:]).end()
        pos += ws
        if pos >= len(inner):
            break
        rx = OLD_BOX if want_box else OLD_ARROW
        mm = rx.match(inner, pos)
        if not mm:
            return None
        if want_box:
            if "<div" in mm.group(2):
                return None
            stages.append({"title": mm.group(2), "html": "", "color": _cname(mm.group(1))})
        pos = mm.end()
        want_box = not want_box
    if len(stages) < 2 or want_box:
        return None
    col = stages[0]["color"]
    if len({s["color"] for s in stages}) == 1:
        for s in stages:
            s.pop("color")
    b = B("flow", color=col, stages=stages)
    for n, sg in enumerate(stages):
        sg["title"] = _setpf(b, "stages.%d.title" % n, sg["title"])
    return b


def r_code(c):
    if not c.startswith('<div style="margin:.4em 0 1em;border:1px solid #3c3c3c;'):
        return None
    tab = re.search(r'<span style="display:inline-block;background:#1e1e1e;[^"]*">(.*?)</span>', c, re.S)
    m = re.search(r'<div style="flex:1 0 auto;white-space:pre;">(.*)</div></div></div>\s*$', c, re.S)
    if not m:
        return None
    opener = '<span style="display:block;min-height:20px;padding:0 1em;">'
    # lines with their own styling (for example highlighted changes) have no place in a
    # plain code box: leave the whole box to a layout block so nothing is lost
    openers = re.findall(r'<span style="display:block;min-height:20px;padding:0 1em;[^"]*">', m.group(1))
    if any(o != opener for o in openers):
        return None
    nums = re.findall(r'<span style="display:block;min-height:20px;">\d+</span>', c)
    pieces = m.group(1).split(opener)[1:]
    if nums and len(nums) != len(pieces):
        return None
    lines = []
    for p in pieces:
        if p.endswith("</span>"):
            p = p[:-7]
        lines.append(_html.unescape(re.sub(r"<[^>]+>", "", p)))
    lang = "sql" if "color:#569cd6" in c or "color:#57a64a" in c or "color:#ce9178" in c else "text"
    title = _html.unescape(tab.group(1)) if tab else ""
    if lang == "sql" and title == "SQLQuery1.sql":
        title = ""
    if lang == "text" and title == "Text":
        title = ""
    return B("code", lang=lang, title=title, code="\n".join(lines))


def r_collapse(c):
    m = re.fullmatch(r'<div class="(mw-collapsible(?: mw-collapsed)?)" style="[^"]*"><div style="[^"]*?(?:color:(%s);)?">(.*?)</div>'
                     r'<div class="mw-collapsible-content" style="[^"]*">(.*)</div></div>' % HEX, c.strip(), re.S)
    if not m or "<div" in m.group(4):
        return None
    h = _rich(_strip_wrap(m.group(4)))
    if h is None:
        return None
    b = B("collapse", title="", html=h, collapsed="mw-collapsed" in m.group(1), color=_cname(m.group(2) or hs.NAVY, "navy"))
    b["title"] = _setpf(b, "title", m.group(3))
    return b


FILE_RE = re.compile(r"\[\[(?:File|Image):([^|\]]+)((?:\|[^\]]*?)?)\]\]", re.I)


def _file_parts(m):
    name = m.group(1).strip()
    full, cap = "", ""
    for p in [x for x in m.group(2).split("|") if x]:
        lm = re.match(r"^\s*link=\{\{filepath:([^}]+)\}\}\s*$", p)
        if lm:
            full = lm.group(1).strip()
        elif re.match(r"^\s*(\d+px|thumb|frame|frameless|left|right|center|none|upright.*|link=.*)\s*$", p):
            continue
        else:
            cap = p.strip()
    return name, full, cap


def r_figure(c, nxt):
    m = re.fullmatch(r'<div style="max-width:\d+px;[^"]*">(\[\[(?:File|Image):[^\]]*\]\])</div>', c.strip(), re.S)
    if not m:
        return None, False
    fm = FILE_RE.fullmatch(m.group(1))
    if not fm:
        return None, False
    name, full, cap = _file_parts(fm)
    used = False
    if nxt:
        cm = re.fullmatch(r'<div style="font-size:90%;color:#54595d;margin:0 0 1em;">(.*?)</div>', nxt.strip(), re.S)
        if cm:
            cap2 = _plain(cm.group(1))
            cap2 = re.sub(r"\s*Click the picture to open it full size\.\s*$", "", cap2).strip()
            cap = cap2.rstrip(".") if full else cap2
            used = True
    if not used and cap == name:
        cap = ""
    return B("image", file=name, full=full, caption=cap), used


EMAIL_RE_ = re.compile(r'<div style="border:1px solid #dfe3e7;border-left:6px solid #1f5fa8;border-radius:6px;margin:0 0 \.6em;background:#fff;overflow:hidden;"><div style="background:#f4f5f7;[^"]*">(.*?)</div><div style="padding:\.5em \.9em;">(.*)</div></div>', re.S)


def r_email_one(c):
    m = EMAIL_RE_.fullmatch(c.strip())
    if not m or "<div" in m.group(2):
        return None
    hdr = {}
    for part in re.split(r"<br\s*/?>\s*", m.group(1)):
        hm = re.match(r"^\s*'''(From|Sent|Date|To|Cc|Subject):'''\s*(.*)$", part.strip(), re.S)
        if hm:
            key = hm.group(1).lower()
            hdr["sent" if key == "date" else key] = hm.group(2).strip()
    h = _rich(_strip_wrap(m.group(2)))
    if h is None:
        return None
    em = {k: hdr.get(k, "") for k in ("from", "sent", "to", "cc", "subject")}
    em["html"] = h
    return em


OL_MSG = '<div style="background:#fff;border-bottom:1px solid #edebe9;padding:14px 18px 12px;'


def r_outlook(c):
    """The Outlook-style email thread from Wiki page templates (modern layout)."""
    c = c.strip()
    if not c.startswith('<div style="border:1px solid #c8c6c4;border-radius:3px;overflow:hidden;background:#faf9f8;'):
        return None
    head = re.search(r'<div style="font-size:20px;font-weight:300;[^"]*">(.*?)</div>', c, re.S)
    pieces = c.split(OL_MSG)[1:]
    if not head or not pieces:
        return None
    b = B("email", caption="", emails=[])
    subjects = []
    for n, p in enumerate(pieces):
        g = lambda rx: (re.search(rx, p, re.S).group(1) if re.search(rx, p, re.S) else "")
        frm = g(r'<div style="font-size:15px;font-weight:600;color:#201f1e;">(.*?)</div>')
        sent = g(r'<div style="font-size:12px;color:#605e5c;">Sent: (.*?)</div>')
        to = g(r'<span style="color:#8a8886;">To:</span> (.*?)</div>')
        cc = g(r'<span style="color:#8a8886;">Cc:</span> (.*?)</div>')
        subj = g(r'<span style="color:#8a8886;">Subject:</span> (.*?)</div>')
        bm = re.search(r'<div style="font-size:14px;line-height:1.5;color:#201f1e;">(.*?)</div></div></div></div>(?:</div>)?$', p, re.S)
        if not bm:
            return None
        parts, pos, html_parts = bm.group(1), 0, []
        for m in re.finditer(r'<p style="margin:0 0 \.85em;">(.*?)</p>|<ul style="[^"]*">(.*?)</ul>|<!--\s*TODO:\s*(.*?)\s*-->', parts, re.S):
            if parts[pos:m.start()].strip():
                return None
            if m.group(1) is not None:
                h = _inline(m.group(1))
                if h is None:
                    return None
                html_parts.append("<p>%s</p>" % h)
            elif m.group(2) is not None:
                lis = re.findall(r"<li>(.*?)</li>", m.group(2), re.S)
                conv = [_inline(x) for x in lis]
                if any(x is None for x in conv):
                    return None
                html_parts.append("<ul>%s</ul>" % "".join("<li>%s</li>" % x for x in conv))
            else:
                html_parts.append('<p data-ph="1">%s</p>' % rich._h(m.group(3)))
            pos = m.end()
        if parts[pos:].strip():
            return None

        def people(raw, key):
            if rich.TODO_RE.fullmatch(raw.strip()):
                return _setpf(b, key, raw)
            chips = re.findall(r'<span style="display:inline-block;background:#f3f2f1;[^"]*">(.*?)</span>', raw, re.S)
            return "; ".join(_plain(x) for x in chips) if chips else _plain(raw)
        em = {"from": _setpf(b, "emails.%d.from" % n, frm), "sent": _setpf(b, "emails.%d.sent" % n, sent),
              "to": people(to, "emails.%d.to" % n), "cc": people(cc, "emails.%d.cc" % n),
              "subject": _setpf(b, "emails.%d.subject" % n, subj), "html": "".join(html_parts)}
        subjects.append("" if "emails.%d.subject" % n in b.get("ph", {}) else em["subject"])
        b["emails"].append(em)
    shown, isph = _pfield(head.group(1))
    if not isph and shown != hs.thread_subject(subjects):
        b["caption"] = shown
    return b


def r_hr(c):
    return B("divider") if re.fullmatch(r"<hr[^>]*/?>", c.strip()) else None


# ---------------------------------------------------------------- tokenizer
BLOCK_START = re.compile(r"^\s*(<div\b|<h[23]\b|<hr\b|\{\||<pre\b|==)", re.I)


def _take_html(lines, i):
    """Collect lines until <div>/</div> (and <h2>/<h3>) balance."""
    depth = 0
    j = i
    while j < len(lines):
        l = lines[j]
        depth += len(re.findall(r"<(div|h2|h3)\b", l, re.I)) - len(re.findall(r"</(div|h2|h3)>", l, re.I))
        j += 1
        if depth <= 0:
            break
    return "\n".join(lines[i:j]), j


def chunks(text):
    """Split page wikitext into ('html'|'table'|'pre'|'head'|'text'|'cat'|'magic'|'comment', str) chunks."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        s = l.strip()
        if not s:
            i += 1
            continue
        if re.fullmatch(r"(__(?:NO)?TOC__\s*)+(__NOEDITSECTION__)?|__NOEDITSECTION__", s):
            out.append(("magic", s))
            i += 1
            continue
        if re.fullmatch(r"(\[\[Category:[^\]]+\]\]\s*)+", s, re.I):
            out.append(("cat", s))
            i += 1
            continue
        if re.match(r"^\s*<(div|h2|h3)\b", l, re.I) or re.match(r"^\s*<hr\b", l, re.I):
            c, i = _take_html(lines, i)
            out.append(("html", c))
            continue
        if s.startswith("{|"):
            j = i
            depth = 0
            while j < len(lines):
                if lines[j].strip().startswith("{|"):
                    depth += 1
                if lines[j].strip() == "|}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append(("table", "\n".join(lines[i:j + 1])))
            i = j + 1
            continue
        if re.match(r"^\s*<pre\b", l, re.I):
            j = i
            while j < len(lines) and "</pre>" not in lines[j].lower():
                j += 1
            out.append(("pre", "\n".join(lines[i:j + 1])))
            i = j + 1
            continue
        if re.match(r"^=+.*=+\s*$", s):
            out.append(("head", s))
            i += 1
            continue
        if re.fullmatch(r"<!--.*-->", s, re.S) and not rich.TODO_RE.fullmatch(s):
            out.append(("comment", s))
            i += 1
            continue
        j = i
        buf = []
        while j < len(lines):
            lj = lines[j]
            sj = lj.strip()
            if buf and sj and (BLOCK_START.match(lj) or re.fullmatch(r"(\[\[Category:[^\]]+\]\]\s*)+", sj, re.I)
                               or re.fullmatch(r"__(NO)?TOC__", sj)):
                break
            if not buf and not sj:
                j += 1
                continue
            if sj.startswith("<!--") and not sj.endswith("-->") and "-->" not in sj:
                k = j
                while k < len(lines) and "-->" not in lines[k]:
                    k += 1
                buf += lines[j:k + 1]
                j = k + 1
                continue
            buf.append(lj)
            j += 1
        while buf and not buf[-1].strip():
            buf.pop()
        out.append(("text", "\n".join(buf)))
        i = j
    return out


def _text_blocks(t):
    """A run of plain wikitext -> blocks. Each paragraph is tried on its own, so one
    paragraph we can't edit doesn't drag its neighbours into a "Wiki code" block."""
    blocks = []
    for p in re.split(r"\n\s*\n", t.strip("\n")):
        pm = re.fullmatch(r"<!--\s*TODO:\s*add a picture here(?: \((.*)\))?\s*-->", p.strip())
        if pm:
            blocks.append(B("image", file="", full="", caption=pm.group(1) or ""))
            continue
        fm = FILE_RE.fullmatch(p.strip())
        if fm:
            name, full, cap = _file_parts(fm)
            blocks.append(B("image", file=name, full=full, caption=cap))
            continue
        h = _rich(p)
        if h is None:
            k = keep(p)
            if k["type"] == "raw" and blocks and blocks[-1]["type"] == "raw":
                blocks[-1]["wiki"] += "\n\n" + p
            else:
                blocks.append(k)
        elif blocks and blocks[-1]["type"] == "text":
            blocks[-1]["html"] += h
        else:
            blocks.append(B("text", html=h))
    return blocks


def import_wiki(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    doc = {"title": "", "summary": "", "toc": True, "categories": [], "blocks": []}
    lines = text.split("\n")
    if lines and re.match(r'^<div style="display:\s*none;?">(.*)</div>\s*$', lines[0]):
        hid = re.match(r'^<div style="display:\s*none;?">(.*)</div>\s*$', lines[0]).group(1)
        hid = _plain(hid)
        m = re.match(r"^(.*?)\.\s+(.*)$", hid)
        if m:
            doc["title"], doc["summary"] = m.group(1).strip(), m.group(2).strip()
        else:
            doc["title"] = hid.rstrip(".")
        text = "\n".join(lines[1:])
    blocks = doc["blocks"]
    toc_seen = notoc = False
    ch = chunks(text)
    k = 0
    while k < len(ch):
        kind, c = ch[k]
        nxt = ch[k + 1][1] if k + 1 < len(ch) and ch[k + 1][0] == "html" else None
        k += 1
        if kind == "magic":
            toc_seen = toc_seen or "__TOC__" in c
            notoc = notoc or "__NOTOC__" in c
            if "__NOEDITSECTION__" in c:
                blocks.append(B("raw", wiki="__NOEDITSECTION__"))
            continue
        if kind == "cat":
            doc["categories"] += [x.strip() for x in re.findall(r"\[\[Category:([^\]|]+)", c, re.I)]
            continue
        if kind == "head":
            m = re.match(r"^(=+)\s*(.*?)\s*\1\s*$", c)
            if m and len(m.group(1)) in (2, 3) and "<" not in m.group(2):
                blocks.append(B("h2" if len(m.group(1)) == 2 else "h3", text=_plain(m.group(2)), color="navy"))
            else:
                blocks.append(keep(c))     # ==== deeper headings ==== keep their level, text editable
            continue
        if kind == "pre":
            m = re.match(r"^\s*<pre[^>]*>\n?(.*?)\n?</pre>\s*$", c, re.S | re.I)
            if m:
                code = _html.unescape(re.sub(r"</?nowiki>", "", m.group(1)))
                blocks.append(B("code", lang="sql" if re.search(r"\b(SELECT|FROM|EXEC|INSERT|UPDATE)\b", code, re.I) else "text", title="", code=code))
            else:
                blocks.append(B("raw", wiki=c))
            continue
        if kind == "table":
            blocks.append(r_table(c) or keep(c))
            continue
        if kind == "html" and re.fullmatch(r"<div>\s*</div>", c.strip()):
            continue    # an empty leftover box shows nothing on the wiki
        if kind == "html":
            em = r_email_one(c)
            capm = re.fullmatch(r'<div style="font:bold 105% sans-serif;color:#1f3a5f;margin:\.6em 0 \.3em;">(.*?)</div>', c.strip(), re.S)
            if capm and nxt and r_email_one(nxt):
                blocks.append(B("email", caption=_plain(capm.group(1)), emails=[]))
                continue
            if em:
                if not (blocks and blocks[-1]["type"] == "email"):
                    blocks.append(B("email", caption="", emails=[]))
                eb = blocks[-1]
                n = len(eb["emails"])
                for key in ("from", "sent", "to", "cc", "subject"):
                    em[key] = _setpf(eb, "emails.%d.%s" % (n, key), em[key])
                eb["emails"].append(em)
                continue
            got = None
            fig, used = r_figure(c, nxt)
            if fig:
                got = fig
                if used:
                    k += 1
            else:
                for f in (r_hero, r_heading, r_step, r_callout, r_card, r_cards, r_flow, r_flow_old, r_code, r_collapse, r_outlook, r_hr):
                    got = f(c)
                    if got:
                        break
            blocks.append(got or keep(c))
            continue
        if kind == "comment":
            blocks.append(B("raw", wiki=c))
            continue
        blocks.extend(_text_blocks(c))
    # keep the page's own choice: __TOC__ (True), __NOTOC__ (False), or neither (None: the wiki decides,
    # showing a contents box by itself on pages with four or more headings)
    doc["toc"] = True if toc_seen else (False if notoc else None)
    # step numbers: keep a number only where it doesn't follow on
    n = 0
    for b in blocks:
        if b["type"] == "h2":
            n = 0
        if b["type"] == "step":
            num = b.pop("_num", None)
            n = n + 1
            if num is not None and num != n:
                b["start"] = num
                n = num
    # hero title that just repeats the page title follows the page title
    for b in blocks:
        if b["type"] == "hero" and b.get("title") == doc["title"]:
            b["title"] = ""
    # merge neighbouring raw blocks so old markup stays together
    merged = []
    for b in blocks:
        if merged and b["type"] == "raw" and merged[-1]["type"] == "raw":
            merged[-1]["wiki"] += "\n" + b["wiki"]
        else:
            merged.append(b)
    doc["blocks"] = merged
    return doc


# ---------------------------------------------------------------- plain text / Word
def import_plain(text, title=""):
    """Plain text (or text read from Word) -> blocks. Headings written as == Heading ==,
    numbered lines (1. 2. 3.) become steps, '* ' lines become bullets, indented lines
    become a code box and tab-separated lines become a table."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    i = 0
    para = []

    def flush():
        if para:
            body = "\n".join(para).strip()
            if body:
                h = _rich(_escape_plain(body))
                blocks.append(B("text", html=h) if h is not None else B("raw", wiki=body))
            para.clear()

    while i < len(lines):
        l = lines[i]
        s = l.strip()
        m = re.match(r"^(={2,3})\s*(.*?)\s*\1\s*$", s)
        if m:
            flush()
            blocks.append(B("h2" if len(m.group(1)) == 2 else "h3", text=m.group(2), color="blue"))
            i += 1
            continue
        if re.match(r"^\d+[.)]\s+", s) and not l.startswith("    "):
            flush()
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()) and not lines[i].startswith("    "):
                body = re.sub(r"^\d+[.)]\s+", "", lines[i].strip())
                h = _inline(_escape_plain(body)) or rich._h(body)
                blocks.append(B("step", html="<p>%s</p>" % h, color="blue"))
                i += 1
            continue
        if l.startswith("    ") and s:
            flush()
            code = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                code.append(lines[i][4:])
                i += 1
            while code and not code[-1].strip():
                code.pop()
            body = "\n".join(code)
            blocks.append(B("code", lang="sql" if re.search(r"\b(SELECT|FROM|EXEC|INSERT|UPDATE|DECLARE)\b", body, re.I) else "text", title="", code=body))
            continue
        if "\t" in l and s:
            flush()
            rows = []
            while i < len(lines) and "\t" in lines[i]:
                rows.append([rich._h(x.strip()) for x in lines[i].split("\t")])
                i += 1
            blocks.append(B("table", rows=rows, header=True, keyval=False, color="navy"))
            continue
        if re.fullmatch(r"<!--.*-->", s):
            flush()
            t = rich.TODO_RE.fullmatch(s)
            blocks.append(B("callout", kind="warning", title="To do:", html="<p>%s</p>" % rich._h(t.group(1))) if t else B("raw", wiki=s))
            i += 1
            continue
        if not s:
            flush()
            i += 1
            continue
        para.append(l.rstrip())
        i += 1
    flush()
    if not title and blocks and blocks[0]["type"] == "text":
        first = rich.plain(blocks[0]["html"])
        if len(first) < 90 and "\n" not in first:
            title = first
            blocks.pop(0)
    return {"title": title, "summary": "", "toc": True, "categories": [], "blocks": blocks}


def _escape_plain(s):
    """Plain text going through the wiki reader: protect characters that would be read as markup."""
    out = []
    for line in s.split("\n"):
        if re.match(r"^\s*[*#]\s", line):
            out.append(line)        # keep bullets
            continue
        line = rich.safe_line(line)
        out.append(line)
    s = "\n".join(out)
    return s.replace("<", "&lt;").replace(">", "&gt;").replace("&lt;br /&gt;", "<br />")
