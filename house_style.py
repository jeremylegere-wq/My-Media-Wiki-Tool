"""
house_style.py - the Wiki look, in one place.

Every colour and every inline style used on exported pages lives here. The
editor in the browser asks for STYLE (see style_sheet()) so what you see while
editing is the same markup that goes to the wiki.
"""
import html
import re

NAVY, BLUE, GREEN, PURPLE, AMBER, RED, GREY = (
    "#1f3a5f", "#1f5fa8", "#13806a", "#6a3fa0", "#b86e00", "#b3261e", "#6b7785")
COLOURS = {"navy": NAVY, "blue": BLUE, "green": GREEN, "purple": PURPLE,
           "amber": AMBER, "red": RED, "grey": GREY}
COLOUR_NAMES = {v: k for k, v in COLOURS.items()}

# callout kind -> (background, border, accent, text colour or "")
CALLOUTS = {
    "note":    ("#e6f0fb", "#1f5fa8", BLUE, ""),
    "warning": ("#fff1d6", "#e0b84d", AMBER, ""),
    "danger":  ("#fdecea", "#f2b8b5", RED, ""),
    "tip":     ("#e9f7f1", "#bfe3d4", GREEN, ""),
    "old":     ("#f4f5f7", "#d5dae0", GREY, "#54595d"),
}
CALLOUT_LABELS = {"note": "Note", "warning": "Warning", "danger": "Stop", "tip": "Tip", "old": "Superseded"}

