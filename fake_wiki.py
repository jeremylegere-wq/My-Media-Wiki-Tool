"""
fake_wiki.py - a small stand-in for the Wiki's MediaWiki API, for tests.

It answers the API calls wiki_api.py makes (tokens, login with bot passwords,
userinfo, reading one or many pages, prefix search, listing pages, file checks,
editing with edit-conflict detection, moving pages, uploading files, logout)
the way an older MediaWiki does. Every page keeps its history, so links to
earlier versions (oldid) can be checked. selftest.py starts one on a
spare port; you can also run it by hand to try the Wiki buttons without the
real wiki:

    python fake_wiki.py --port 8899
    python wiki_style_tool.py --wiki-api http://127.0.0.1:8899/w/api.php

Log in as Tester@StyleTool with the password  test-bot-password  (a made-up
password for this fake only).
"""
import argparse
import hashlib
import json
import secrets
from email import policy
from email.parser import BytesParser
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BOT_USER, BOT_PASS = "Tester@StyleTool", "test-bot-password"


def _now(offset=0):
    return (datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeWiki:
    RIGHTS = ["read", "edit", "createpage", "writeapi", "move", "upload", "reupload"]

    def __init__(self, read_needs_login=False, slots=False, rights=None):
        self.read_needs_login = read_needs_login
        self.slots = slots                  # newer MediaWiki puts text in slots.main
        self.rights = list(self.RIGHTS if rights is None else rights)
        self.pages = {}                     # title -> {"text", "revid", "timestamp", "user", "comment"}
        self.history = {}                   # revid -> (title, text)
        self.protected = set()
        self.files = set()
        self.file_data = {}                 # name -> bytes (uploads)
        self.moves = []                     # (from, to, user, reason)
        self.sessions = {}                  # cookie -> user
        self.csrf = {}                      # cookie -> token
        self.login_tokens = {}
        self.edits = []                     # (user, title, summary, minor)
        self.requests = []                  # raw request bodies, to check nothing leaks
        self.clock = 0
        self.revid = 100
        self.lock = threading.Lock()

    def add_page(self, title, text, user="Someone", comment=""):
        self.revid += 1
        self.clock += 60
        self.pages[title] = {"text": text, "revid": self.revid, "timestamp": _now(self.clock), "user": user, "comment": comment}
        self.history[self.revid] = (title, text)

    def other_person_edits(self, title, text, comment="Fixed a typo"):
        """Someone else saves the page (for edit-conflict and hand-edit tests)."""
        self.add_page(title, text, "Someone Else", comment)

    def add_file(self, name, data):
        name = name.replace(" ", "_")
        self.files.add(name)
        self.file_data[name] = data

    # ------------------------------------------------------------ API
    def handle(self, params, cookie):
        user = self.sessions.get(cookie, "")
        a = params.get("action", "")
        if a == "query":
            return self.query(params, cookie, user)
        if a == "login":
            if self.login_tokens.get(cookie) != params.get("lgtoken"):
                return {"login": {"result": "NeedToken"}}
            if params.get("lgname") == BOT_USER and params.get("lgpassword") == BOT_PASS:
                self.sessions[cookie] = "Tester"
                return {"login": {"result": "Success", "lguserid": 7, "lgusername": "Tester"}}
            if "@" not in params.get("lgname", ""):
                return {"login": {"result": "Aborted", "reason": "Login with your main password via action=login is not allowed."}}
            return {"login": {"result": "Failed", "reason": "Incorrect username or password entered."}}
        if a == "logout":
            self.sessions.pop(cookie, None)
            return {}
        if a == "edit":
            return self.edit(params, cookie, user)
        if a == "move":
            return self.move(params, cookie, user)
        if a == "upload":
            return self.upload(params, cookie, user)
        return {"error": {"code": "unknown_action", "info": "Unrecognized value for parameter \"action\""}}

    def query(self, params, cookie, user):
        out = {"batchcomplete": ""}
        if params.get("meta") == "tokens":
            kind = params.get("type", "csrf")
            if kind == "login":
                tok = secrets.token_hex(8) + "+\\"
                self.login_tokens[cookie] = tok
                return {"query": {"tokens": {"logintoken": tok}}}
            tok = (secrets.token_hex(8) + "+\\") if user else "+\\"
            self.csrf[cookie] = tok
            return {"query": {"tokens": {"csrftoken": tok}}}
        if params.get("meta") == "userinfo":
            if not user:
                return {"query": {"userinfo": {"id": 0, "name": "127.0.0.1", "anon": ""}}}
            return {"query": {"userinfo": {"id": 7, "name": user, "groups": ["*", "user"], "rights": list(self.rights)}}}
        if self.read_needs_login and not user:
            return {"error": {"code": "readapidenied", "info": "You need read permission to use this module."}}
        if params.get("list") == "prefixsearch":
            p = params.get("pssearch", "").lower()
            return {"query": {"prefixsearch": [{"ns": 0, "title": t} for t in sorted(self.pages) if t.lower().startswith(p)][:12]}}
        if params.get("list") == "allpages":
            p = params.get("apprefix", "")
            redir = params.get("apfilterredir", "all")
            hits = []
            for t in sorted(self.pages):
                if not t.startswith(p):
                    continue
                is_redir = self.pages[t]["text"].lstrip().upper().startswith("#REDIRECT")
                if (redir == "nonredirects" and is_redir) or (redir == "redirects" and not is_redir):
                    continue
                hits.append({"pageid": 1, "ns": 0, "title": t})
            start = int(params.get("apcontinue") or 0)
            lim = int(params.get("aplimit") or 10)
            res = {"query": {"allpages": hits[start:start + lim]}}
            if start + lim < len(hits):
                res["continue"] = {"apcontinue": str(start + lim), "continue": "-||"}
            return res
        titles = [t for t in params.get("titles", "").split("|") if t]
        if titles:
            pages, normalized = {}, []
            for n, t in enumerate(titles):
                tt = t.replace("_", " ")
                if tt != t:
                    normalized.append({"from": t, "to": tt})
                if tt.startswith("File:"):
                    name = tt[5:].replace(" ", "_")
                    if name in {f.replace(" ", "_") for f in self.files}:
                        entry = {"pageid": 900 + n, "ns": 6, "title": tt}
                        if "imageinfo" in params.get("prop", ""):
                            data = self.file_data.get(name, b"")
                            entry["imageinfo"] = [{"sha1": hashlib.sha1(data).hexdigest(), "size": len(data)}]
                        pages[str(900 + n)] = entry
                    else:
                        pages[str(-1 - n)] = {"ns": 6, "title": tt, "missing": ""}
                    continue
                pg = self.pages.get(tt)
                if not pg:
                    pages[str(-1 - n)] = {"ns": 0, "title": tt, "missing": "", "protection": []}
                    continue
                rev = {"revid": pg["revid"], "parentid": pg["revid"] - 1, "timestamp": pg["timestamp"]}
                rvprop = params.get("rvprop", "")
                if "user" in rvprop:
                    rev["user"] = pg.get("user", "")
                if "comment" in rvprop:
                    rev["comment"] = pg.get("comment", "")
                if self.slots:
                    rev["slots"] = {"main": {"contentmodel": "wikitext", "contentformat": "text/x-wiki", "*": pg["text"]}}
                else:
                    rev.update({"contentformat": "text/x-wiki", "contentmodel": "wikitext", "*": pg["text"]})
                entry = {"pageid": 500 + n, "ns": 0, "title": tt, "lastrevid": pg["revid"], "revisions": [rev],
                         "protection": [{"type": "edit", "level": "sysop", "expiry": "infinity"}] if tt in self.protected else []}
                if pg["text"].lstrip().upper().startswith("#REDIRECT"):
                    entry["redirect"] = ""
                pages[str(500 + n)] = entry
            out["query"] = {"pages": pages}
            if normalized:
                out["query"]["normalized"] = normalized
            if params.get("curtimestamp"):
                out["curtimestamp"] = _now(self.clock + 5)
            if not self.slots and params.get("rvslots"):
                out["warnings"] = {"main": {"*": "Unrecognized parameter: rvslots."}}
            return out
        return out

    def edit(self, params, cookie, user):
        if params.get("assert") == "user" and not user:
            return {"error": {"code": "assertuserfailed", "info": "You are no longer logged in."}}
        if not params.get("token") or params.get("token") != self.csrf.get(cookie):
            return {"error": {"code": "badtoken", "info": "Invalid CSRF token."}}
        title = params.get("title", "").replace("_", " ")
        pg = self.pages.get(title)
        if title in self.protected:
            return {"error": {"code": "protectedpage", "info": "This page has been protected to prevent editing."}}
        if params.get("createonly") and pg:
            return {"error": {"code": "articleexists", "info": "The article you tried to create has been created already."}}
        if params.get("nocreate") and not pg:
            return {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        if pg and params.get("basetimestamp") and params["basetimestamp"] != pg["timestamp"]:
            return {"error": {"code": "editconflict", "info": "Edit conflict."}}
        if "edit" not in self.rights or (not pg and "createpage" not in self.rights):
            return {"error": {"code": "permissiondenied", "info": "You don't have permission to edit this page."}}
        self.edits.append((user, title, params.get("summary", ""), bool(params.get("minor"))))
        if pg and pg["text"] == params.get("text"):
            return {"edit": {"result": "Success", "pageid": 1, "title": title, "contentmodel": "wikitext", "nochange": ""}}
        old = pg["revid"] if pg else 0
        self.add_page(title, params.get("text", ""), user, params.get("summary", ""))
        res = {"result": "Success", "pageid": 1, "title": title, "contentmodel": "wikitext", "oldrevid": old,
               "newrevid": self.pages[title]["revid"], "newtimestamp": self.pages[title]["timestamp"]}
        if not pg:
            res["new"] = ""
        return {"edit": res}


    def _check_token(self, params, cookie, user):
        if not user:
            return {"error": {"code": "mustbeloggedin", "info": "You must be logged in."}}
        if not params.get("token") or params.get("token") != self.csrf.get(cookie):
            return {"error": {"code": "badtoken", "info": "Invalid CSRF token."}}
        return None

    def move(self, params, cookie, user):
        err = self._check_token(params, cookie, user)
        if err:
            return err
        if "move" not in self.rights:
            return {"error": {"code": "cantmove", "info": "You don't have permission to move pages."}}
        frm, to = params.get("from", "").replace("_", " "), params.get("to", "").replace("_", " ")
        if frm not in self.pages:
            return {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        if frm == to:
            return {"error": {"code": "selfmove", "info": "The title is the same."}}
        target = self.pages.get(to)
        if target and not target["text"].lstrip().upper().startswith("#REDIRECT"):
            return {"error": {"code": "articleexists", "info": "A page of that name already exists."}}
        pg = self.pages.pop(frm)
        self.pages[to] = pg
        for rid, (t, txt) in list(self.history.items()):
            if t == frm:
                self.history[rid] = (to, txt)
        self.moves.append((frm, to, user, params.get("reason", "")))
        if not params.get("noredirect"):
            self.add_page(frm, "#REDIRECT [[%s]]" % to, user, params.get("reason", ""))
        return {"move": {"from": frm, "to": to, "reason": params.get("reason", "")}}

    def upload(self, params, cookie, user):
        err = self._check_token(params, cookie, user)
        if err:
            return err
        name = params.get("filename", "").replace(" ", "_")
        data = params.get("file", b"")
        if "upload" not in self.rights:
            return {"error": {"code": "permissiondenied", "info": "You don't have permission to upload."}}
        if name in self.files:
            if self.file_data.get(name) == data:
                return {"error": {"code": "fileexists-no-change", "info": "The upload is an exact duplicate of the current version."}}
            if "reupload" not in self.rights:
                return {"error": {"code": "fileexists-forbidden", "info": "A file with this name exists already."}}
            if not params.get("ignorewarnings"):
                return {"upload": {"result": "Warning", "warnings": {"exists": name}, "filekey": "x"}}
        self.add_file(name, data)
        self.edits.append((user, "File:" + name, params.get("comment", ""), False))
        return {"upload": {"result": "Success", "filename": name, "imageinfo": {"sha1": hashlib.sha1(data).hexdigest()}}}


def make_handler(wiki):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _cookie(self):
            c = self.headers.get("Cookie", "")
            for part in c.split(";"):
                k, _, v = part.strip().partition("=")
                if k == "fakewiki_session":
                    return v, False
            return secrets.token_hex(12), True

        def _reply(self, obj, cookie, new):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if new:
                self.send_header("Set-Cookie", "fakewiki_session=%s; Path=/; HttpOnly" % cookie)
            self.end_headers()
            self.wfile.write(body)

        def _go(self, raw, multipart=None):
            u = urlparse(self.path)
            if not u.path.endswith("/api.php"):
                self.send_response(404)
                self.end_headers()
                return
            params = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
            params.update({k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()})
            params.update(multipart or {})
            cookie, new = self._cookie()
            with wiki.lock:
                wiki.requests.append(self.path + " " + raw)
                obj = wiki.handle(params, cookie)
            self._reply(obj, cookie, new)

        def do_GET(self):
            self._go("")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("multipart/form-data"):
                msg = BytesParser(policy=policy.default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
                fields = {}
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    payload = part.get_payload(decode=True)
                    fields[name] = payload if part.get_filename() else payload.decode("utf-8")
                self._go("", {k: v for k, v in fields.items()})
                return
            self._go(body.decode("utf-8"))
    return H


def serve(wiki, port):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(wiki))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def sample_wiki():
    w = FakeWiki()
    w.add_page("Sample Data Hub", '<div style="display:none">Sample Data Hub. Where to start for sample data.</div>\n'
                               '<div style="background:#fff;border:1px solid #dfe3e7;border-radius:6px;padding:.9em 1.2em;margin:0 0 .8em;">\n\n'
                               "Everything about the sample in one place.\n\n</div>\n\n== Pages ==\n* [[Sample Load Procedure]]\n\n"
                               "[[Category:Reporting and Publishing]]\n")
    w.add_page("Navigation Page", "Protected navigation.\n")
    w.protected.add("Navigation Page")
    w.add_page("Old Sample", "#REDIRECT [[Sample Data Hub]]\n")
    w.files.add("Wiki_Style_Tool_Editor_700.png")
    return w


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="A stand-in MediaWiki API for trying the Wiki buttons.")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--read-needs-login", action="store_true")
    args = ap.parse_args()
    wk = sample_wiki()
    wk.read_needs_login = args.read_needs_login
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(wk))
    print("Fake wiki API at http://127.0.0.1:%d/w/api.php  (login %s / %s)" % (args.port, BOT_USER, BOT_PASS))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
