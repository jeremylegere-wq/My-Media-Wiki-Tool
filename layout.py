"""
layout.py - keeps a layout the tool has no block for (boxes inside boxes, wiki
tables with merged or coloured cells, table diagrams, hand-made emails) exactly
as written, while letting people change the text inside it.

    blk = build(wikitext)    # a "layout" block, or None when it can't be done safely
    wiki = export(blk)       # the wikitext again, with any edited text put back

How it works: the wikitext is split into its frame (HTML tags and wiki table
lines, kept character for character) and the pieces of text in between. Each
piece of text that the editor can handle becomes an editable "leaf"; anything
else (pictures, templates) is kept as part of the frame. A leaf nobody changed
is written back exactly as it was, so an untouched layout comes back unchanged.
"""
import html as _html
import re

import rich

MARK = "%d"
MARK_RE = re.compile("(\\d+)")
LEAF_TAG = '<wst-leaf data-i="%d"></wst-leaf>'

# tags that live inside a piece of text (the editor understands them)
INLINE = {"code", "br", "s", "u", "sub", "sup", "b", "i", "strong", "em"}
# tags that make up the frame
FRAME = {"div", "span", "p", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "col", "colgroup",
         "h1", "h2", "h3", "h4", "h5", "h6", "center", "small", "big", "font", "blockquote", "ul", "ol", "li",
         "dl", "dt", "dd", "hr", "abbr", "cite", "q", "del", "ins", "tt", "kbd", "var", "samp", "mark", "section"}
VOID = {"br", "hr", "col"}
ATTRS_OK = {"style", "colspan", "rowspan", "align", "valign", "width", "height", "border", "cellpadding",
            "cellspacing", "title", "class"}

TOKEN = re.compile(r"<!--.*?-->|<nowiki\s*/>|<nowiki>.*?</nowiki>|<pre\b[^>]*>.*?</pre>|"
                   r"<(/?)([A-Za-z][A-Za-z0-9]*)((?:\s+[^<>]*?)?)\s*(/?)>", re.S | re.I)
UNDERLINE = re.compile(r'<span style="text-decoration:\s*underline;?">.*?</span>', re.S)
HEAD = re.compile(r"^(={1,6})[ \t]*(\S.*?)[ \t]*\1[ \t]*$")
ATTR = re.compile(r"""([A-Za-z-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s"'>|]+)""")
CELL_ATTRS = re.compile(r"""[ \t]*((?:[A-Za-z-]+\s*=\s*(?:"[^"]*"|'[^']*'|[\w#%.:-]+)[ \t]*)+)\|(?!\|)""")


class Bail(Exception):
    """Something we must not touch (extension tags, multi-line templates)."""


# ---------------------------------------------------------------- the view (what the editor shows)
def _clean_style(v):
    v = _html.unescape(v)
    if re.search(r"url\s*\(|expression\s*\(|javascript:|@import|behavior\s*:", v, re.I):
        return ""
    v = re.sub(r"position\s*:\s*fixed\s*;?", "", v, flags=re.I)
    return v


def view_attrs(raw):
    out = []
    for name, val in ATTR.findall(raw or ""):
        name = name.lower()
        if name not in ATTRS_OK:
            continue
        val = val[1:-1] if val[:1] in "\"'" else val
        if name == "style":
            val = _clean_style(val)
            if not val:
                continue
        if name == "class":
            # page classes (wikitable, mw-collapsible) must not pick up the editor's own styles
            out.append(' data-wclass="%s"' % _html.escape(val, quote=True))
            continue
        out.append(' %s="%s"' % (name, _html.escape(_html.unescape(val), quote=True)))
    return "".join(out)


