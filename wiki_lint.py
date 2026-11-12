"""
wiki_lint.py - offline checker and safe auto-fixer for Wiki pages (wikitext).

No AI and no network. Plain rules, so the same page always gives the same answer.

    issues = check(text, names={"Jane Citizen": "Manager, Application Development"})
    new_text, applied = fix(text, names=...)

Each issue is a dict: id, level ("error" | "warn" | "info"), line (1-based or 0),
message, fixable (True when fix() repairs it safely), text (short excerpt).
fix() only does mechanical repairs that cannot change what a page means.
"""
import re

CODE_DIV = re.compile(r'(<div style="[^"]*white-space:\s*pre-wrap[^"]*">)(.*?)(</div>)', re.S | re.I)
ALLOWED_IN_CODE = {"span", "br"}
LINE_START = {"*": "&#42;", "#": "&#35;", ":": "&#58;", ";": "&#59;", "=": "&#61;",
              "|": "&#124;", "!": "&#33;", "{": "&#123;", "-": "&#45;", " ": "&#32;"}
WIKI_HOST = r"https?://your-wiki\.example\.com/Wiki/(?:index\.php(?:/|\?title=))"
SMART = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
NAVY = "#1f3a5f"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?61[\s-]?|0)[2-478](?:[\s-]?\d){8}\b|\(0\d\)[\s-]?\d{4}[\s-]?\d{4}")
SECRET_RE = re.compile(r"^.*\b(password|passwd|pwd|secret|api[\s_-]?key|token|bearer)\b\s*[:=].*$", re.I | re.M)
SHARE_RE = re.compile(r"sharepoint\.com/[^\s]*(:[a-z]:|sharing|guestaccess|\?e=)", re.I)
H2_PLAIN = re.compile(r"^==\s*([^=].*?)\s*==\s*$", re.M)
H3_PLAIN = re.compile(r"^===\s*([^=].*?)\s*===\s*$", re.M)


PROTECT_RE = re.compile(r"<pre\b[^>]*>.*?</pre>|<nowiki>.*?</nowiki>|<!--.*?-->", re.S | re.I)


def _mask(text):
    """Blank out <pre>, <nowiki> and comments (keeping line numbers) for structural checks."""
    return PROTECT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _excerpt(s, n=70):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _strip_comments(text):
    return re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def _balance(text, open_re, close_re):
    return len(re.findall(open_re, text, re.I)), len(re.findall(close_re, text, re.I))


def _code_blocks(text):
    return list(CODE_DIV.finditer(text))


