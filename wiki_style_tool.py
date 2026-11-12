#!/usr/bin/env python3
"""
Wiki Style Tool - article editor
====================================
Write knowledge articles straight onto a page that looks like the Wiki,
start from a template, and export the result as wikitext in our house style.

How it works
  * This program starts a small web server that listens on this computer only
    (127.0.0.1) and opens the editor in your browser.
  * Python does all the real work: the templates, turning the page into
    wikitext, reading existing wikitext and Word or email files back in,
    checking the page against the house rules, and saving files.
  * The browser is only the editing surface. Nothing is sent over the network.

Run it
  python wiki_style_tool.py
  python wiki_style_tool.py --port 9000 --no-browser
  python wiki_style_tool.py --make-shortcut

Needs Python 3.8 or later and nothing else. One optional package:
  pip install extract-msg     reading Outlook .msg files
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if getattr(sys, "frozen", False):  # packaged with PyInstaller
    BASE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE = APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import doc_import  # noqa: E402
import exporter  # noqa: E402
import house_style  # noqa: E402
import importer  # noqa: E402
import layout  # noqa: E402
import rich  # noqa: E402
import templates  # noqa: E402
import wiki_api  # noqa: E402
import wiki_lint  # noqa: E402

VERSION = "1.0.0"
STATIC = os.path.join(BASE, "static")
OUTPUT = os.path.join(APP_DIR, "output")
DRAFTS = os.path.join(OUTPUT, "drafts")
MAX_UPLOAD = 30 * 1024 * 1024
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
STATIC_FILES = {"editor.js": "application/javascript; charset=utf-8", "editor.css": "text/css; charset=utf-8",
                "index.html": "text/html; charset=utf-8"}
WIKI_EDIT = "https://your-wiki.example.com/Wiki/index.php?title=%s&action=edit"
BACKUPS = os.path.join(OUTPUT, "wiki_backups")

# The wiki connection lives in memory only: one session for this computer's tool,
# gone when the tool closes. The bot password is never kept (see wiki_api.py).
WIKI = {"api": os.environ.get("WST_WIKI_API") or wiki_api.DEFAULT_API, "session": None, "reader": None}
WIKI_LOCK = threading.Lock()


class ToolError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def msg_support():
    try:
        import extract_msg  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def slug(name, default="wiki_page"):
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", str(name or "")).strip(" ._") or default
    return re.sub(r"\s+", "_", name)[:100]


def text_to_html(body):
    """Plain email text -> editor paragraphs."""
    paras = re.split(r"\n\s*\n", (body or "").strip())
    out = []
    for p in paras:
        lines = [rich._h(l.strip()) for l in p.split("\n") if l.strip()]
        if lines:
            out.append("<p>%s</p>" % "<br>".join(lines))
    return "".join(out)


def clean_contact(s):
    s = wiki_lint.EMAIL_RE.sub("(email address removed)", s or "")
    return wiki_lint.PHONE_RE.sub("(phone number removed)", s)


def mail_to_block(emails, anon=True, strip=True):
    out = []
    ph = {}
    for n, e in enumerate(emails):
        item = {}
        for k in ("from", "sent", "to", "cc", "subject"):
            v = str(e.get(k) or "")
            if anon and k in ("from", "to", "cc") and v:
                v = "Role to be added"
                ph["emails.%d.%s" % (n, k)] = True
            item[k] = v
        body = e.get("body", "")
        item["html"] = text_to_html(clean_contact(body) if strip else body)
        out.append(item)
    return {"id": importer._id(), "type": "email", "caption": "", "emails": out, "ph": ph}


def wiki_reader(api=None):
    """The logged-in session if there is one for this address, otherwise one that reads without logging in."""
    api = api or WIKI["api"]
    s = WIKI["session"]
    if s and s.user and s.api == api:
        return s
    r = WIKI["reader"]
    if not r or r.api != api:
        r = WIKI["reader"] = wiki_api.WikiSession(api)
    return r


def wiki_status():
    s = WIKI["session"]
    st = s.status() if s else {"connected": False, "user": "", "api": WIKI["api"], "canEdit": False, "canCreate": False}
    base = WIKI["api"].rsplit("/", 1)[0]
    st.update({"defaultApi": WIKI["api"], "botPasswordsUrl": base + "/index.php?title=Special:BotPasswords",
               "helpUrl": base + "/index.php?title=Wiki_Style_Tool_-_Connecting_to_the_wiki"})
    return st


def wiki_source(page, api):
    return {"title": page["title"], "exists": page["exists"], "revid": page["revid"], "timestamp": page["timestamp"],
            "starttimestamp": page["starttimestamp"], "protected": page["protected"], "api": api,
            "url": wiki_api.page_url(api, page["title"])}


def page_files(text):
    """Picture names a page uses: [[File:x]] and {{filepath:x}}."""
    names = re.findall(r"\[\[\s*(?:File|Image)\s*:\s*([^|\]]+)", text, re.I) + re.findall(r"\{\{\s*filepath\s*:\s*([^}|]+)", text, re.I)
    return [n.strip() for n in names if n.strip()]


def backup_page(page):
    """Keep a copy of the wiki's version before it is replaced."""
    if not page.get("exists"):
        return ""
    os.makedirs(BACKUPS, exist_ok=True)
    name = "%s_r%s_%s.txt" % (slug(page["title"]), page.get("revid", 0), datetime.now().strftime("%Y%m%d-%H%M%S"))
    path = os.path.join(BACKUPS, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page.get("text", ""))
    return path