# The styles. "{c}" is replaced by the block colour.
S = {
    "hidden": "display:none",
    "hero": "background:linear-gradient(120deg,#0f2a4a 0%,#1f5fa8 100%);color:#fff;border-radius:8px;padding:1.4em 1.8em;margin:0 0 .8em;",
    "hero_kicker": "font:bold 85% sans-serif;letter-spacing:.18em;text-transform:uppercase;opacity:.85;",
    "hero_title": "font:bold 210% Georgia,serif;line-height:1.15;margin:.2em 0 .25em;color:#fff;",
    "hero_sub": "font-size:108%;opacity:.95;max-width:60em;",
    "hero_pills": "margin-top:.9em;",
    "hero_pill": "display:inline-block;background:rgba(255,255,255,.18);font:85% sans-serif;padding:.25em .8em;border-radius:99px;margin:0 .4em .3em 0;",
    "card": "background:#fff;border:1px solid #dfe3e7;border-radius:6px;padding:.9em 1.2em;margin:0 0 .8em;",
    "h2": "background:#eef1f5;border:0;border-left:8px solid {c};color:#111;font:bold 135% sans-serif;margin:1.4em 0 .6em;padding:.45em .8em;border-radius:3px;",
    "h3": "border:0;border-bottom:2px solid {c};color:{c};font:bold 112% sans-serif;margin:1.1em 0 .5em;padding:0 0 .25em;",
    "step": "display:flex;gap:.8em;align-items:flex-start;margin:0 0 .8em;",
    "step_numwrap": "flex:0 0 2.4em;",
    "step_num": "background:{c};color:#fff;border-radius:50%;width:2.4em;height:2.4em;text-align:center;font:bold 105% sans-serif;line-height:2.4em;",
    "step_body": "flex:1 1 auto;min-width:0;background:#fff;border:1px solid #dfe3e7;border-left:6px solid {c};border-radius:6px;padding:.5em .9em;",
    "callout": "background:{bg};border:1px solid {bd};border-left:8px solid {c};border-radius:4px;padding:.6em 1em;margin:.8em 0;{tx}",
    "table": "border-collapse:collapse;width:100%;background:#fff;",
    "th": "background:{c};color:#fff;padding:.5em .7em;text-align:left;",
    "tr": "border-bottom:1px solid #e4e8ee;",
    "td": "padding:.45em .7em;vertical-align:top;",
    "tk": "background:#eef1f5;padding:.45em .7em;text-align:left;vertical-align:top;width:22%;",
    "cards": "display:flex;flex-wrap:wrap;gap:.7em;margin:0 0 .8em;",
    "cardx": "flex:1 1 240px;min-width:0;background:#fff;border:1px solid #dfe3e7;border-top:6px solid {c};border-radius:6px;padding:.3em 1em .8em;",
    "cardx_title": "font:bold 112% sans-serif;color:{c};margin:.6em 0 .3em;",
    "flow": "display:flex;flex-wrap:wrap;gap:.5em;align-items:stretch;margin:.4em 0 1em;",
    "flow_stage": "flex:1 1 180px;min-width:0;background:#f8f9fa;border:1px solid #dfe3e7;border-top:6px solid {c};border-radius:6px;padding:.4em .8em .6em;",
    "flow_title": "font:bold 105% sans-serif;color:{c};margin:.2em 0 .1em;",
    "flow_item": "background:#fff;border:1px solid #dfe3e7;border-left:5px solid {c};border-radius:4px;padding:.3em .7em;margin:.35em 0;",
    "flow_arrow": "flex:0 0 auto;align-self:center;font:bold 180% sans-serif;color:#1f5fa8;padding:0 .1em;",
    "collapse": "border:1px solid #dfe3e7;border-radius:6px;margin:.6em 0;background:#fff;",
    "collapse_head": "background:#eef1f5;padding:.45em .9em;font-weight:bold;color:{c};",
    "collapse_body": "padding:.4em .9em;",
    "figure": "max-width:710px;margin:.4em 0 .2em;border:1px solid #dfe3e7;border-radius:6px;padding:.4em;background:#fff;",
    "figcap": "font-size:90%;color:#54595d;margin:0 0 1em;",
    "pill": "display:inline-block;background:{c};color:#fff;font:bold 80% sans-serif;padding:.1em .6em;border-radius:99px;",
    "hr": "border:0;border-top:1px solid #dfe3e7;margin:1.2em 0;",
    "ol_wrap": "border:1px solid #c8c6c4;border-radius:3px;overflow:hidden;background:#faf9f8;margin:.4em 0 1em;box-shadow:0 1px 3px rgba(0,0,0,.12);",
    "ol_bar": "background:#0072c6;color:#fff;padding:.5em 1em;font:600 13px/1.2 Segoe UI,sans-serif;display:flex;justify-content:space-between;",
    "ol_bar_r": "opacity:.85;font-weight:400;",
    "ol_head": "background:#fff;border-bottom:1px solid #edebe9;padding:14px 18px;font-family:'Segoe UI','Segoe UI Web (West European)',-apple-system,Helvetica,Arial,sans-serif;",
    "ol_subj": "font-size:20px;font-weight:300;color:#201f1e;line-height:1.25;",
    "ol_meta": "font-size:12px;color:#605e5c;margin-top:4px;",
    "ol_msg": "background:#fff;border-bottom:1px solid #edebe9;padding:14px 18px 12px;font-family:'Segoe UI','Segoe UI Web (West European)',-apple-system,Helvetica,Arial,sans-serif;",
    "ol_row": "display:flex;gap:12px;align-items:flex-start;",
    "ol_badge": "flex:0 0 auto;width:40px;height:40px;border-radius:50%;background:{c};color:#fff;font:600 15px/40px Segoe UI,sans-serif;text-align:center;",
    "ol_main": "flex:1 1 auto;min-width:0;",
    "ol_top": "display:flex;flex-wrap:wrap;justify-content:space-between;gap:.3em 1em;",
    "ol_from": "font-size:15px;font-weight:600;color:#201f1e;",
    "ol_sent": "font-size:12px;color:#605e5c;",
    "ol_to": "font-size:12px;color:#605e5c;margin:3px 0 0;",
    "ol_cc": "font-size:12px;color:#605e5c;",
    "ol_lab": "color:#8a8886;",
    "ol_chip": "display:inline-block;background:#f3f2f1;border:1px solid #edebe9;border-radius:2px;padding:0 .4em;margin:0 .25em .15em 0;color:#323130;",
    "ol_subline": "font-size:12px;color:#605e5c;margin:2px 0 8px;",
    "ol_body": "font-size:14px;line-height:1.5;color:#201f1e;",
    "ol_p": "margin:0 0 .85em;",
    "ol_ul": "margin:0 0 .85em 1.4em;padding:0;",
    "email_cap": "font:bold 105% sans-serif;color:#1f3a5f;margin:.6em 0 .3em;",
    "email": "border:1px solid #dfe3e7;border-left:6px solid #1f5fa8;border-radius:6px;margin:0 0 .6em;background:#fff;overflow:hidden;",
    "email_head": "background:#f4f5f7;padding:.4em .9em;border-bottom:1px solid #e4e8ee;font-size:92%;color:#444;",
    "email_body": "padding:.5em .9em;",
    "code_wrap": "margin:.4em 0 1em;border:1px solid #3c3c3c;border-radius:6px;overflow:hidden;background:#1e1e1e;",
    "code_tabbar": "background:#2d2d30;border-bottom:1px solid #3c3c3c;font:12px Segoe UI,sans-serif;color:#ccc;",
    "code_tab": "display:inline-block;background:#1e1e1e;border-top:2px solid #007acc;padding:.45em 1em;color:#fff;",
    "code_body": "display:flex;overflow-x:auto;padding:.5em 0;font:13px/20px Consolas,Menlo,monospace;color:#d4d4d4;",
    "code_nums": "flex:0 0 auto;text-align:right;padding:0 .8em;color:#858585;border-right:1px solid #3c3c3c;white-space:pre;",
    "code_lines": "flex:1 0 auto;white-space:pre;",
    "code_line": "display:block;min-height:20px;padding:0 1em;",
    "code_num": "display:block;min-height:20px;",
}