def check(text, names=None):
    names = names or {}
    issues = []

    def add(id_, level, line, message, fixable=False, excerpt=""):
        issues.append({"id": id_, "level": level, "line": line, "message": message,
                       "fixable": fixable, "text": _excerpt(excerpt)})

    if not text.strip():
        add("empty", "error", 0, "The page is empty.")
        return issues
    nocom = _strip_comments(text)      # content scans (contact details, secrets, names)
    struct = _mask(text)               # structure scans (ignore pre, nowiki, comments)
    lines = text.split("\n")

    # 1. hidden first line
    first = lines[0]
    m = re.match(r'^<div style="display:none">(.*)</div>\s*$', first)
    if not m:
        add("hidden-missing", "error", 1,
            'The first line must be a hidden summary: <div style="display:none">PAGE TITLE. One or two plain sentences.</div>',
            False, first)
    else:
        inner = m.group(1)
        if re.search(r"[<>\[\]{}|=]", inner):
            add("hidden-chars", "error", 1, "The hidden summary contains one of < > [ ] { } | = which breaks search.", True, inner)
        if len(inner) > 400:
            add("hidden-long", "warn", 1, "The hidden summary is long (over 400 characters). One or two sentences is enough.", False, inner)
        if "TODO" in inner:
            add("hidden-todo", "warn", 1, "The hidden summary still says TODO.", False, inner)

    # 2. balance of structures (code boxes are checked separately)
    nocom_all = nocom
    nocom = CODE_DIV.sub(lambda m: m.group(1) + m.group(3), struct)
    for tag in ("div", "span", "pre", "table", "ul", "ol", "li", "code", "b", "i", "h2", "h3"):
        o, c = _balance(nocom, r"<%s[\s>]" % tag, r"</%s\s*>" % tag)
        if o != c:
            add("unbalanced-" + tag, "error", 0, "Unbalanced <%s>: %d opening and %d closing." % (tag, o, c))
    o = len(re.findall(r"^\s*\{\|", nocom, re.M))
    c = len(re.findall(r"^\s*\|\}", nocom, re.M))
    if o != c:
        add("unbalanced-wikitable", "error", 0, "Unbalanced wiki table: %d {| and %d |}." % (o, c))
    if nocom.count("[[") != nocom.count("]]"):
        add("unbalanced-links", "error", 0, "Unbalanced links: %d [[ and %d ]]." % (nocom.count("[["), nocom.count("]]")))
    if nocom.count("{{") != nocom.count("}}"):
        add("unbalanced-templates", "error", 0, "Unbalanced templates: %d {{ and %d }}." % (nocom.count("{{"), nocom.count("}}")))
    content = nocom_all
    nocom = struct

    # 3. contact details, secrets, sharing links, names
    for mm in EMAIL_RE.finditer(content):
        add("email", "warn", _line_of(text, mm.start()), "Email address. Leave contact details off the wiki.", False, mm.group(0))
    for mm in PHONE_RE.finditer(content):
        add("phone", "warn", _line_of(text, mm.start()), "Phone number. Leave contact details off the wiki.", False, mm.group(0))
    for mm in SECRET_RE.finditer(content):
        add("secret", "error", _line_of(text, mm.start()), "Possible password, key or token. Remove it.", False, mm.group(0))
    for mm in SHARE_RE.finditer(content):
        add("sharepoint", "error", _line_of(text, mm.start()), "SharePoint sharing link. Name the folder in words instead.", False, mm.group(0))
    for name, role in names.items():
        for mm in re.finditer(re.escape(name), content, re.I):
            add("name", "warn", _line_of(text, mm.start()),
                'Personal name "%s". Use the role%s.' % (name, (' "%s"' % role) if role else ""),
                bool(role), mm.group(0))

    # 4. images
    for mm in re.finditer(r"\[\[(?:File|Image):[^\]]*\]\]", nocom, re.I):
        s = mm.group(0)
        if re.search(r"\|\s*\d+(?:x\d+)?px\s*(?=\||\])", s, re.I):
            add("img-width", "warn", _line_of(text, mm.start()),
                "Image has a width setting. Leave it off; images must be 700px or less already.", True, s)
        if re.search(r"\|\s*(thumb|thumbnail|frame)\s*(?=\||\])", s, re.I):
            add("img-thumb", "info", _line_of(text, mm.start()), "Image uses thumb or frame, which adds a box and may shrink it.", False, s)
    for mm in re.finditer(r"<img\b[^>]*>", nocom, re.I):
        w = re.search(r'width\s*[:=]\s*"?(\d+)', mm.group(0), re.I)
        if w and int(w.group(1)) > 700:
            add("img-wide", "error", _line_of(text, mm.start()), "Image wider than 700px.", False, mm.group(0))

    # 5. links to this wiki written as external links
    for mm in re.finditer(r"\[(" + WIKI_HOST + r"[^\s\]]+)(?:\s+([^\]]*))?\]", nocom):
        add("self-link", "info", _line_of(text, mm.start()), "Link to this wiki written as an external link. Use a normal [[Page]] link.", True, mm.group(0))
    for mm in re.finditer(r"\[\[\s", nocom):
        add("link-space", "warn", _line_of(text, mm.start()), "Space after [[ in a link.", True, text[mm.start():mm.start() + 30])

    # 6. headings
    h_levels = []
    for mm in re.finditer(r"^(={1,6})\s*(.*?)\s*\1\s*$", nocom, re.M):
        h_levels.append((len(mm.group(1)), mm.group(2), _line_of(text, mm.start())))
    for mm in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", nocom, re.S | re.I):
        h_levels.append((int(mm.group(1)), re.sub(r"<[^>]+>", "", mm.group(2)).strip(), _line_of(text, mm.start())))
    h_levels.sort(key=lambda x: x[2])
    seen = {}
    prev = 1
    for lvl, title, ln in h_levels:
        if lvl == 1:
            add("h1", "warn", ln, "Level-1 heading. The page title is already the top heading; start at level 2.", False, title)
        if lvl > prev + 1 and prev >= 2:
            add("h-skip", "warn", ln, "Heading jumps from level %d to %d." % (prev, lvl), False, title)
        if not title:
            add("h-empty", "warn", ln, "Empty heading.")
        k = title.lower()
        if k and k in seen:
            add("h-dup", "warn", ln, 'Heading "%s" is repeated (first on line %d).' % (title, seen[k]), False, title)
        seen.setdefault(k, ln)
        prev = lvl
    n_h2 = sum(1 for l in h_levels if l[0] == 2)
    plain2 = H2_PLAIN.findall(nocom)
    plain3 = H3_PLAIN.findall(nocom)
    if plain2 or plain3:
        add("plain-headings", "info", 0, "%d plain heading(s) (== ==) are not in the page style. Fix restyles them as navy bars." % (len(plain2) + len(plain3)), True)
    if n_h2 >= 3 and "__TOC__" not in nocom:
        add("toc", "warn", 0, "Three or more sections but no __TOC__.", True)
    if n_h2 == 0:
        add("no-h2", "info", 0, "No section headings.")

    # 7. code boxes
    for blk in _code_blocks(text):
        inner = blk.group(2)
        base_line = _line_of(text, blk.start(2))
        for off, ln in enumerate(inner.split("\n")):
            if off > 0 and ln and ln[0] in LINE_START:
                add("code-linestart", "error", base_line + off,
                    "Code line starts with \"%s\", which the wiki turns into a list, heading or table." % ln[0], True, ln)
        for mm in re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9]*)", inner):
            if mm.group(2).lower() not in ALLOWED_IN_CODE:
                add("code-tag", "error", base_line + inner.count("\n", 0, mm.start()),
                    "A < followed by a letter inside a code box is read as a tag. Use &lt;.", True, inner[mm.start():mm.start() + 30])
        plain = re.sub(r"<[^>]+>", "", inner)
        if any(ch in plain for ch in SMART):
            add("code-smart", "warn", base_line, "Smart quotes, dashes or non-breaking spaces inside a code box break copy and paste.", True)
        if re.search(r"\[\[|\]\]|\{\{|\}\}|''|~~~|__[A-Z]+__", plain):
            add("code-markup", "warn", base_line, "Wiki markup characters inside a code box ([[ {{ '' ~~~ __X__) will be interpreted.", True)
    for mm in re.finditer(r"<pre\b[^>]*>(.*?)</pre>", nocom_all, re.S | re.I):
        if re.search(r"<span\b", mm.group(1), re.I):
            add("pre-span", "info", _line_of(text, mm.start()),
                "<span> inside <pre> is shown as text, not colour. Fine when documenting code; otherwise use a styled code div.", False)

    # 8. leftovers and old markup
    for mm in re.finditer(r"\b(TBC|TBD|XXX+|lorem ipsum|insert here)\b", nocom, re.I):
        add("placeholder", "warn", _line_of(text, mm.start()), "Placeholder text left in the page.", False, mm.group(0))
    todos = re.findall(r"<!--\s*TODO", re.sub(r"<pre\b[^>]*>.*?</pre>|<nowiki>.*?</nowiki>", "", text, flags=re.S | re.I))
    if todos:
        add("todos", "info", 0, "%d hidden TODO comment(s) still to resolve." % len(todos))
    for mm in re.finditer(r"<(font|center|u|strike|blink|marquee)\b", nocom, re.I):
        add("old-tag", "warn", _line_of(text, mm.start()), "Old HTML tag <%s>. Use inline styles." % mm.group(1), False, mm.group(0))
    for mm in re.finditer(r'style="[^"]*%%[^"]*"', nocom):
        add("style-percent", "warn", _line_of(text, mm.start()),
            "A style has %% where % is meant, so the browser ignores that setting. Fix changes %% to %.", True, mm.group(0))
    for mm in re.finditer(r"\[http://", nocom):
        add("http", "info", _line_of(text, mm.start()), "Link uses http, not https.", False, text[mm.start():mm.start() + 40])
    if re.search(r"[ \t]+$", text, re.M):
        add("trailing-space", "info", 0, "Trailing spaces on some lines.", True)
    if re.search(r"\n{4,}", text):
        add("blank-lines", "info", 0, "More than two blank lines in a row.", True)
    if "[[Category:" not in text:
        add("no-category", "info", 0, "No [[Category:...]] on the page.")
    return issues


