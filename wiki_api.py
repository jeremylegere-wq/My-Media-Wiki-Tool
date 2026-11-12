"""
wiki_api.py - talks to the Wiki through its MediaWiki API, so people can open
a page from the wiki, edit it in the tool and publish it back.

    s = WikiSession(api_url)
    s.login("YourWikiName@BotName", bot_password)    # a bot password from Special:BotPasswords
    page = s.get_page("Sample Data Hub")                 # text, revision, timestamps, protection
    s.publish("Sample Data Hub", new_text, "Tidied the steps", base=page)

It can also read many pages at once
(get_pages, list_prefix), rename pages (move), and upload pictures (upload,
file_info).

Rules this module keeps:
- The bot password is used once, to log in, and then dropped. It is never saved,
  logged or sent anywhere except the wiki's API address.
- The session lives in memory only and ends when the tool closes or on logout.
- Edits are normal edits under the person's own name (no bot flag), so they show
  in Recent changes and the page history like any other edit.
- Every edit names the revision it started from, so the wiki refuses it with an
  edit conflict if someone else changed the page in the meantime.

Written for the Wiki's older MediaWiki: page text is read from either
revisions[0].slots.main["*"] or revisions[0]["*"], whichever the wiki returns.
Standard library only.
"""
import hashlib
import http.cookiejar
import json
import re
import secrets
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API = "https://your-wiki.example.com/Wiki/api.php"
TIMEOUT = 30