def st(key, c=None, **kw):
    s = S[key]
    if c is not None:
        s = s.replace("{c}", COLOURS.get(c, c))
    for k, v in kw.items():
        s = s.replace("{%s}" % k, v)
    return s


def colour(name, default="blue"):
    return COLOURS.get(name) or COLOURS[default]


# ---------------------------------------------------------------- blocks
def hidden_line(title, summary):
    def clean(s):
        s = re.sub(r"[<>\[\]{}|=]", " ", s or "")
        return re.sub(r"\s+", " ", s).strip()
    t, m = clean(title), clean(summary)
    if t and not t.endswith("."):
        t += "."
    return '<div style="%s">%s</div>' % (S["hidden"], (t + " " + m).strip())


def hero(kicker, title, sub, pills):
    p = "".join('<span style="%s">%s</span>' % (S["hero_pill"], x) for x in pills if x)
    return ('<div style="%s"><div style="%s">%s</div><div style="%s">%s</div><div style="%s">%s</div>%s</div>'
            % (S["hero"], S["hero_kicker"], kicker, S["hero_title"], title, S["hero_sub"], sub,
               ('<div style="%s">%s</div>' % (S["hero_pills"], p)) if p else ""))


def card(body):
    return '<div style="%s">\n\n%s\n\n</div>' % (S["card"], body)


def h2(text, c="blue"):
    return '<h2 style="%s">%s</h2>' % (st("h2", c), text)


def h3(text, c="blue"):
    return '<h3 style="%s">%s</h3>' % (st("h3", c), text)


def step(n, body, c="blue"):
    return ('<div style="%s"><div style="%s"><div style="%s">%d</div></div><div style="%s">\n\n%s\n\n</div></div>'
            % (S["step"], S["step_numwrap"], st("step_num", c), n, st("step_body", c), body))


def callout(kind, body, inline=True):
    bg, bd, c, tx = CALLOUTS.get(kind, CALLOUTS["note"])
    style = st("callout", c, bg=bg, bd=bd, tx=("color:%s;" % tx) if tx else "")
    return ('<div style="%s">%s</div>' % (style, body)) if inline else ('<div style="%s">\n\n%s\n\n</div>' % (style, body))


def table(rows, header=True, keyval=False, c="navy"):
    """rows: list of lists of cell wikitext (already escaped for table use)."""
    o = ['{| style="%s"' % S["table"]]
    body = rows
    if header and rows:
        o.append("|-")
        for h in rows[0]:
            o.append('! style="%s" | %s' % (st("th", c), h))
        body = rows[1:]
    for r in body:
        o.append('|- style="%s"' % S["tr"])
        for i, cell in enumerate(r):
            if keyval and i == 0:
                o.append('! style="%s" | %s' % (S["tk"], cell))
            else:
                o.append('| style="%s" | %s' % (S["td"], cell))
    o.append("|}")
    return "\n".join(o)


def cards(items, c="blue"):
    """items: list of (title, body wikitext, colour or None)."""
    out = ['<div style="%s">' % S["cards"]]
    for title, body, cc in items:
        cc = cc or c
        t = ('<div style="%s">%s</div>' % (st("cardx_title", cc), title)) if title else ""
        out.append('<div style="%s">%s\n\n%s\n\n</div>' % (st("cardx", cc), t, body))
    out.append("</div>")
    return "\n".join(out)


def flow(stages, c="blue"):
    """stages: list of (title, [item wikitext], colour or None)."""
    parts = []
    for i, (title, items, cc) in enumerate(stages):
        cc = cc or c
        li = "".join('<div style="%s">%s</div>' % (st("flow_item", cc), x) for x in items)
        parts.append('<div style="%s"><div style="%s">%s</div>%s</div>' % (st("flow_stage", cc), st("flow_title", cc), title, li))
        if i < len(stages) - 1:
            parts.append('<div style="%s">&rarr;</div>' % S["flow_arrow"])
    return '<div style="%s">' % S["flow"] + "".join(parts) + "</div>"


