"""
rich.py - converts the editor's rich text (a small, safe subset of HTML) to
wikitext, and wikitext back to that HTML.

The editor only ever produces these tags: p, br, b/strong, i/em, u, s, code,
a, ul, ol, li, sub, sup and two kinds of span:
  <span data-pill="green">Live</span>    a coloured status pill
  <span data-ph="1">Prompt text</span>   a template prompt nobody has filled in
  (p, li and td can also carry data-ph="1")
Anything else that arrives (for example from a paste) is reduced to its text.
"""
import html as _html
import re
from html.parser import HTMLParser

import house_style as hs

VOID = {"br", "hr", "img", "input", "wbr", "meta", "link", "col", "source"}
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "section", "article",
         "header", "footer", "table", "tr", "td", "th", "tbody", "thead", "figure", "figcaption", "dl", "dt", "dd"}
LIST = {"ul", "ol"}
SKIP = {"script", "style", "head", "title", "template", "noscript"}
BR = "\x00BR\x00"


class Node:
    __slots__ = ("tag", "attrs", "kids")

    def __init__(self, tag, attrs=None):
        self.tag, self.attrs, self.kids = tag, dict(attrs or {}), []

    def text(self):
        out = []
        for k in self.kids:
            if isinstance(k, str):
                out.append(k)
            elif k.tag == "br":
                out.append(" ")
            else:
                out.append(k.text())
        return "".join(out)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        n = Node(tag, attrs)
        self.stack[-1].kids.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        if self.skip or tag in SKIP:
            return
        self.stack[-1].kids.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not self.skip:
            self.stack[-1].kids.append(data)


def parse(src):
    t = _Tree()
    t.feed(src or "")
    t.close()
    return t.root


# ------------------------------------------------------------------ escaping
def esc_text(s, cell=False):
    s = s.replace("\xa0", " ").replace("​", "")
    s = re.sub(r"&(?=#?\w+;)", "&amp;", s)
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    # wiki markup typed or shown as text stays text: [[ ]] {{ }} '' and [http...]
    s = re.sub(r"\[(?=\[)|\[(?=(?:https?|ftp|mailto):)", "&#91;", s)
    s = re.sub(r"\](?=\])", "&#93;", s)
    s = re.sub(r"\{(?=\{)", "&#123;", s)
    s = re.sub(r"\}(?=\})", "&#125;", s)
    s = re.sub(r"'(?=')", "&#39;", s)
    s = re.sub(r"~{3,}", lambda m: "~" + "&#126;" * (len(m.group(0)) - 1), s)
    s = re.sub(r"__([A-Z]+)__", r"_&#95;\1_&#95;", s)
    if cell:
        s = s.replace("|", "&#124;").replace("!!", "!&#33;")
    return s


LINE_START = {"*": "&#42;", "#": "&#35;", ":": "&#58;", ";": "&#59;", "=": "&#61;", "{": "&#123;",
              "|": "&#124;", "!": "&#33;", "-": "&#45;"}


def safe_line(line):
    line = line.lstrip(" \t")
    if line[:1] in LINE_START and not line.startswith("<!--"):
        if line[0] == "-" and not line.startswith("----"):
            return line
        return LINE_START[line[0]] + line[1:]
    return line


def ph_comment(text):
    t = re.sub(r"\s+", " ", (text or "").replace("--", "- ")).strip()
    return "<!-- TODO: %s -->" % t if t else ""


# ------------------------------------------------------------------ HTML -> wiki
def _wrap(mark, inner):
    if not inner.strip():
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()):]
    return "%s%s%s%s%s" % (lead, mark, inner.strip(), mark, trail)


def _wrap_tag(tag, inner):
    if not inner.strip():
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()):]
    return "%s<%s>%s</%s>%s" % (lead, tag, inner.strip(), tag, trail)