class WikiError(Exception):
    """A problem worth showing to the person, in plain English. code is the API's error code if there was one."""

    def __init__(self, message, code="", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def check_api_url(url):
    """The API address must be https (plain http only for this computer, which the tests use)."""
    url = (url or "").strip()
    p = urllib.parse.urlparse(url)
    local = (p.hostname or "") in ("127.0.0.1", "localhost")
    if p.scheme not in ("https", "http") or not p.hostname or (p.scheme == "http" and not local):
        raise WikiError("The wiki API address must start with https:// (for this wiki: %s)." % DEFAULT_API, "badurl")
    if not p.path.endswith("api.php"):
        raise WikiError("The wiki API address should end with api.php (for this wiki: %s)." % DEFAULT_API, "badurl")
    return url


LOGIN_MESSAGES = {
    "WrongPass": "The wiki did not accept that password. Use the bot password (shown once when you created it), not your normal password.",
    "WrongPluginPass": "The wiki did not accept that password. Use the bot password, not your normal password.",
    "Failed": "The wiki did not accept that login. Check the username is exactly YourWikiName@BotName and the password is the bot password.",
    "NotExists": "There is no wiki user with that name. The username is YourWikiName@BotName, for example YourName@WikiStyleTool.",
    "Illegal": "That username is not valid. It should look like YourWikiName@BotName.",
    "EmptyPass": "Enter the bot password.",
    "Throttled": "Too many login attempts. Wait a few minutes and try again.",
    "Blocked": "That wiki account is blocked.",
    "Aborted": "The wiki only accepts bot passwords here. Create one at Special:BotPasswords and use YourWikiName@BotName.",
}

EDIT_MESSAGES = {
    "editconflict": "Someone else changed this page after you opened it.",
    "protectedpage": "This page is protected. Only wiki admins can change it (for example the Navigation Page).",
    "cascadeprotected": "This page is protected. Only wiki admins can change it.",
    "permissiondenied": "Your bot password does not allow this. On Special:BotPasswords, give it 'Edit existing pages' and 'Create, edit, and move pages'.",
    "noedit": "Your bot password does not allow editing. On Special:BotPasswords, tick 'Edit existing pages'.",
    "nocreate": "Your bot password does not allow creating pages. On Special:BotPasswords, tick 'Create, edit, and move pages'.",
    "cantcreate": "Your bot password does not allow creating pages. On Special:BotPasswords, tick 'Create, edit, and move pages'.",
    "articleexists": "A page with this title already exists. Open it from the wiki first.",
    "missingtitle": "That page no longer exists on the wiki.",
    "pagedeleted": "That page was deleted after you opened it.",
    "readapidenied": "The wiki needs you to log in to read pages. Connect to the wiki first.",
    "assertuserfailed": "Your wiki session has ended. Connect to the wiki again.",
    "assertbotfailed": "Your wiki session has ended. Connect to the wiki again.",
    "notloggedin": "Your wiki session has ended. Connect to the wiki again.",
    "spamdetected": "The wiki's spam filter refused the page. A web address in it is on the blocked list.",
    "abusefilter-disallowed": "One of the wiki's edit filters refused the change.",
    "contenttoobig": "The page is too large for the wiki.",
    "invalidtitle": "That is not a valid page title.",
    "ratelimited": "The wiki is limiting how often you can save. Wait a minute and try again.",
    "readonly": "The wiki is read-only at the moment (often during maintenance). Try again later.",
    "cantmove": "Your bot password does not allow renaming (moving) pages. On Special:BotPasswords, tick 'Create, edit, and move pages'.",
    "cantmove-anon": "Your wiki session has ended. Connect to the wiki again.",
    "selfmove": "The new title is the same as the old one.",
    "immobilenamespace": "Pages of this kind cannot be renamed.",
    "protectedtitle": "That title is protected from being created. Ask a wiki admin.",
    "nosuchpage": "That page no longer exists on the wiki.",
    "uploaddisabled": "Uploading files is turned off on this wiki. Upload the pictures by hand instead.",
    "fileexists-no-change": "That picture is already on the wiki, exactly the same.",
    "fileexists-forbidden": "A picture with that name already exists and your bot password cannot replace it. On Special:BotPasswords, tick 'Upload, replace, and move files'.",
    "filetype-banned": "The wiki does not accept that type of file.",
    "verification-error": "The wiki did not accept the file (it failed the wiki's file checks).",
    "mustbeloggedin": "Your wiki session has ended. Connect to the wiki again.",
}


def _clean_title(title):
    t = re.sub(r"\s+", " ", str(title or "").replace("_", " ")).strip()
    if not t or re.search(r"[\[\]{}|#<>]", t):
        raise WikiError("That is not a valid page title. Titles cannot contain [ ] { } | # < or >.", "invalidtitle")
    return t


class WikiSession:
    def __init__(self, api_url=DEFAULT_API, use_proxy=True):
        self.api = check_api_url(api_url)
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar),
                    urllib.request.HTTPSHandler(context=ssl.create_default_context())]
        if not use_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)
        self.user = ""            # set after a successful login
        self.rights = []
        self.csrf = ""
        self.user_agent = "Wiki-Style-Tool (local article editor; Python urllib)"

    # ------------------------------------------------------------ plumbing
    def call(self, params, post=False):
        """One API request. Returns the decoded JSON, or raises WikiError."""
        params = dict(params)
        params["format"] = "json"
        data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode("utf-8")
        if post:
            req = urllib.request.Request(self.api, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
        else:
            req = urllib.request.Request(self.api + "?" + data.decode("ascii"), method="GET")
        return self._send(req)

    def _send(self, req):
        req.add_header("User-Agent", self.user_agent)
        req.add_header("Accept", "application/json")
        try:
            with self.opener.open(req, timeout=TIMEOUT) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise WikiError("The wiki refused the connection (HTTP %d). Check you are on the company network or VPN "
                                "and that the API address is right." % e.code, "http%d" % e.code, 502)
            raise WikiError("The wiki answered with an error (HTTP %d %s)." % (e.code, e.reason), "http%d" % e.code, 502)
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
                raise WikiError("This computer does not trust the wiki's security certificate. On a work computer this usually "
                                "means Python is not using the Windows certificate store; see Troubleshooting on the "
                                "Wiki Style Tool pages.", "ssl", 502)
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) or "Name or service not known" in str(reason) \
                    or "getaddrinfo" in str(reason) or "Connection refused" in str(reason):
                raise WikiError("Cannot reach the wiki. Check you are on the company network or VPN.", "unreachable", 502)
            raise WikiError("Cannot reach the wiki: %s" % reason, "unreachable", 502)
        except (socket.timeout, TimeoutError):
            raise WikiError("The wiki took too long to answer. Try again.", "timeout", 504)
        try:
            j = json.loads(raw.decode("utf-8-sig"))
        except ValueError:
            raise WikiError("The wiki sent back something that is not API data. Check the API address ends with api.php.", "notjson", 502)
        err = j.get("error") if isinstance(j, dict) else None
        if err:
            code = err.get("code", "")
            raise WikiError(EDIT_MESSAGES.get(code) or "The wiki said: %s" % (err.get("info") or code), code)
        return j

    def call_multipart(self, fields, files):
        """A POST with files (action=upload). files: {field: (file name, bytes, content type)}."""
        boundary = "----WikiStyleTool" + secrets.token_hex(12)
        body = []
        for k, v in fields.items():
            if v is None:
                continue
            body.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n'
                         % (boundary, k)).encode("utf-8") + str(v).encode("utf-8") + b"\r\n")
        for k, (fname, data, ctype) in files.items():
            body.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                         % (boundary, k, fname.replace('"', ""), ctype)).encode("utf-8") + data + b"\r\n")
        body.append(("--%s--\r\n" % boundary).encode("ascii"))
        req = urllib.request.Request(self.api, data=b"".join(body), method="POST")
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
        return self._send(req)

    def _write(self, params, files=None):
        """A change to the wiki (edit, move, upload): adds the edit token, and gets a new one once if it has expired."""
        if not self.user:
            raise WikiError("Connect to the wiki first.", "notloggedin", 401)
        params = dict(params)
        for attempt in (1, 2):
            if not self.csrf:
                self.csrf = self.token("csrf")
            params["token"] = self.csrf
            try:
                if files:
                    params["format"] = "json"
                    return self.call_multipart(params, files)
                return self.call(params, post=True)
            except WikiError as e:
                if e.code == "badtoken" and attempt == 1:
                    self.csrf = ""
                    continue
                if e.code in ("assertuserfailed", "assertbotfailed", "notloggedin", "mustbeloggedin"):
                    self.user, self.rights, self.csrf = "", [], ""
                raise

    def token(self, kind):
        j = self.call({"action": "query", "meta": "tokens", "type": kind})
        tok = j.get("query", {}).get("tokens", {}).get(kind + "token", "")
        if not tok:
            raise WikiError("The wiki did not give a %s token. It may be an older MediaWiki than the tool supports." % kind, "notoken", 502)
        return tok

    # ------------------------------------------------------------ session
    def login(self, username, password):
        username = (username or "").strip()
        if "@" not in username:
            raise WikiError("Use your bot username, YourWikiName@BotName (for example YourName@WikiStyleTool). "
                            "Create one at Special:BotPasswords.", "Illegal")
        if not password:
            raise WikiError(LOGIN_MESSAGES["EmptyPass"], "EmptyPass")
        lt = self.token("login")
        j = self.call({"action": "login", "lgname": username, "lgpassword": password, "lgtoken": lt}, post=True)
        password = None  # noqa: F841 - dropped as soon as it has been used
        res = j.get("login", {})
        if res.get("result") != "Success":
            code = res.get("result", "Failed")
            reason = res.get("reason", "")
            raise WikiError(LOGIN_MESSAGES.get(code, "The wiki did not accept that login (%s). %s" % (code, reason)).strip(), code, 401)
        self.user = res.get("lgusername") or username.split("@")[0]
        self.csrf = ""
        self.refresh_rights()
        return self.status()

    def refresh_rights(self):
        j = self.call({"action": "query", "meta": "userinfo", "uiprop": "rights|groups"})
        ui = j.get("query", {}).get("userinfo", {})
        if "anon" in ui:
            self.user, self.rights = "", []
        else:
            self.user = ui.get("name", self.user)
            self.rights = ui.get("rights", [])
        return ui

    def status(self):
        r = self.rights
        return {"connected": bool(self.user), "user": self.user, "api": self.api,
                "canEdit": "edit" in r, "canCreate": "createpage" in r, "canMove": "move" in r,
                "canUpload": "upload" in r, "canReupload": "reupload" in r or "reupload-own" in r}

    def logout(self):
        if self.user:
            try:
                self.call({"action": "logout", "token": self.token("csrf")}, post=True)
            except WikiError:
                pass  # older wikis log out without a token; the cookies are cleared below anyway
        self.jar.clear()
        self.user, self.rights, self.csrf = "", [], ""

    # ------------------------------------------------------------ reading
    def get_page(self, title):
        """The page as it is now. exists is False for a page that has not been created yet."""
        title = _clean_title(title)
        j = self.call({"action": "query", "prop": "revisions|info", "rvprop": "content|timestamp|ids", "rvslots": "main",
                       "inprop": "protection", "titles": title, "curtimestamp": "1"})
        q = j.get("query", {})
        pages = q.get("pages", {})
        page = next(iter(pages.values()), {}) if isinstance(pages, dict) else (pages[0] if pages else {})
        norm = {n.get("from"): n.get("to") for n in q.get("normalized", [])}
        out = {"title": page.get("title") or norm.get(title, title), "exists": "missing" not in page and "invalid" not in page,
               "text": "", "revid": 0, "timestamp": "", "starttimestamp": j.get("curtimestamp", ""), "redirect": "",
               "protected": "", "pageid": page.get("pageid", 0)}
        if "invalid" in page:
            raise WikiError("That is not a valid page title.", "invalidtitle")
        for p in page.get("protection", []):
            if p.get("type") == "edit" and p.get("level"):
                out["protected"] = p["level"]
        if not out["exists"]:
            return out
        revs = page.get("revisions") or []
        if revs:
            rev = revs[0]
            if "slots" in rev:
                main = rev["slots"].get("main", {})
                text = main.get("*", main.get("content", ""))
            else:
                text = rev.get("*", rev.get("content", ""))
            out.update(text=(text or "").lstrip("﻿"), revid=rev.get("revid", 0), timestamp=rev.get("timestamp", ""))
        if "redirect" in page:
            m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", out["text"], re.I)
            out["redirect"] = m.group(1).strip() if m else ""
        return out

    def search(self, prefix, limit=12):
        """Page titles that start with what was typed (main namespace)."""
        prefix = re.sub(r"\s+", " ", str(prefix or "")).strip()
        if not prefix:
            return []
        try:
            j = self.call({"action": "query", "list": "prefixsearch", "pssearch": prefix, "pslimit": str(limit), "psnamespace": "0"})
            return [p["title"] for p in j.get("query", {}).get("prefixsearch", [])]
        except WikiError as e:
            if e.code in ("readapidenied", "unreachable", "ssl", "timeout") or e.code.startswith("http"):
                raise
        j = self.call({"action": "query", "list": "allpages", "apprefix": prefix, "aplimit": str(limit)})
        return [p["title"] for p in j.get("query", {}).get("allpages", [])]

    def missing_files(self, names):
        """Which of these picture names are not on the wiki yet."""
        names = [n for n in dict.fromkeys(names) if n]
        missing = []
        for i in range(0, len(names), 40):
            chunk = names[i:i + 40]
            j = self.call({"action": "query", "titles": "|".join("File:" + n for n in chunk), "prop": "info"})
            norm = {n.get("to"): n.get("from") for n in j.get("query", {}).get("normalized", [])}
            for p in j.get("query", {}).get("pages", {}).values():
                if "missing" in p:
                    t = p.get("title", "")
                    t = norm.get(t, t)
                    missing.append(re.sub(r"^(File|Image):", "", t))
        return missing

    def get_pages(self, titles, batch=20):
        """Many pages at once. Returns {title as given: page}, each page like get_page plus "user" and "comment"
        (who made the latest edit, and its summary), and the time the pages were read."""
        titles = [_clean_title(t) for t in dict.fromkeys(titles)]
        out, started = {}, ""
        for i in range(0, len(titles), batch):
            chunk = titles[i:i + batch]
            j = self.call({"action": "query", "prop": "revisions|info", "rvprop": "content|timestamp|ids|user|comment",
                           "rvslots": "main", "inprop": "protection", "titles": "|".join(chunk), "curtimestamp": "1"}, post=True)
            started = started or j.get("curtimestamp", "")
            q = j.get("query", {})
            norm = {n.get("to"): n.get("from") for n in q.get("normalized", [])}
            pages = q.get("pages", {})
            for page in (pages.values() if isinstance(pages, dict) else pages):
                t = page.get("title", "")
                asked = norm.get(t, t)
                p = self._page_from(page, j.get("curtimestamp", ""))
                if p["exists"] and not p["revid"]:
                    p = self.get_page(t)  # the answer was cut short for size: read this one on its own
                    p.update(self._last_edit(t))
                out[asked] = p
        for t in titles:
            out.setdefault(t, {"title": t, "exists": False, "text": "", "revid": 0, "timestamp": "", "starttimestamp": started,
                               "redirect": "", "protected": "", "pageid": 0, "user": "", "comment": ""})
        return out

    def _last_edit(self, title):
        j = self.call({"action": "query", "prop": "revisions", "rvprop": "user|comment", "titles": title})
        for page in j.get("query", {}).get("pages", {}).values():
            rev = (page.get("revisions") or [{}])[0]
            return {"user": rev.get("user", ""), "comment": rev.get("comment", "")}
        return {"user": "", "comment": ""}

    def _page_from(self, page, curtimestamp):
        out = {"title": page.get("title", ""), "exists": "missing" not in page and "invalid" not in page, "text": "", "revid": 0,
               "timestamp": "", "starttimestamp": curtimestamp, "redirect": "", "protected": "", "pageid": page.get("pageid", 0),
               "user": "", "comment": ""}
        for p in page.get("protection", []):
            if p.get("type") == "edit" and p.get("level"):
                out["protected"] = p["level"]
        revs = page.get("revisions") or []
        if out["exists"] and revs:
            rev = revs[0]
            if "slots" in rev:
                main = rev["slots"].get("main", {})
                text = main.get("*", main.get("content", ""))
            else:
                text = rev.get("*", rev.get("content", ""))
            out.update(text=(text or "").lstrip("\ufeff"), revid=rev.get("revid", 0), timestamp=rev.get("timestamp", ""),
                       user=rev.get("user", ""), comment=rev.get("comment", ""))
        if "redirect" in page:
            m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", out["text"], re.I)
            out["redirect"] = m.group(1).strip() if m else ""
        return out

    def list_prefix(self, prefix, namespace=0, redirects=False):
        """Every page title starting with prefix (redirects left out unless asked for)."""
        out, cont = [], {}
        while True:
            params = {"action": "query", "list": "allpages", "apprefix": prefix, "apnamespace": str(namespace), "aplimit": "500",
                      "apfilterredir": "all" if redirects else "nonredirects"}
            params.update(cont)
            j = self.call(params)
            out += [p["title"] for p in j.get("query", {}).get("allpages", [])]
            c = j.get("continue") or j.get("query-continue", {}).get("allpages")
            if not c or len(out) > 5000:
                return out
            cont = {k: v for k, v in c.items() if k != "continue"} if "continue" in j else c

    def file_info(self, names):
        """{file name: sha1 of the file on the wiki, or "" if there is no such file}."""
        out = {}
        names = [n for n in dict.fromkeys(names) if n]
        for i in range(0, len(names), 40):
            chunk = names[i:i + 40]
            j = self.call({"action": "query", "titles": "|".join("File:" + n for n in chunk), "prop": "imageinfo", "iiprop": "sha1|size"})
            norm = {n.get("to"): n.get("from") for n in j.get("query", {}).get("normalized", [])}
            for p in j.get("query", {}).get("pages", {}).values():
                t = norm.get(p.get("title", ""), p.get("title", ""))
                name = re.sub(r"^(File|Image):", "", t)
                ii = (p.get("imageinfo") or [{}])[0]
                out[name] = "" if "missing" in p and not p.get("imageinfo") else ii.get("sha1", "")
        for n in names:
            out.setdefault(n, "")
        return out

    # ------------------------------------------------------------ writing
    def move(self, old, new, reason, leave_redirect=True):
        """Rename a page. Its history goes with it; the old title becomes a redirect (unless asked not to)."""
        params = {"action": "move", "from": _clean_title(old), "to": _clean_title(new), "reason": (reason or "").strip()[:480],
                  "movetalk": "1"}
        if not leave_redirect:
            params["noredirect"] = "1"
        j = self._write(params)
        mv = j.get("move", {})
        if not mv.get("to"):
            raise WikiError("The wiki did not rename the page.", "notmoved")
        return {"from": mv.get("from", old), "to": mv.get("to", new)}

    def upload(self, filename, data, comment, text="", content_type="application/octet-stream"):
        """Upload a file, replacing the one already there with the same name. Returns {"result", "filename", "nochange"}."""
        fields = {"action": "upload", "filename": filename, "comment": (comment or "").strip()[:480], "text": text,
                  "ignorewarnings": "1"}
        try:
            j = self._write(fields, {"file": (filename, data, content_type)})
        except WikiError as e:
            if e.code == "fileexists-no-change":
                return {"result": "Success", "filename": filename, "nochange": True}
            raise
        up = j.get("upload", {})
        if up.get("result") != "Success":
            warn = up.get("warnings") or {}
            if "exists" in warn or "duplicate" in warn or "nochange" in warn:
                if up.get("result") == "Warning" and "nochange" in warn:
                    return {"result": "Success", "filename": filename, "nochange": True}
            raise WikiError("The wiki did not take the file %s (%s)." % (filename, up.get("result") or "no reason given"),
                            "notuploaded")
        return {"result": "Success", "filename": up.get("filename", filename), "nochange": False}

    def publish(self, title, text, summary, base=None, minor=False, force=False):
        """Save the page. base is the page as it was when it was opened (from get_page), or None for a new page.
        force=True publishes over someone else's newer change (after the person has said so)."""
        if not self.user:
            raise WikiError("Connect to the wiki first.", "notloggedin", 401)
        title = _clean_title(title)
        params = {"action": "edit", "title": title, "text": text, "summary": (summary or "").strip()[:480] or
                  "Edited with the Wiki Style Tool", "assert": "user"}
        if minor:
            params["minor"] = "1"
        if base and base.get("exists"):
            params["nocreate"] = "1"
            if force:
                latest = self.get_page(title)
                params["basetimestamp"] = latest.get("timestamp", "")
                params["starttimestamp"] = latest.get("starttimestamp", "")
            else:
                params["basetimestamp"] = base.get("timestamp", "")
                params["starttimestamp"] = base.get("starttimestamp", "")
        else:
            params["createonly"] = "1"
        j = self._write(params)
        ed = j.get("edit", {})
        if ed.get("result") != "Success":
            if "captcha" in ed:
                raise WikiError("The wiki asked for a CAPTCHA, which the tool cannot answer. Save this page on the wiki instead.", "captcha")
            raise WikiError("The wiki did not save the page (%s)." % (ed.get("result") or "no reason given"), ed.get("code", "notsaved"))
        return {"title": ed.get("title", title), "newrevid": ed.get("newrevid", 0), "newtimestamp": ed.get("newtimestamp", ""),
                "nochange": "nochange" in ed, "new": "new" in ed}