def _fix_code_div(m):
    open_, inner, close = m.group(1), m.group(2), m.group(3)
    # split into tags and text; keep allowed tags, escape the rest
    parts = re.split(r"(<[^>]*>)", inner)
    out = []
    for p in parts:
        if p.startswith("<") and p.endswith(">") and re.match(r"</?(span|br)\b", p, re.I):
            out.append(p)
            continue
        if p.startswith("<") and p.endswith(">"):
            p = p.replace("<", "&lt;").replace(">", "&gt;")
        else:
            p = re.sub(r"<(?=[A-Za-z/])", "&lt;", p)
        for k, v in SMART.items():
            p = p.replace(k, v)
        p = p.replace("[[", "&#91;&#91;").replace("]]", "&#93;&#93;").replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;").replace("''", "&#39;&#39;")
        p = p.replace("~~~", "&#126;~~").replace("__", "&#95;_")
        out.append(p)
    inner = "".join(out)
    lines = inner.split("\n")
    for i in range(1, len(lines)):
        if lines[i] and lines[i][0] in LINE_START:
            lines[i] = LINE_START[lines[i][0]] + lines[i][1:]
    return open_ + "\n".join(lines) + close


def _h2(t):
    # same as house_style.h2(t, "navy")
    return ('<h2 style="background:#eef1f5;border:0;border-left:8px solid %s;color:#111;font:bold 135%% sans-serif;'
            'margin:1.4em 0 .6em;padding:.45em .8em;border-radius:3px;">%s</h2>' % (NAVY, t))