def collapse(title, body, collapsed=True, c="navy"):
    cls = "mw-collapsible mw-collapsed" if collapsed else "mw-collapsible"
    return ('<div class="%s" style="%s"><div style="%s">%s</div><div class="mw-collapsible-content" style="%s">\n\n%s\n\n</div></div>'
            % (cls, S["collapse"], st("collapse_head", c), title, S["collapse_body"], body))


def figure(name, full, caption):
    alt = re.sub(r"[|\]\[]", " ", caption or name).strip()
    link = ("|link={{filepath:%s}}" % full) if full else ""
    line = '<div style="%s">[[File:%s%s|%s]]</div>' % (S["figure"], name, link, alt)
    cap = caption.strip() if caption else ""
    if full:
        cap = (cap.rstrip(".") + ". " if cap else "") + "Click the picture to open it full size."
    return line + ("\n<div style=\"%s\">%s</div>" % (S["figcap"], cap) if cap else "")


def pill(text, c="green"):
    return '<span style="%s">%s</span>' % (st("pill", c), text)


EMAIL_FIELDS = (("from", "From"), ("sent", "Sent"), ("to", "To"), ("cc", "Cc"), ("subject", "Subject"))


BADGE_COLOURS = ["#0f7b6c", "#1f5fa8", "#6a3fa0", "#b86e00", "#a8325e", "#1f3a5f"]


def initials(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "") if w and w.lower() not in ("of", "and", "the", "to", "for")]
    return ("".join(w[0] for w in words[:2]).upper()) or "?"


def thread_subject(emails_plain_subjects):
    for subj in emails_plain_subjects:
        s_ = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", subj or "", flags=re.I).strip()
        if s_:
            return s_
    return ""


def email(subject, meta, messages):
    """Outlook-style thread, as on Wiki page templates (modern layout).
    messages: list of dicts with wikitext values: from, sent, to (list), cc (list), subject, body,
    plus badge (initials) and colour. Every message sits on one line of wikitext."""
    out = ['<div style="%s"><div style="%s"><span>Mail</span><span style="%s">Conversation view</span></div>'
           % (S["ol_wrap"], S["ol_bar"], S["ol_bar_r"])]
    out.append('<div style="%s"><div style="%s">%s</div>%s</div>'
               % (S["ol_head"], S["ol_subj"], subject, ('<div style="%s">%s</div>' % (S["ol_meta"], meta)) if meta else ""))
    for m in messages:
        chips = lambda xs: " ".join('<span style="%s">%s</span>' % (S["ol_chip"], x) if not x.startswith("<!--") else x for x in xs)
        h = '<div style="%s"><div style="%s"><div style="%s">%s</div><div style="%s">' % (
            S["ol_msg"], S["ol_row"], st("ol_badge", m["colour"]), m["badge"], S["ol_main"])
        h += '<div style="%s"><div style="%s">%s</div>%s</div>' % (
            S["ol_top"], S["ol_from"], m["from"], ('<div style="%s">Sent: %s</div>' % (S["ol_sent"], m["sent"])) if m["sent"] else "")
        if m["to"]:
            h += '<div style="%s"><span style="%s">To:</span> %s</div>' % (S["ol_to"], S["ol_lab"], chips(m["to"]))
        if m["cc"]:
            h += '<div style="%s"><span style="%s">Cc:</span> %s</div>' % (S["ol_cc"], S["ol_lab"], chips(m["cc"]))
        if m["subject"]:
            h += '<div style="%s"><span style="%s">Subject:</span> %s</div>' % (S["ol_subline"], S["ol_lab"], m["subject"])
        h += '<div style="%s">%s</div></div></div></div>' % (S["ol_body"], m["body"])
        out.append(h)
    out.append("</div>")
    return "".join(out)


def divider():
    return '<hr style="%s" />' % S["hr"]