# ---------------------------------------------------------------- splitting into frame and text
class _Split:
    def __init__(self, src):
        self.s = src
        self.segs = []          # ("frame", wiki, view) | ("text", wiki, in_cell, at_line_start)
        self.buf = []
        self.buf_start_line = True
        self.buf_in_cell = False
        self.consumed = 0       # characters of the source handed out so far
        self.styled = {}        # styled inline tags opened as frame, so their closing tag is frame too
        self.tables = []        # each: {"row": bool, "cell": tag or None}
        self.line_kind = None   # None | "cell" | "head" while on a table cell line

    # text and frame
    def text(self, t):
        if not self.buf:
            i = self.consumed
            self.buf_start_line = i == 0 or self.s[i - 1] == "\n"
            self.buf_in_cell = bool(self.tables and self.tables[-1]["cell"])   # decided where the text starts
        self.buf.append(t)
        self.consumed += len(t)

    def flush(self):
        if self.buf:
            self.segs.append(("text", "".join(self.buf), self.buf_in_cell, self.buf_start_line))
            self.buf = []

    def frame(self, wiki, view):
        self.flush()
        self.segs.append(("frame", wiki, view))
        self.consumed += len(wiki)

    # wiki tables
    def _close_cell(self):
        t = self.tables[-1]
        v = ""
        if t["cell"]:
            v += "</%s>" % t["cell"]
            t["cell"] = None
        return v

    def _close_row(self):
        t = self.tables[-1]
        v = self._close_cell()
        if t["row"]:
            v += "</tr>"
            t["row"] = False
        return v

    def _open_cell(self, tag, attrs):
        t = self.tables[-1]
        v = self._close_cell()
        if tag != "caption" and not t["row"]:
            v += "<tr>"
            t["row"] = True
        t["cell"] = tag
        return v + "<%s%s>" % (tag, view_attrs(attrs))

    def _cell_prefix(self, i, prefix, tag):
        """At a cell start: frame the prefix and any 'attrs |', return the new position."""
        j = i + len(prefix)
        m = CELL_ATTRS.match(self.s, j)
        line_end = self.s.find("\n", j)
        line_end = len(self.s) if line_end < 0 else line_end
        attrs = ""
        if m and m.end() <= line_end and "[[" not in m.group(1):
            attrs = m.group(1)
            j = m.end()
        self.frame(self.s[i:j], self._open_cell(tag, attrs))
        return j

    def table_line(self, i):
        """At the start of a line. Returns the new position if it was table markup, else None."""
        s = self.s
        k = i
        while k < len(s) and s[k] in " \t":
            k += 1
        rest = s[k:k + 2]
        line_end = s.find("\n", k)
        line_end = len(s) if line_end < 0 else line_end
        if rest == "{|":
            self.frame(s[i:line_end], "<table%s>" % view_attrs(s[k + 2:line_end]))
            self.tables.append({"row": False, "cell": None})
            return line_end
        if not self.tables:
            return None
        if rest == "|}":
            v = self._close_row() + "</table>"
            self.tables.pop()
            self.frame(s[i:k + 2], v)
            return k + 2
        if rest == "|-":
            v = self._close_row() + "<tr%s>" % view_attrs(s[k + 2:line_end])
            self.tables[-1]["row"] = True
            self.frame(s[i:line_end], v)
            return line_end
        if rest == "|+":
            self.line_kind = "cell"
            return self._cell_prefix(i, s[i:k + 2], "caption")
        if s[k:k + 1] == "!":
            self.line_kind = "head"
            return self._cell_prefix(i, s[i:k + 1], "th")
        if s[k:k + 1] == "|":
            self.line_kind = "cell"
            return self._cell_prefix(i, s[i:k + 1], "td")
        return None

    def heading_line(self, i):
        """== Heading == lines (any level): the = signs are frame, the words are text."""
        line_end = self.s.find("\n", i)
        line_end = len(self.s) if line_end < 0 else line_end
        m = HEAD.match(self.s[i:line_end])
        if not m or self.tables:
            return None
        lvl = len(m.group(1))
        self.frame(self.s[i:i + m.start(2)], "<h%d>" % lvl)
        self.text(m.group(2))
        self.frame(self.s[i + m.end(2):line_end], "</h%d>" % lvl)
        return line_end

    def run(self):
        s, i, n = self.s, 0, len(self.s)
        while i < n:
            if i == 0 or s[i - 1] == "\n":
                self.line_kind = None
                j = self.table_line(i)
                if j is None:
                    j = self.heading_line(i)
                if j is not None:
                    i = j
                    continue
            ch = s[i]
            if self.line_kind and (s.startswith("||", i) or (self.line_kind == "head" and s.startswith("!!", i))):
                i = self._cell_prefix(i, s[i:i + 2], "th" if self.line_kind == "head" else "td")
                continue
            if ch == "<":
                m = TOKEN.match(s, i)
                if not m:
                    self.text(ch)
                    i += 1
                    continue
                tok = m.group(0)
                low = tok[:9].lower()
                if tok.startswith("<!--"):
                    if rich.TODO_RE.fullmatch(tok):
                        self.text(tok)
                    else:
                        self.frame(tok, "")
                elif low.startswith("<nowiki"):
                    self.text(tok)
                elif low.startswith("<pre"):
                    inner = re.sub(r"^<pre\b[^>]*>|</pre>$", "", tok, flags=re.I)
                    inner = re.sub(r"</?nowiki>", "", inner)
                    self.frame(tok, '<pre class="lay-pre">%s</pre>' % _html.escape(_html.unescape(inner)))
                else:
                    close, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
                    if name in INLINE and close and self.styled.get(name):
                        self.styled[name] -= 1
                        self.frame(tok, "</%s>" % name)
                    elif name in INLINE and (name == "br" or close or not (attrs or "").strip()):
                        self.text(tok)
                    elif name in INLINE:
                        # a styled <sup>, <code> or <b>: part of the frame, with editable text inside
                        self.styled[name] = self.styled.get(name, 0) + 1
                        self.frame(tok, "<%s%s>" % (name, view_attrs(attrs)))
                    elif name == "span" and not close and (rich.PILL_RE.match(s, i) or UNDERLINE.match(s, i)):
                        mm = rich.PILL_RE.match(s, i) or UNDERLINE.match(s, i)
                        self.text(mm.group(0))
                        i = mm.end()
                        continue
                    elif name in FRAME:
                        if close:
                            v = "</%s>" % name
                        elif name in VOID:
                            v = "<%s%s>" % (name, view_attrs(attrs))
                        else:
                            v = "<%s%s>%s" % (name, view_attrs(attrs), "</%s>" % name if selfclose else "")
                        self.frame(tok, v)
                    elif name in rich.EXT_TAGS or name in rich.HTML_TAGS:
                        raise Bail("<%s>" % name)
                    else:
                        self.text(tok)      # <DATA_NAME> and the like: the wiki shows these as text
                i = m.end()
                continue
            if s.startswith("{{", i):
                j = _match_braces(s, i)
                if j < 0 or "\n" in s[i:j]:
                    raise Bail("template")
                self.text(s[i:j])
                i = j
                continue
            if s.startswith("[[", i):
                j = s.find("]]", i)
                if j < 0 or "\n" in s[i:j]:
                    self.text("[[")
                    i += 2
                    continue
                self.text(s[i:j + 2])
                i = j + 2
                continue
            # plain run up to the next character that matters
            j = i + 1
            while j < n and s[j] not in "<{[|!\n":
                j += 1
            if j < n and s[j] == "\n":
                j += 1
            self.text(s[i:j])
            i = j
        self.flush()
        if self.tables:
            raise Bail("unclosed table")
        return self.segs