def _link(href, inner, plain):
    href = (href or "").strip()
    if not href:
        return inner
    if href.startswith("wiki:"):
        page = href[5:].strip()
        if not page:
            return inner
        if plain.strip() == page:
            return "[[%s]]" % page
        return "[[%s|%s]]" % (page, inner.strip() or page)
    if re.match(r"^(https?|ftp|mailto|file):", href, re.I):
        href = href.replace(" ", "%20").replace("[", "%5B").replace("]", "%5D")
        if plain.strip() in ("", href):
            return href
        return "[%s %s]" % (href, inner.strip())
    # anything else (e.g. typed "Page name") is treated as a wiki page
    return "[[%s|%s]]" % (href, inner.strip() or href)


def inline(node, cell=False, ctx=None):
    ctx = ctx or {"b": False, "i": False}
    out = []
    for k in node.kids:
        if isinstance(k, str):
            # keep_spaces: text that lines up in columns (inside a pre-wrap box) keeps its spaces
            out.append(esc_text(re.sub(r"[\t\r\n]+" if ctx.get("ks") else r"[ \t\r\n]+", " ", k), cell))
            continue
        t = k.tag
        a = k.attrs
        if "data-ph" in a:
            out.append(ph_comment(k.text()))
            continue
        if t == "br":
            out.append(BR)
        elif t in ("b", "strong"):
            if ctx["b"]:
                out.append(inline(k, cell, ctx))
            else:
                ctx["b"] = True
                out.append(_wrap("'''", inline(k, cell, ctx)))
                ctx["b"] = False
        elif t in ("i", "em"):
            if ctx["i"]:
                out.append(inline(k, cell, ctx))
            else:
                ctx["i"] = True
                out.append(_wrap("''", inline(k, cell, ctx)))
                ctx["i"] = False
        elif t in ("u", "ins"):
            inner = inline(k, cell, ctx)
            if inner.strip():
                lead = inner[: len(inner) - len(inner.lstrip())]
                trail = inner[len(inner.rstrip()):]
                inner = '%s<span style="text-decoration:underline;">%s</span>%s' % (lead, inner.strip(), trail)
            out.append(inner)
        elif t in ("s", "strike", "del"):
            out.append(_wrap_tag("s", inline(k, cell, ctx)))
        elif t in ("sub", "sup"):
            out.append(_wrap_tag(t, inline(k, cell, ctx)))
        elif t in ("code", "kbd", "tt", "samp"):
            txt = k.text().replace("\xa0", " ")
            if txt.strip():
                out.append("<code>%s</code>" % hs.code_esc(txt))
        elif t == "a":
            out.append(_link(a.get("href"), inline(k, cell, ctx), k.text()))
        elif t == "span" and a.get("data-pill"):
            txt = esc_text(k.text().strip(), cell)
            if txt:
                out.append(hs.pill(txt, a.get("data-pill") if a.get("data-pill") in hs.COLOURS else "green"))
        elif t in ("img", "hr", "input"):
            continue
        else:
            out.append(inline(k, cell, ctx))
    return "".join(out)


def _tidy_inline(s, keep_spaces=False):
    if not keep_spaces:
        s = re.sub(r" {2,}", " ", s)
    s = s.replace(" " + BR, BR).replace(BR + " ", BR)
    return s.strip(" ")


def _strip_br(s):
    """Drop line breaks at the start and end. (str.strip(BR) would also eat the
    letters B and R, since strip takes a set of characters.)"""
    s = s.strip()
    while s.startswith(BR):
        s = s[len(BR):].strip()
    while s.endswith(BR):
        s = s[:-len(BR)].strip()
    return s


def _list_lines(node, prefix, cell=False):
    lines = []
    for li in node.kids:
        if isinstance(li, str):
            if li.strip():
                lines.append(prefix + " " + esc_text(li.strip(), cell))
            continue
        if li.tag in LIST:  # badly nested list straight inside a list
            lines += _list_lines(li, prefix + ("#" if li.tag == "ol" else "*"), cell)
            continue
        if "data-ph" in li.attrs:
            lines.append(prefix + " " + ph_comment(li.text()))
            continue
        holder = Node("span")
        nested = []
        for k in li.kids:
            if not isinstance(k, str) and k.tag in LIST:
                nested.append(k)
            elif not isinstance(k, str) and k.tag in BLOCK:
                if holder.kids:
                    holder.kids.append(Node("br"))
                holder.kids.extend(k.kids)
            else:
                holder.kids.append(k)
        text = _strip_br(_tidy_inline(inline(holder, cell))).replace(BR, "<br />")
        if text:
            lines.append(prefix + " " + text)
        for n in nested:
            lines += _list_lines(n, prefix + ("#" if n.tag == "ol" else "*"), cell)
    return lines