def list_drafts():
    out = []
    if os.path.isdir(DRAFTS):
        for f in os.listdir(DRAFTS):
            if not f.endswith(".json"):
                continue
            p = os.path.join(DRAFTS, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                title = d.get("title") or "(untitled)"
            except (OSError, ValueError):
                continue
            out.append({"name": f, "title": title, "modified": os.path.getmtime(p),
                        "when": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%d %b %Y %H:%M")})
    return sorted(out, key=lambda x: -x["modified"])[:40]


class Handler(BaseHTTPRequestHandler):
    server_version = "WikiStyleTool/" + VERSION

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower().strip("[]")
        if host not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin and self.command == "POST":
            o = urlparse(origin)
            if (o.hostname or "").lower() not in ALLOWED_HOSTS:
                return False
        return True

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _static(self, name):
        try:
            with open(os.path.join(STATIC, name), "rb") as f:
                return self._send(200, f.read(), STATIC_FILES[name])
        except OSError:
            return self._send(500, {"error": "static/%s is missing" % name})

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "Not allowed"})
        url = urlparse(self.path)
        path = url.path
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/") and path[8:] in STATIC_FILES:
            return self._static(path[8:])
        if path == "/api/ping":
            return self._send(200, {"ok": True, "version": VERSION, "msg": msg_support(), "saveDir": OUTPUT})
        if path == "/api/style":
            d = house_style.style_sheet()
            d.update({"categories": exporter.OFFICIAL_CATEGORIES, "blockNames": exporter.BLOCK_NAMES,
                      "wikiEdit": WIKI_EDIT, "version": VERSION})
            return self._send(200, d)
        if path == "/api/templates":
            return self._send(200, templates.listing())
        if path == "/api/template":
            doc = templates.build(q.get("id", ""))
            return self._send(200, doc) if doc else self._send(404, {"error": "No such template"})
        if path == "/api/drafts":
            return self._send(200, list_drafts())
        if path == "/api/draft":
            name = os.path.basename(q.get("name", ""))
            p = os.path.join(DRAFTS, name)
            if not name.endswith(".json") or not os.path.isfile(p):
                return self._send(404, {"error": "That draft was not found."})
            with open(p, encoding="utf-8") as f:
                return self._send(200, f.read())
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path.startswith("/api/wiki/"):
            try:
                return self._wiki_get(path, q)
            except wiki_api.WikiError as e:
                return self._send(e.status, {"error": str(e), "code": e.code})
        return self._send(404, {"error": "Not found"})

    def _wiki_get(self, path, q):
        if path == "/api/wiki/status":
            return self._send(200, wiki_status())
        if path == "/api/wiki/search":
            with WIKI_LOCK:
                return self._send(200, {"titles": wiki_reader().search(q.get("q", ""))})
        if path == "/api/wiki/open":
            with WIKI_LOCK:
                r = wiki_reader()
                page = r.get_page(q.get("title", ""))
            src = wiki_source(page, r.api)
            if not page["exists"]:
                return self._send(200, {"missing": True, "source": src})
            if page["redirect"]:
                return self._send(200, {"redirect": page["redirect"], "source": src})
            doc = importer.import_wiki(page["text"])
            if not doc.get("title"):
                doc["title"] = page["title"]
            doc["_wiki"] = src
            return self._send(200, {"doc": doc, "source": src})
        return self._send(404, {"error": "Not found"})

    def _json(self, data):
        try:
            return json.loads(data.decode("utf-8") or "{}")
        except ValueError:
            raise ToolError("That was not valid JSON.")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "Not allowed"})
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                raise ToolError("That file is too large (limit 30 MB).", 413)
            data = self.rfile.read(length) if length else b""
            p = url.path
            if p == "/api/export":
                doc = self._json(data)
                text, notes = exporter.export(doc)
                issues = wiki_lint.check(text)
                return self._send(200, {"text": text, "notes": notes, "issues": issues,
                                        "filename": slug(doc.get("title"), "wiki_page") + ".txt"})
            if p == "/api/import":
                payload = self._json(data)
                return self._send(200, importer.import_wiki(payload.get("text", "")))
            if p == "/api/layout":
                # wiki code -> a layout block with editable text (or null)
                payload = self._json(data)
                blk = layout.build(payload.get("wiki", ""))
                if blk:
                    blk["id"] = importer._id()
                return self._send(200, {"block": blk})
            if p == "/api/blockwiki":
                # one block -> its wiki code (used by "Edit wiki code")
                payload = self._json(data)
                b = payload.get("block") or {}
                kind, text = exporter._block(b, int(payload.get("num") or 1), [], 0)
                return self._send(200, {"wiki": text or ""})
            if p.startswith("/api/wiki/"):
                # writing to the wiki: only the editor page can ask (a custom header other web sites cannot send)
                if self.headers.get("X-WST") != "1":
                    return self._send(403, {"error": "Not allowed"})
                try:
                    return self._wiki_post(p, self._json(data))
                except wiki_api.WikiError as e:
                    return self._send(409 if e.code == "editconflict" else e.status, {"error": str(e), "code": e.code})
            if p == "/api/import-plain":
                payload = self._json(data)
                return self._send(200, importer.import_plain(payload.get("text", "")))
            if p == "/api/lint":
                payload = self._json(data)
                issues = wiki_lint.check(payload.get("text", ""))
                return self._send(200, {"issues": issues, "summary": wiki_lint.summary(issues)})
            if p == "/api/fix":
                payload = self._json(data)
                text, applied = wiki_lint.fix(payload.get("text", ""))
                issues = wiki_lint.check(text)
                return self._send(200, {"text": text, "applied": applied, "issues": issues})
            if p == "/api/docx":
                text = doc_import.docx_to_text(data)
                doc = importer.import_plain(text)
                if not doc.get("title"):
                    doc["title"] = os.path.splitext(os.path.basename(q.get("name", "")))[0].replace("_", " ")
                return self._send(200, doc)
            if p == "/api/mail":
                name = q.get("name", "")
                mode = q.get("mode", "split") if q.get("mode") in ("split", "latest", "whole") else "split"
                ext = os.path.splitext(name)[1].lower()
                if ext == ".eml":
                    emails, att = doc_import.parse_eml(data, mode)
                elif ext == ".msg":
                    emails, att = doc_import.parse_msg(data, mode)
                else:
                    raise ToolError("Please choose a .eml or .msg file.")
                emails = sorted(emails, key=lambda e: -(e.get("ts") or 0))
                block = mail_to_block(emails, q.get("anon", "1") == "1", q.get("strip", "1") == "1")
                return self._send(200, {"block": block, "attachments": att})
            if p == "/api/codebox":
                payload = self._json(data)
                html = house_style.codebox(str(payload.get("title") or ""), str(payload.get("code") or ""),
                                           "sql" if payload.get("lang", "sql") == "sql" else "text")
                return self._send(200, {"html": html})
            if p == "/api/save":
                payload = self._json(data)
                os.makedirs(OUTPUT, exist_ok=True)
                target = os.path.join(OUTPUT, re.sub(r"\.txt$", "", slug(payload.get("name"), "wiki_page")) + ".txt")
                with open(target, "w", encoding="utf-8", newline="\n") as f:
                    f.write(payload.get("text", ""))
                return self._send(200, {"path": target})
            if p == "/api/draft":
                payload = self._json(data)
                doc = payload.get("doc") or {}
                os.makedirs(DRAFTS, exist_ok=True)
                name = payload.get("name") or (slug(doc.get("title"), "untitled") + ".json")
                name = os.path.basename(name)
                if not name.endswith(".json"):
                    name += ".json"
                target = os.path.join(DRAFTS, name)
                with open(target, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(doc, f, indent=1, ensure_ascii=False)
                return self._send(200, {"path": target, "name": name})
            return self._send(404, {"error": "Not found"})
        except ToolError as e:
            return self._send(e.status, {"error": str(e)})
        except doc_import.ToolError as e:
            return self._send(e.status, {"error": str(e)})
        except Exception as e:  # never crash the server on a bad file
            return self._send(500, {"error": "Something went wrong: %s" % e})


def _wiki_post_impl(self, p, payload):
    if p == "/api/wiki/login":
        password = payload.pop("password", "")
        api = (payload.get("api") or WIKI["api"]).strip()
        with WIKI_LOCK:
            s = wiki_api.WikiSession(api, use_proxy=not payload.get("noProxy"))
            try:
                st = s.login(payload.get("username", ""), password)
            finally:
                password = None  # noqa: F841 - never kept
            old = WIKI["session"]
            WIKI["session"], WIKI["api"] = s, s.api
            if old and old is not s:
                old.jar.clear()
        return self._send(200, wiki_status())
    if p == "/api/wiki/logout":
        with WIKI_LOCK:
            if WIKI["session"]:
                WIKI["session"].logout()
            WIKI["session"] = None
        return self._send(200, wiki_status())
    if p in ("/api/wiki/preview", "/api/wiki/publish"):
        doc = payload.get("doc") or {}
        src = doc.get("_wiki") or {}
        title = (payload.get("title") or src.get("title") or doc.get("title") or "").strip()
        text, notes = exporter.export(doc)
        with WIKI_LOCK:
            s = WIKI["session"]
            if not (s and s.user):
                raise wiki_api.WikiError("Connect to the wiki first.", "notloggedin", 401)
            current = s.get_page(title)
            same_page = bool(src.get("exists")) and src.get("title", "").replace("_", " ") == current["title"]
            base = src if same_page else None
            if p == "/api/wiki/preview":
                missing = s.missing_files(page_files(text))
                diff, added, removed = wiki_api.diff_html(current["text"] if current["exists"] else "", text)
                return self._send(200, {
                    "title": current["title"], "exists": current["exists"], "samePage": same_page,
                    "changedSinceOpen": bool(same_page and current["revid"] != src.get("revid")),
                    "existsButNotOpened": bool(current["exists"] and not same_page),
                    "protected": current["protected"], "canEdit": "edit" in s.rights, "canCreate": "createpage" in s.rights,
                    "diff": diff, "added": added, "removed": removed, "text": text,
                    "issues": [i for i in wiki_lint.check(text) if i["level"] in ("error", "warn")],
                    "todos": [n["message"] for n in notes if n["message"].startswith("Still to do")],
                    "missingFiles": missing, "url": wiki_api.page_url(s.api, current["title"]),
                    "openedRevid": src.get("revid", 0), "currentRevid": current["revid"]})
            if current["exists"] and not same_page:
                raise wiki_api.WikiError("A page called %s already exists on the wiki. Open it from the wiki first, "
                                         "or publish under another title." % current["title"], "articleexists")
            backup = backup_page(current) if current["exists"] else ""
            res = s.publish(current["title"], text, payload.get("summary", ""), base=base,
                            minor=bool(payload.get("minor")), force=bool(payload.get("force")))
        newsrc = dict(src, title=res["title"], exists=True, revid=res["newrevid"] or current["revid"],
                      timestamp=res["newtimestamp"] or current["timestamp"], starttimestamp=res["newtimestamp"] or current["starttimestamp"],
                      api=s.api, url=wiki_api.page_url(s.api, res["title"]), protected=current["protected"])
        return self._send(200, {"ok": True, "result": res, "source": newsrc, "backup": backup})
    return self._send(404, {"error": "Not found"})


Handler._wiki_post = _wiki_post_impl


def free_port(start):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free port found near %d" % start)


def make_shortcut():
    """Put a 'Wiki Style Tool' shortcut on the user's Desktop (Windows .lnk, Linux .desktop)."""
    here = APP_DIR
    if sys.platform.startswith("win"):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):  # OneDrive-redirected desktops
            for cand in (os.environ.get("OneDrive", ""), os.environ.get("OneDriveCommercial", "")):
                if cand and os.path.isdir(os.path.join(cand, "Desktop")):
                    desktop = os.path.join(cand, "Desktop")
                    break
        link = os.path.join(desktop, "Wiki Style Tool.lnk")
        if getattr(sys, "frozen", False):
            target, arguments = sys.executable, ""
        else:
            target = sys.executable
            arguments = '"%s"' % os.path.abspath(__file__)
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
            "$s.TargetPath='%s';$s.Arguments='%s';$s.WorkingDirectory='%s';"
            "$s.Description='Wiki Style Tool';$s.WindowStyle=7;$s.Save()"
        ) % (link.replace("'", "''"), target.replace("'", "''"), arguments.replace("'", "''"), here.replace("'", "''"))
        import subprocess
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(link):
            print("Could not create the shortcut:", (r.stderr or r.stdout).strip())
            return 1
        print("Shortcut created on your Desktop:", link)
        return 0
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    cmd = ('"%s"' % sys.executable) if getattr(sys, "frozen", False) else ('"%s" "%s"' % (sys.executable, os.path.abspath(__file__)))
    path = os.path.join(desktop, "Wiki Style Tool.desktop")
    with open(path, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Wiki Style Tool\nComment=Write Wiki articles\n"
                "Exec=%s\nPath=%s\nTerminal=true\nCategories=Utility;\n" % (cmd, here))
    os.chmod(path, 0o755)
    print("Shortcut created:", path)
    print("On Ubuntu, right-click it and choose Allow Launching the first time.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Wiki Style Tool - article editor (local)")
    ap.add_argument("--make-shortcut", action="store_true", help="put a shortcut on the Desktop and exit")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--wiki-api", help="the wiki's API address (default %s)" % wiki_api.DEFAULT_API)
    args = ap.parse_args()
    if args.wiki_api:
        WIKI["api"] = wiki_api.check_api_url(args.wiki_api)
    if args.make_shortcut:
        return make_shortcut()
    port = free_port(args.port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    print("Wiki Style Tool %s is running at %s" % (VERSION, url))
    print("Saved pages and drafts go to:", OUTPUT)
    print(".msg email support:", "yes" if msg_support() else "not installed (optional: pip install extract-msg)")
    print("Leave this window open while you work. Close it, or press Ctrl+C, to stop.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