def _match_braces(s, i):
    depth, j = 0, i
    while j < len(s) - 1:
        if s.startswith("{{", j):
            depth += 1
            j += 2
            continue
        if s.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j
            continue
        j += 1
    return -1


# ---------------------------------------------------------------- leaves
def _conv(mode, cell, ks=False):
    if mode == "block":
        return lambda h: rich.to_wiki(h, cell=cell)
    return lambda h: rich.safe_line(rich.to_inline(h, cell=cell, keep_spaces=ks))


def _keeps_spaces(core):
    return bool(re.search(r"\S {2,}\S", core))


def _leaf(core, mode, cell):
    """Editor HTML for a piece of text, or None when it has to stay as wiki code."""
    try:
        h = rich.wiki_to_html(core) if mode == "block" else rich.inline_to_html(core)
    except rich.Unsupported:
        return None
    text = rich.plain(h)
    if not text.strip() and not rich.has_ph(h):
        return None
    try:
        back = _conv(mode, cell, _keeps_spaces(core))(h)
        h2 = rich.wiki_to_html(back) if mode == "block" else rich.inline_to_html(back)
    except rich.Unsupported:
        return None
    if rich.plain(h2) != text:
        return None
    return h


def _fixed_view(core):
    try:
        h = rich.inline_to_html(core)
        if not rich.plain(h).strip():
            return h          # spacing, line breaks, &nbsp;
    except rich.Unsupported:
        pass
    m = re.fullmatch(r"\[\[(?:File|Image):([^|\]]+)[^\]]*\]\]", core.strip(), re.I)
    if m:
        return '<span class="lay-code" title="A picture. Use Edit wiki code to change it.">Picture: %s</span>' % _html.escape(m.group(1).strip())
    return '<span class="lay-code" title="Wiki code. Use Edit wiki code to change it.">%s</span>' % _html.escape(core)


