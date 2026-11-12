"""
doc_import.py - reads Word (.docx) files into plain text that importer.import_plain()
turns into blocks, and email files (.eml, .msg) into email-thread blocks. Taken from the earlier Wiki Style Tool. Standard library only.
"""
import io
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser


class ToolError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CODE_FONTS = ("consolas", "courier", "lucida console", "menlo", "monaco")


def _on(el):
    if el is None:
        return False
    v = el.get(W + "val")
    return v is None or v.lower() not in ("0", "false", "off", "none")


def _load_numbering(zf):
    fmts, nums = {}, {}
    if "word/numbering.xml" not in zf.namelist():
        return fmts, nums
    root = ET.fromstring(zf.read("word/numbering.xml"))
    for an in root.findall(W + "abstractNum"):
        aid = an.get(W + "abstractNumId")
        for lvl in an.findall(W + "lvl"):
            fmt = lvl.find(W + "numFmt")
            fmts[(aid, lvl.get(W + "ilvl"))] = fmt.get(W + "val") if fmt is not None else "decimal"
    for num in root.findall(W + "num"):
        a = num.find(W + "abstractNumId")
        if a is not None:
            nums[num.get(W + "numId")] = a.get(W + "val")
    return fmts, nums


def _style_names(zf):
    names = {}
    if "word/styles.xml" in zf.namelist():
        root = ET.fromstring(zf.read("word/styles.xml"))
        for st in root.findall(W + "style"):
            n = st.find(W + "name")
            if n is not None:
                names[st.get(W + "styleId")] = n.get(W + "val", "").lower()
    return names


def _runs(p):
    runs = []
    for r in p.iter(W + "r"):
        rpr = r.find(W + "rPr")
        bold = italic = False
        code = False
        if rpr is not None:
            bold = _on(rpr.find(W + "b"))
            italic = _on(rpr.find(W + "i"))
            rf = rpr.find(W + "rFonts")
            if rf is not None:
                fn = (rf.get(W + "ascii") or rf.get(W + "hAnsi") or "").lower()
                code = any(c in fn for c in CODE_FONTS)
        text = ""
        for node in r:
            if node.tag == W + "t":
                text += node.text or ""
            elif node.tag in (W + "tab", W + "br", W + "cr"):
                text += " "
            elif node.tag == W + "noBreakHyphen":
                text += "-"
        if text:
            runs.append((text, bold, italic, code))
    return runs