def to_chunks(src, cell=False, keep_spaces=False):
    """Rich HTML -> list of chunks: ('p', wikitext with <br />) | ('list', [lines]) | ('todo', text)."""
    root = parse(src)
    chunks = []
    cur = Node("p")

    def flush():
        nonlocal cur
        if cur.kids:
            text = _tidy_inline(inline(cur, cell, {"b": False, "i": False, "ks": keep_spaces}), keep_spaces)
            parts = [p.strip() for p in text.split(BR)]
            while parts and not parts[0]:
                parts.pop(0)
            while parts and not parts[-1]:
                parts.pop()
            if parts:
                chunks.append(("p", parts))
        cur = Node("p")

    def walk(node):
        for k in node.kids:
            if isinstance(k, str):
                cur.kids.append(k)
                continue
            if "data-ph" in k.attrs and (k.tag in BLOCK or k.tag == "li"):
                flush()
                chunks.append(("todo", k.text()))
            elif k.tag in LIST:
                flush()
                lines = _list_lines(k, "#" if k.tag == "ol" else "*", cell)
                if lines:
                    chunks.append(("list", lines))
            elif k.tag in BLOCK:
                flush()
                if k.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    b = Node("b")
                    b.kids = k.kids
                    cur.kids.append(b)
                    flush()
                else:
                    walk(k)
                    flush()
            else:
                cur.kids.append(k)
    walk(root)
    flush()
    return chunks


def to_wiki(src, cell=False):
    """Rich HTML -> block wikitext (paragraphs separated by blank lines)."""
    out = []
    for kind, val in to_chunks(src, cell):
        if kind == "p":
            out.append(safe_line("<br />".join(val)))
        elif kind == "list":
            out.append("\n".join(val))
        elif kind == "todo":
            c = ph_comment(val)
            if c:
                out.append(c)
    return "\n\n".join(x for x in out if x.strip())


def to_inline(src, cell=False, keep_spaces=False):
    """Rich HTML -> one line of wikitext (paragraphs and list items joined with <br />)."""
    parts = []
    for kind, val in to_chunks(src, cell, keep_spaces):
        if kind == "p":
            parts.append("<br />".join(val))
        elif kind == "list":
            for l in val:
                m = re.match(r"^([*#]+)\s*(.*)$", l)
                depth = len(m.group(1)) - 1
                parts.append("&nbsp;" * (3 * depth) + "&bull; " + m.group(2))
        elif kind == "todo":
            parts.append(ph_comment(val))
    return "<br />".join(p for p in parts if p)


def is_simple(src):
    """True when the rich text is a single plain paragraph (so it can sit inline in a callout)."""
    ch = to_chunks(src)
    return len(ch) == 1 and ch[0][0] == "p" and len(ch[0][1]) == 1


def plain(src):
    return re.sub(r"\s+", " ", parse(src).text()).strip()


def has_ph(src):
    return 'data-ph' in (src or "")


def ph_texts(src):
    out = []

    def walk(n):
        for k in n.kids:
            if isinstance(k, str):
                continue
            if "data-ph" in k.attrs:
                out.append(re.sub(r"\s+", " ", k.text()).strip())
            else:
                walk(k)
    walk(parse(src))
    return out