# ---------------------------------------------------------------- code box
SQL_KW = set("""SELECT FROM WHERE AND OR NOT NULL IN IS AS ON JOIN LEFT RIGHT INNER OUTER FULL CROSS APPLY GROUP ORDER BY
HAVING UNION ALL DISTINCT TOP INSERT INTO VALUES UPDATE SET DELETE TRUNCATE EXEC EXECUTE DECLARE USE CREATE ALTER DROP
TABLE VIEW PROCEDURE PROC FUNCTION TRIGGER INDEX BEGIN END CASE WHEN THEN ELSE LIKE BETWEEN DESC ASC EXISTS WITH OVER
PARTITION GO OPENROWSET BULK FORMATFILE FIRSTROW RETURN RETURNS IF WHILE MERGE OUTPUT PRIMARY KEY FOREIGN REFERENCES
NOLOCK TRAN TRANSACTION COMMIT ROLLBACK TRY CATCH PRINT NOCOUNT OFF IDENTITY DEFAULT CONSTRAINT CHECK UNIQUE CLUSTERED
NONCLUSTERED SCHEMA DATABASE GRANT REVOKE DENY PIVOT UNPIVOT FETCH NEXT ROWS ONLY OFFSET CURSOR OPEN CLOSE DEALLOCATE
INT BIGINT SMALLINT TINYINT BIT DECIMAL NUMERIC FLOAT REAL MONEY CHAR NCHAR VARCHAR NVARCHAR TEXT NTEXT DATE TIME
DATETIME DATETIME2 SMALLDATETIME DATETIMEOFFSET UNIQUEIDENTIFIER VARBINARY BINARY MAX""".split())
SQL_FUNCS = set("""COUNT SUM MIN AVG CAST CONVERT TRY_CAST TRY_CONVERT ISNULL COALESCE NULLIF IIF CHOOSE GETDATE
SYSDATETIME GETUTCDATE DATEADD DATEDIFF DATEPART DATENAME DATEFROMPARTS EOMONTH YEAR MONTH DAY LEN DATALENGTH SUBSTRING
REPLACE LTRIM RTRIM TRIM UPPER LOWER CHARINDEX PATINDEX STUFF CONCAT CONCAT_WS FORMAT ROUND ABS FLOOR CEILING
ROW_NUMBER RANK DENSE_RANK NTILE LAG LEAD FIRST_VALUE LAST_VALUE STRING_AGG STRING_SPLIT OBJECT_ID OBJECT_NAME
SCHEMA_NAME DB_NAME DB_ID NEWID SCOPE_IDENTITY ERROR_MESSAGE ERROR_NUMBER QUOTENAME REVERSE REPLICATE SPACE STR""".split())
SQL_COLOURS = {"kw": "#569cd6", "fn": "#d670d6", "str": "#ce9178", "com": "#57a64a", "num": "#b5cea8",
               "var": "#9cdcfe", "sys": "#4ec9b0"}
_SQLTOK = re.compile(r"(?P<com>--.*$)|(?P<str>N?'(?:[^']|'')*'?)|(?P<var>@@?\w+)"
                     r"|(?P<sys>\b(?:sys|INFORMATION_SCHEMA)\.\w+|\b(?:msdb|tempdb|master)\b)"
                     r"|(?P<num>\b\d+(?:\.\d+)?\b)|(?P<word>\b[A-Za-z_]\w*\b)", re.I)


def code_esc(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;")
    s = (s.replace("{", "&#123;").replace("}", "&#125;").replace("[", "&#91;").replace("]", "&#93;")
         .replace("|", "&#124;").replace("__", "_&#95;").replace("~~~", "~&#126;~"))
    return s


def _paint(kind, text):
    return '<span style="color:%s">%s</span>' % (SQL_COLOURS[kind], code_esc(text))


def _sql_line(line):
    out, last = "", 0
    for m in _SQLTOK.finditer(line):
        kind = m.lastgroup
        if kind == "word":
            w = m.group(0).upper()
            kind = "fn" if w in SQL_FUNCS else ("kw" if w in SQL_KW else None)
            if kind is None:
                continue
        out += code_esc(line[last:m.start()]) + _paint(kind, m.group(0))
        last = m.end()
    return out + code_esc(line[last:])


def codebox(title, text, lang="sql"):
    lines = (text or "").replace("\r", "").replace("\t", "    ").rstrip("\n").split("\n")
    while len(lines) > 1 and not lines[0].strip():
        lines.pop(0)
    nums = "".join('<span style="%s">%d</span>' % (S["code_num"], i + 1) for i in range(len(lines)))
    fn = _sql_line if lang == "sql" else code_esc
    body = "".join('<span style="%s">%s</span>' % (S["code_line"], fn(l)) for l in lines)
    return ('<div style="%s"><div style="%s"><span style="%s">%s</span></div><div style="%s"><div style="%s">%s</div><div style="%s">%s</div></div></div>'
            % (S["code_wrap"], S["code_tabbar"], S["code_tab"], html.escape(title or ("SQLQuery1.sql" if lang == "sql" else "Text"), quote=False),
               S["code_body"], S["code_nums"], nums, S["code_lines"], body))


def style_sheet():
    """What the browser editor needs to draw blocks exactly like the export."""
    return {"S": S, "colours": COLOURS, "callouts": {k: list(v) for k, v in CALLOUTS.items()},
            "calloutLabels": CALLOUT_LABELS, "badgeColours": BADGE_COLOURS}