def _wiki_runs(runs, plain=False):
    merged = []
    for text, b, i, c in runs:
        if merged and merged[-1][1:] == (b, i, c):
            merged[-1] = (merged[-1][0] + text, b, i, c)
        else:
            merged.append((text, b, i, c))
    out = ""
    for text, b, i, c in merged:
        if plain or not (b or i) or not text.strip():
            out += text
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        mark = "'''''" if (b and i) else ("'''" if b else "''")
        out += lead + mark + core + mark + trail
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def docx_to_text(data):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(zf.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ToolError("That does not look like a .docx file. Older .doc files need to be saved as .docx first.")
    fmts, nums = _load_numbering(zf)
    styles = _style_names(zf)
    body = root.find(W + "body")
    lines = []
    counters = {}
    prev_kind = None

    def emit(kind, text):
        nonlocal prev_kind
        joinable = kind in ("list", "code", "table") and prev_kind == kind
        if lines and not joinable:
            lines.append("")
        lines.append(text)
        prev_kind = kind

    if body is None:
        return ""
    for child in body:
        if child.tag == W + "p":
            ppr = child.find(W + "pPr")
            style_id = ""
            numpr = None
            if ppr is not None:
                ps = ppr.find(W + "pStyle")
                style_id = ps.get(W + "val") if ps is not None else ""
                numpr = ppr.find(W + "numPr")
            sname = styles.get(style_id, style_id).lower()
            if child.find(".//" + W + "drawing") is not None or child.find(".//{urn:schemas-microsoft-com:vml}imagedata") is not None:
                emit("p", "<!-- TODO: an image in the Word document was not carried over. Add it as a [[File:...]] line. -->")
            runs = _runs(child)
            text = _wiki_runs(runs)
            if not text:
                continue
            m = re.match(r"heading\s*(\d)", sname)
            if sname == "title":
                emit("p", text)
                continue
            if m:
                level = int(m.group(1))
                counters.clear()
                plain = _wiki_runs(runs, plain=True)
                emit("h", ("== %s ==" if level <= 2 else "=== %s ===") % plain)
                continue
            if all(r[3] for r in runs):
                emit("code", "    " + _wiki_runs(runs, plain=True))
                continue
            if numpr is not None and numpr.find(W + "numId") is not None and numpr.find(W + "numId").get(W + "val") != "0":
                nid = numpr.find(W + "numId").get(W + "val")
                il = numpr.find(W + "ilvl")
                lvl = il.get(W + "val") if il is not None else "0"
                fmt = fmts.get((nums.get(nid), lvl), "bullet")
                indent = "    " * int(lvl)
                if fmt == "bullet":
                    emit("list", "%s* %s" % (indent, text))
                else:
                    counters[(nid, lvl)] = counters.get((nid, lvl), 0) + 1
                    emit("list", "%s%d. %s" % (indent, counters[(nid, lvl)], text))
                continue
            if "list" in sname:
                if "number" in sname:
                    counters[("style", sname)] = counters.get(("style", sname), 0) + 1
                    emit("list", "%d. %s" % (counters[("style", sname)], text))
                else:
                    emit("list", "* " + text)
                continue
            emit("p", text)
        elif child.tag == W + "tbl":
            for tr in child.iter(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    parts = [_wiki_runs(_runs(p)) for p in tc.findall(W + "p")]
                    cells.append(" ".join(x for x in parts if x).replace("\t", " "))
                if any(cells):
                    emit("table", "\t".join(cells))
    return "\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------
# Email reading
# --------------------------------------------------------------------------
class _HtmlToText(HTMLParser):
    BLOCK = {"p", "div", "tr", "table", "h1", "h2", "h3", "h4", "ul", "ol", "blockquote"}

    def __init__(self):
        super().__init__()
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n* ")
        elif tag in self.BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(src):
    p = _HtmlToText()
    p.feed(src)
    return tidy_text("".join(p.out))


def tidy_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_FMT_DATES = [
    "%A, %d %B %Y %I:%M %p",
    "%A, %B %d, %Y %I:%M %p",
    "%A, %d %B %Y %H:%M",
    "%d %B %Y %I:%M %p",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
]


def parse_any_date(text):
    """Best effort. Returns a datetime or None."""
    if not text:
        return None
    text = text.strip()
    try:
        return parsedate_to_datetime(text)
    except Exception:
        pass
    cleaned = re.sub(r"\s+", " ", text).replace(" at ", " ")
    for fmt in _FMT_DATES:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def nice_date(dt):
    if dt is None:
        return ""
    try:
        if dt.tzinfo is not None:
            dt = dt.astimezone()
    except Exception:
        pass
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return "%s, %d %s %d:%02d %s" % (dt.strftime("%A"), dt.day, dt.strftime("%B %Y"), hour12, dt.minute, ampm)


def names_only(value):
    """'Jane Citizen <jane@x.com>; Sam <s@x.com>' -> 'Jane Citizen; Sam'"""
    if not value:
        return ""
    out = []
    for name, addr in getaddresses([value.replace(";", ",")]):
        label = name.strip().strip('"') or addr
        if label:
            out.append(label)
    return "; ".join(out)


_H = re.compile(r"^\s*(from|sent|date|to|cc|subject)\s*:\s*(.*)$", re.I)


def _is_header_start(lines, i):
    if not re.match(r"^\s*from\s*:", lines[i], re.I):
        return False
    following = [x for x in lines[i + 1 : i + 8] if x.strip()][:4]
    return any(re.match(r"^\s*(sent|date|to|subject)\s*:", x, re.I) for x in following)


def _strip_separators(lines):
    while lines and (not lines[-1].strip() or re.match(r"^\s*(-{3,}.*Original Message.*-{3,}|_{5,}|-{5,}|={5,})\s*$", lines[-1], re.I)):
        lines = lines[:-1]
    return lines


def split_thread(body):
    """Split a message body into [first message body, quoted earlier emails...].
    Returns (first_body, [ {from,sent,to,cc,subject,body}, ... ])"""
    lines = body.splitlines()
    starts = [i for i in range(len(lines)) if _is_header_start(lines, i)]
    if starts:
        first = "\n".join(_strip_separators(lines[: starts[0]])).strip()
        quoted = []
        for n, s in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(lines)
            seg = lines[s:end]
            hdr = {}
            j = 0
            while j < len(seg):
                m = _H.match(seg[j])
                if m and not (j > 0 and not seg[j].strip()):
                    hdr[m.group(1).lower()] = m.group(2).strip()
                    j += 1
                    continue
                if not seg[j].strip() and hdr:
                    j += 1
                break
            rest = "\n".join(_strip_separators(seg[j:])).strip()
            quoted.append({
                "from": names_only(hdr.get("from", "")),
                "sent": hdr.get("sent") or hdr.get("date", ""),
                "to": names_only(hdr.get("to", "")),
                "cc": names_only(hdr.get("cc", "")),
                "subject": hdr.get("subject", ""),
                "body": rest,
            })
        return first, quoted
    # Gmail style: "On <date> <name> wrote:" followed by > quoted lines
    for i, line in enumerate(lines):
        m = re.match(r"^\s*On (.+) wrote:\s*$", line)
        if m and i + 1 < len(lines) and any(x.lstrip().startswith(">") for x in lines[i + 1 : i + 4]):
            first = "\n".join(_strip_separators(lines[:i])).strip()
            rest = []
            for x in lines[i + 1 :]:
                rest.append(re.sub(r"^\s*>+ ?", "", x))
            quoted_body = "\n".join(rest).strip()
            return first, [{"from": "", "sent": re.sub(r"\s*<[^>]*>", "", m.group(1)).strip(), "to": "", "cc": "", "subject": "", "body": quoted_body}]
    return body.strip(), []


def thread_from_message(hdr, body, mode):
    """hdr: dict from/sent/to/cc/subject/ts. mode: split | latest | whole"""
    if mode == "whole":
        first, quoted = body.strip(), []
    else:
        first, quoted = split_thread(body)
    emails = [dict(hdr, body=first)]
    if mode == "split":
        for q in quoted:
            q.setdefault("ts", None)
            dt = parse_any_date(q.get("sent", ""))
            q["ts"] = dt.timestamp() if dt else None
            if not q.get("subject"):
                q["subject"] = hdr.get("subject", "")
            emails.append(q)
    return emails


def parse_eml(data, mode):
    msg = BytesParser(policy=policy.default).parsebytes(data)
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        body = ""
    else:
        content = part.get_content()
        body = html_to_text(content) if part.get_content_type() == "text/html" else tidy_text(content)
    dt = None
    try:
        dt = parsedate_to_datetime(str(msg["date"])) if msg["date"] else None
    except Exception:
        dt = None
    hdr = {
        "from": names_only(str(msg["from"] or "")),
        "sent": nice_date(dt),
        "to": names_only(str(msg["to"] or "")),
        "cc": names_only(str(msg["cc"] or "")),
        "subject": str(msg["subject"] or "").strip(),
        "ts": dt.timestamp() if dt else None,
    }
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    return thread_from_message(hdr, body, mode), attachments


def parse_msg(data, mode):
    try:
        import extract_msg  # type: ignore
    except ImportError:
        raise ToolError(".msg files need one extra package. Close this program and run:  pip install extract-msg", 501)
    fd, path = tempfile.mkstemp(suffix=".msg")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        m = extract_msg.Message(path)
        try:
            sender = m.sender or ""
            to = m.to or ""
            cc = m.cc or ""
            subject = m.subject or ""
            date = m.date
            body = m.body or ""
            if not str(body).strip():
                hb = getattr(m, "htmlBody", None)
                if hb:
                    body = html_to_text(hb.decode("utf-8", "replace") if isinstance(hb, bytes) else hb)
            attachments = [a.longFilename or a.shortFilename for a in (m.attachments or []) if (a.longFilename or a.shortFilename)]
        finally:
            try:
                m.close()
            except Exception:
                pass
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    dt = date if isinstance(date, datetime) else parse_any_date(str(date or ""))
    hdr = {
        "from": names_only(sender),
        "sent": nice_date(dt),
        "to": names_only(to),
        "cc": names_only(cc),
        "subject": subject.strip(),
        "ts": dt.timestamp() if dt else None,
    }
    return thread_from_message(hdr, tidy_text(str(body)), mode), attachments