# ------------------------------------------------------------------ wiki -> HTML
# tags MediaWiki treats as HTML or as extension tags; any other <word> is shown as text (e.g. <DATA_NAME>)
HTML_TAGS = {"abbr", "b", "bdi", "bdo", "big", "blockquote", "br", "caption", "center", "cite", "code", "data", "dd", "del",
             "dfn", "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "ins", "kbd", "li", "link",
             "mark", "meta", "ol", "p", "pre", "q", "rb", "rp", "rt", "rtc", "ruby", "s", "samp", "small", "span", "strike",
             "strong", "sub", "sup", "table", "td", "th", "time", "tr", "tt", "u", "ul", "var", "wbr", "thead", "tbody", "tfoot",
             "img", "a", "section", "col", "colgroup"}
EXT_TAGS = {"nowiki", "gallery", "ref", "references", "syntaxhighlight", "source", "math", "chem", "ce", "poem", "timeline",
            "templatestyles", "includeonly", "noinclude", "onlyinclude", "graph", "imagemap", "inputbox", "categorytree",
            "charinsert", "hiero", "score", "indicator", "mapframe", "maplink", "langconvert", "tabber", "tabs",
            "embedvideo", "html", "rss", "dpl", "dynamicpagelist", "youtube", "video", "comments", "translate",
            "languages", "tvar", "div"}
NOT_A_TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9_.:-]*)\b[^<>]*>")


def literal_tags(s, keep):
    """<DATA_NAME>, <timestamp> and the like are not tags: the wiki shows them as text."""
    def one(m):
        name = m.group(1).lower()
        return m.group(0) if (name in HTML_TAGS or name in EXT_TAGS) else keep(_h(m.group(0)))
    return NOT_A_TAG.sub(one, s)


PILL_RE = re.compile(r'<span style="display:inline-block;background:(#[0-9a-fA-F]{6});color:#fff;font:bold 80% sans-serif;padding:\.1em \.6em;border-radius:99px;">(.*?)</span>')
TODO_RE = re.compile(r"<!--\s*TODO:\s*(.*?)\s*-->", re.S)
ALLOWED_TAGS = {"code", "br", "s", "u", "sub", "sup", "span", "b", "i", "strong", "em", "del"}


class Unsupported(Exception):
    pass


def _h(s):
    return _html.escape(_html.unescape(s), quote=False)


def inline_to_html(s):
    """One run of wikitext inline markup -> editor HTML. Raises Unsupported for things we cannot represent."""
    tokens = []

    def keep(h):
        tokens.append(h)
        return "\x01%d\x02" % (len(tokens) - 1)

    # <nowiki>: the text inside is shown exactly as written (even <!-- -->)
    s = re.sub(r"<nowiki\s*/>", "", s, flags=re.I)
    s = re.sub(r"<code><nowiki>(.*?)</nowiki></code>", lambda m: keep("<code>%s</code>" % _h(m.group(1))), s, flags=re.S | re.I)
    s = re.sub(r"<nowiki>(.*?)</nowiki>", lambda m: keep(_h(m.group(1))), s, flags=re.S | re.I)
    s = TODO_RE.sub(lambda m: keep('<span data-ph="1">%s</span>' % _h(m.group(1))), s)
    if "<!--" in s:
        raise Unsupported("comment")
    s = re.sub(r"<code>(.*?)</code>", lambda m: keep("<code>%s</code>" % _h(re.sub(r"\x01(\d+)\x02", lambda k: _html.unescape(re.sub(r"<[^>]+>", "", tokens[int(k.group(1))])), m.group(1)))), s, flags=re.S)
    s = PILL_RE.sub(lambda m: keep('<span data-pill="%s">%s</span>' % (hs.COLOUR_NAMES.get(m.group(1).lower(), "green"), _h(m.group(2)))), s)
    s = re.sub(r"<br\s*/?>", lambda m: keep("<br>"), s, flags=re.I)

    def wl(m):
        target, label = m.group(1), m.group(2)
        if re.match(r"^\s*(File|Image|Category)\s*:", target, re.I):
            raise Unsupported("file or category link")
        label = label if label is not None else target
        return keep('<a href="wiki:%s">%s</a>' % (_html.escape(target.strip(), quote=True), _h(label)))
    s = re.sub(r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]", wl, s)
    s = re.sub(r"\[((?:https?|ftp|mailto|file):[^\s\]]+)\s+([^\]]+)\]",
               lambda m: keep('<a href="%s">%s</a>' % (_html.escape(m.group(1), quote=True), _h(m.group(2)))), s)
    s = re.sub(r'<span style="text-decoration:\s*underline;?">(.*?)</span>', lambda m: keep("<u>") + m.group(1) + keep("</u>"), s, flags=re.S)
    for tag, out_tag in (("s", "s"), ("u", "u"), ("sub", "sub"), ("sup", "sup"), ("b", "b"), ("strong", "b"), ("i", "i"), ("em", "i")):
        s = re.sub(r"<%s>(.*?)</%s>" % (tag, tag), lambda m, t=out_tag: keep("<%s>" % t) + m.group(1) + keep("</%s>" % t), s, flags=re.S)
    s = literal_tags(s, keep)
    if re.search(r"<\s*/?\s*[a-zA-Z]", s) or "{{" in s or "{|" in s:
        raise Unsupported("html or template")
    # bold / italic (MediaWiki style toggles)
    out, b, i = [], False, False
    for part in re.split(r"('{5}|'{3}|'{2})", s):
        if part == "'''''":
            if b and i:
                out.append("</i></b>"); b = i = False
            else:
                out.append("<b><i>"); b = i = True
        elif part == "'''":
            out.append("</b>" if b else "<b>"); b = not b
        elif part == "''":
            out.append("</i>" if i else "<i>"); i = not i
        else:
            out.append(_h(part))
    if i:
        out.append("</i>")
    if b:
        out.append("</b>")
    res = "".join(out)
    for _ in range(4):     # tokens can hold tokens (a <nowiki> inside <code>)
        if "\x01" not in res:
            break
        res = re.sub(r"\x01(\d+)\x02", lambda m: tokens[int(m.group(1))], res)
    return res