def sha1_hex(data):
    """A file's SHA-1 as the wiki reports it (imageinfo sha1), to tell whether a picture has changed."""
    return hashlib.sha1(data).hexdigest()


def page_url(api_url, title):
    """The normal address of a page, from the API address (…/api.php -> …/index.php?title=…)."""
    base = api_url.rsplit("/", 1)[0]
    return "%s/index.php?title=%s" % (base, urllib.parse.quote(title.replace(" ", "_"), safe=":/()_-,."))


def diff_html(old, new, context=2, max_lines=400):
    """A compact line-by-line view of what publishing will change, for the publish dialog.
    Returns (html, added, removed)."""
    import difflib
    import html as _html
    a, b = (old or "").split("\n"), (new or "").split("\n")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    rows, added, removed, shown = [], 0, 0, 0

    def row(cls, sign, line):
        line = line if len(line) <= 600 else line[:600] + " …"
        return '<div class="dl %s"><span class="sg">%s</span>%s</div>' % (cls, sign, _html.escape(line) or "&nbsp;")
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            n = i2 - i1
            if n <= context * 2 + 1:
                rows += [row("eq", " ", x) for x in a[i1:i2]]
            else:
                if rows:
                    rows += [row("eq", " ", x) for x in a[i1:i1 + context]]
                rows.append('<div class="dl gap">… %d unchanged line%s …</div>' % (n - (context * 2 if rows else context),
                                                                                  "" if n == 1 else "s"))
                rows += [row("eq", " ", x) for x in a[i2 - context:i2]]
            continue
        for x in a[i1:i2]:
            rows.append(row("del", "−", x))
            removed += 1
        for x in b[j1:j2]:
            rows.append(row("add", "+", x))
            added += 1
        shown += 1
    if not added and not removed:
        return '<div class="dl gap">No changes: the page on the wiki already says exactly this.</div>', 0, 0
    if len(rows) > max_lines:
        rows = rows[:max_lines] + ['<div class="dl gap">… and more. The list is cut short here.</div>']
    return "".join(rows), added, removed