def _h3(t):
    # same as house_style.h3(t, "navy")
    return ('<h3 style="border:0;border-bottom:2px solid %s;color:%s;font:bold 112%% sans-serif;'
            'margin:1.1em 0 .5em;padding:0 0 .25em;">%s</h3>' % (NAVY, NAVY, t))


def fix(text, names=None, restyle_headings=True):
    """Apply only the safe mechanical repairs. Returns (new_text, [what was done])."""
    names = names or {}
    done = []
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # <pre>, <nowiki> and comments are left exactly as written
    saved = []

    def _save(m):
        saved.append(m.group(0))
        return "\x00%d\x00" % (len(saved) - 1)
    t = PROTECT_RE.sub(_save, t)

    def note(msg, before, after):
        if before != after:
            done.append(msg)

    # hidden line characters
    lines = t.split("\n")
    m = re.match(r'^(<div style="display:none">)(.*)(</div>)\s*$', lines[0])
    if m and re.search(r"[<>\[\]{}|=]", m.group(2)):
        cleaned = re.sub(r"\s+", " ", re.sub(r"[<>\[\]{}|=]", " ", m.group(2))).strip()
        lines[0] = m.group(1) + cleaned + m.group(3)
        done.append("Removed forbidden characters from the hidden summary line")
        t = "\n".join(lines)

    # code boxes
    before = t
    t = CODE_DIV.sub(_fix_code_div, t)
    note("Escaped code-box characters (line starts, tags, smart quotes, wiki markup)", before, t)

    # image widths
    def img(mm):
        return re.sub(r"\|\s*\d+(?:x\d+)?px\s*(?=\||\])", "", mm.group(0), flags=re.I)
    before = t
    t = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", img, t, flags=re.I)
    note("Removed image width settings", before, t)

    # self links
    def selfl(mm):
        target = re.sub(r"%([0-9A-Fa-f]{2})", lambda x: chr(int(x.group(1), 16)), mm.group(1).split("index.php", 1)[-1].lstrip("/").replace("?title=", ""))
        target = target.replace("_", " ").split("&")[0]
        label = (mm.group(2) or "").strip()
        return "[[%s|%s]]" % (target, label) if label and label != target else "[[%s]]" % target
    before = t
    t = re.sub(r"\[(" + WIKI_HOST + r"[^\s\]]+)(?:\s+([^\]]*))?\]", selfl, t)
    note("Turned links to this wiki into normal [[links]]", before, t)
    before = t
    t = re.sub(r"\[\[\s+", "[[", t)
    note("Removed spaces after [[", before, t)

    # names to roles
    for name, role in names.items():
        if role:
            before = t
            t = re.sub(re.escape(name), role, t, flags=re.I)
            note('Replaced "%s" with "%s"' % (name, role), before, t)

    # plain headings
    if restyle_headings:
        before = t
        t = re.sub(r"^===\s*([^=].*?)\s*===\s*$", lambda mm: _h3(mm.group(1)), t, flags=re.M)
        t = re.sub(r"^==\s*([^=].*?)\s*==\s*$", lambda mm: _h2(mm.group(1)), t, flags=re.M)
        note("Restyled plain == headings", before, t)

    # TOC
    nocom = _strip_comments(t)
    n_h2 = len(re.findall(r"<h2\b", nocom, re.I)) + len(H2_PLAIN.findall(nocom))
    if n_h2 >= 3 and "__TOC__" not in nocom:
        mm = re.search(r"^(<h2\b|==[^=])", t, re.M)
        if mm:
            t = t[:mm.start()] + "__TOC__\n" + t[mm.start():]
            done.append("Added __TOC__ before the first section")

    # %% in styles (left over from a script) -> %
    before = t
    t = re.sub(r'style="[^"]*%%[^"]*"', lambda mm: mm.group(0).replace("%%", "%"), t)
    note("Changed %% to % in styles", before, t)

    # whitespace
    before = t
    t = re.sub(r"[ \t]+$", "", t, flags=re.M)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    note("Tidied trailing spaces and extra blank lines", before, t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], t)
    return t, done


def summary(issues):
    out = {"error": 0, "warn": 0, "info": 0}
    for i in issues:
        out[i["level"]] += 1
    return out