def wiki_to_html(text):
    """Block wikitext (paragraphs and * # lists) -> editor rich HTML."""
    text = (text or "").strip("\n")
    if not text.strip():
        return ""
    out = []
    para = []
    lst = []

    def flush_para():
        if para:
            joined = " ".join(x.strip() for x in para)
            m = TODO_RE.fullmatch(joined.strip())
            if m:
                out.append('<p data-ph="1">%s</p>' % _h(m.group(1)))
            else:
                out.append("<p>%s</p>" % inline_to_html(joined))
            para.clear()

    def flush_list():
        if not lst:
            return
        tag = lambda ch: "ol" if ch == "#" else "ul"
        h, prev = [], ""
        for prefix, body in lst:
            common = 0
            while common < min(len(prev), len(prefix)) and prev[common] == prefix[common]:
                common += 1
            for ch in reversed(prev[common:]):
                h.append("</li></%s>" % tag(ch))
            m = TODO_RE.fullmatch(body.strip())
            item = ('<li data-ph="1">%s' % _h(m.group(1))) if m else ("<li>%s" % inline_to_html(body))
            if common == len(prefix):
                h.append("</li>" + item)
            else:
                for ch in prefix[common:-1]:
                    h.append("<%s><li>" % tag(ch))
                h.append("<%s>%s" % (tag(prefix[-1]), item))
            prev = prefix
        for ch in reversed(prev):
            h.append("</li></%s>" % tag(ch))
        out.append("".join(h))
        lst.clear()

    for line in text.split("\n"):
        m = re.match(r"^([*#]+)\s?(.*)$", line)
        if m:
            flush_para()
            lst.append((m.group(1), m.group(2)))
            continue
        flush_list()
        if not line.strip():
            flush_para()
            continue
        if re.match(r"^\s*[:;{|!=]", line) or line.startswith(" ") or line.strip().startswith("----"):
            raise Unsupported("line markup")
        para.append(line)
        if re.search(r"<br\s*/?>\s*$", line, re.I):
            para[-1] = line.rstrip()
    flush_para()
    flush_list()
    res = "".join(out)
    # a paragraph split over lines with <br /> joins: "a<br /> b" -> keep the break, drop the space
    return res.replace("<br> ", "<br>")