def build(wiki):
    """Wikitext -> a layout block, or None."""
    src = (wiki or "").replace("\r\n", "\n").replace("\r", "\n")
    if not src.strip():
        return None
    try:
        segs = _Split(src).run()
    except Bail:
        return None
    tpl, view, leaves = [], [], []
    for seg in segs:
        if seg[0] == "frame":
            tpl.append(seg[1])
            view.append(seg[2])
            continue
        _, w, in_cell, line_start = seg
        core = w.strip()
        lead = w[: len(w) - len(w.lstrip())]
        trail = w[len(w.rstrip()):]
        if not core:
            tpl.append(w)
            view.append(w)
            continue
        starts_line = line_start or "\n" in lead
        mode = "block" if ("\n" in core or (starts_line and core[0] in "*#:;")) else "inline"
        h = _leaf(core, mode, in_cell)
        if h is None:
            tpl.append(w)
            view.append(lead + _fixed_view(core) + trail)
            continue
        n = len(leaves)
        lf = {"wiki": core, "html": h, "html0": h, "mode": mode, "cell": in_cell}
        if mode == "inline" and _keeps_spaces(core):
            lf["ks"] = True
        leaves.append(lf)
        tpl.append(lead + MARK % n + trail)
        view.append(lead + LEAF_TAG % n + trail)
    if not leaves:
        return None
    blk = {"type": "layout", "tpl": "".join(tpl), "view": "".join(view), "leaves": leaves}
    if export(blk) != src:      # safety net: untouched, it must give back exactly what came in
        return None
    return blk


def leaf_wiki(lf):
    conv = _conv(lf.get("mode"), bool(lf.get("cell")), bool(lf.get("ks")))
    html = lf.get("html") or ""
    new = conv(html)
    if lf.get("wiki") is not None and lf.get("html0") is not None:
        try:
            if new == conv(lf["html0"]):
                return lf["wiki"]
        except Exception:  # noqa: BLE001 - a damaged html0 just means "changed"
            pass
    return new


def export(b):
    leaves = b.get("leaves") or []

    def put(m):
        i = int(m.group(1))
        return leaf_wiki(leaves[i]) if i < len(leaves) and isinstance(leaves[i], dict) else ""
    return MARK_RE.sub(put, str(b.get("tpl") or ""))


def prompts(b):
    out = []
    for lf in b.get("leaves") or []:
        if isinstance(lf, dict) and rich.has_ph(lf.get("html", "")):
            out += rich.ph_texts(lf.get("html", ""))
    return out
