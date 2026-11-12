# Developing the Wiki Style Tool

A guide for whoever works on the tool next. For using the tool, see
`README.txt` and the Wiki Style Tool pages on the Wiki. For what changed
and when, see `CHANGELOG.md`.

## What it is

A small Python program that runs on the user's own computer and serves an
editor to their browser at `http://127.0.0.1:8765/`. People write on a page
that already looks like the Wiki, starting from a template, and press
**Export to wiki** to get wikitext in our house style. It can also open
existing wiki pages, Word documents and emails, and connect to
the wiki with the person's own bot password to open pages and publish them.

## Principles (please keep these)

1. **Python does the logic, the browser edits.** Export, import, checks,
   templates and file reading are all in Python. `static/editor.js` only
   draws blocks and records what people type.
2. **Standard library only.** Python 3.8+ is all anyone needs for the
   editor. One optional package: `extract-msg` for Outlook `.msg` files.
   Import them lazily and say plainly what to install when one is missing.
3. **Offline and rule-based.** No AI, and nothing leaves the computer except
   what a person deliberately publishes to the wiki. The server listens on
   127.0.0.1 only and checks the host name and origin of every request; wiki
   actions also need the `X-WST: 1` header, which other web sites cannot send.
4. **Nothing is lost on import.** If the tool has a block for something, it
   becomes that block. If not, it becomes a layout (look kept, text
   editable). If even that is not safe, it stays as wiki code. Never drop
   content.
5. **Untouched means unchanged.** A page made with the tool, opened and
   exported again, must come back exactly. An untouched layout must come back
   character for character. `selftest.py` checks both.
6. **Never make things up.** Anything the tool cannot know becomes a grey
   prompt, which exports as a hidden `<!-- TODO: ... -->` note and is listed
   by Check.
7. **House rules are enforced, not suggested.** Role titles rather than names,
   no passwords, tokens or account IDs, no SharePoint sharing links, no contact
   details, no image widths (pictures are 700px or less), a hidden first line,
   `__TOC__` on content pages.
8. **Credentials are never kept.** The bot password is used once to log in
   and dropped. Never write it to disk, a log, a draft, localStorage or an
   error message. `selftest.py` checks nothing on disk contains it. Each person
   uses their own bot password; edits go under their own name, without the
   bot flag.
9. **Never overwrite someone else's edit silently.** Every publish sends the
   revision it started from; replacing a newer edit is a separate, deliberate
   step, and the replaced version is backed up to `output/wiki_backups`. 
10. **A refresh with nothing new changes nothing.** The same sheets must build
   byte-for-byte the same pages and pictures, so comparing again after
   publishing shows everything as the same. `selftest.py` checks this, and
   that the three published summary pages are rebuilt exactly.
11. **Never delete.** Retired measures keep their page; earlier versions are
   reached through the page history (oldid links), not copies.

## Getting started

```
git clone <the repository>        (or unzip the repository zip)
cd wiki_style_tool
python wiki_style_tool.py         (Windows: py wiki_style_tool.py)
python selftest.py                (must end with "0 failed")
```

`python wiki_style_tool.py --no-browser --port 8790` starts it without opening
a browser, on another port. Close the window or press Ctrl+C to stop it.
Python changes need a restart; changes to `static/` need only a browser
refresh.

## Where things are

| File | What it does |
|---|---|
| `wiki_style_tool.py` | The web server and launcher. Routes, security checks, saving, `--make-shortcut`. `VERSION` lives here. |
| `house_style.py` | Every colour and style on exported pages, and the functions that write each block's wikitext (`hero`, `h2`, `step`, `callout`, `table`, `cards`, `flow`, `collapse`, `figure`, `codebox`, `email`...). The editor reads the same styles from `/api/style`. |
| `exporter.py` | A page (the editor's blocks) to wikitext: `export(doc)` returns `(text, notes)`. |
| `importer.py` | Wikitext back to blocks (`import_wiki`), plain or Word text to blocks (`import_plain`). One recogniser per block style (`r_hero`, `r_step`, `r_table`...), then `keep()` for anything else. |
| `layout.py` | Layout blocks: keeps a layout exactly and makes its text editable. |
| `rich.py` | Formatted text: the editor's small HTML subset to wikitext (`to_wiki`, `to_inline`) and back (`wiki_to_html`, `inline_to_html`). |
| `templates.py` | The templates, built from helper functions. |
| `doc_import.py` | Reads `.docx`, `.eml` and `.msg` files. |
| `wiki_lint.py` | Check (`check`) and the safe fixes (`fix`). |
| `wiki_api.py` | The wiki's MediaWiki API: `WikiSession` (login with a bot password, `get_page`, `search`, `missing_files`, `publish`, `logout`), `diff_html` for the Publish window, and plain-English error messages. Standard library (`urllib`, `http.cookiejar`). |
| `fake_wiki.py` | A stand-in MediaWiki API for tests and for trying the Wiki buttons by hand. Keeps page history; supports moves and uploads. |
| `static/` | `index.html`, `editor.js`, `editor.css`: the editor. |
| `selftest.py` | The tests. No browser needed. |
| `test_files/` | Sample Word, email, SQL and picture files. |
| `dev/` | Developer scripts (not in the release zip). |
| `docs/` | The wiki help pages, their pictures and the scripts that build them. |

## How a page moves through the tool

```
editor (blocks as JSON) --POST /api/export--> exporter.export --> house_style --> wikitext
wikitext --POST /api/import--> importer.chunks --> recognisers r_*() --> block
                                                  \--> keep() --> layout.build() or a "raw" block

wiki --GET /api/wiki/open--> wiki_api.get_page --> importer --> doc with doc._wiki (title, revid, timestamps)
doc --POST /api/wiki/preview--> exporter + current page --> diff, Check, missing pictures
doc --POST /api/wiki/publish--> backup of the current page --> wiki_api.publish (basetimestamp) --> new doc._wiki
```

`doc._wiki` records which wiki page and revision a page was opened from. It is
saved with drafts, so a draft can be published later and still be protected
against overwriting someone else's edit. Publishing to a different title than
`doc._wiki.title` creates a new page and will not replace an existing one.

`importer.chunks()` splits a page into chunks: HTML blocks (balanced `<div>`,
`<h2>`, `<h3>`), wiki tables, `<pre>`, `== headings ==`, categories, magic
words, comments and runs of text. Each HTML chunk is tried against every
recogniser in turn; the first that matches wins.

### The page (doc) model

```
{ "title": "...", "summary": "...", "toc": true, "categories": ["Wiki Help"],
  "blocks": [ { "id": "...", "type": "...", ...fields } ] }
```

| Block `type` | Fields |
|---|---|
| `hero` | `kicker`, `title` (empty = page title), `sub` (rich), `pills` |
| `card`, `text` | `html` (rich) |
| `h2`, `h3` | `text`, `color` |
| `step` | `html`, `color`, `start` (optional number) |
| `callout` | `kind` (note, warning, danger, tip, old), `title`, `html` |
| `table` | `rows` (rich cells), `header`, `keyval`, `color` |
| `cards` | `color`, `items`: `title`, `html`, optional `color` |
| `flow` | `color`, `stages`: `title`, `html` (one item per line), optional `color` |
| `collapse` | `title`, `html`, `collapsed`, `color` |
| `code` | `lang` (sql or text), `title`, `code` |
| `image` | `file`, `full`, `caption` |
| `email` | `caption`, `emails`: `from`, `sent`, `to`, `cc`, `subject`, `html` |
| `divider` | none |
| `raw` | `wiki` (kept exactly) |
| `layout` | `tpl`, `view`, `leaves` (see below) |

"Rich" fields hold the editor's HTML subset: `p, br, b, i, u, s, code, a
href="wiki:Page" or https:..., ul, ol, li, sub, sup`, `<span data-pill="green">`
for status labels and `data-ph="1"` on prompts. A block can also have
`"ph": {"field.path": true}` for plain fields that still hold their prompt.

### Layout blocks

`layout.build(wikitext)` splits the wikitext into the **frame** (HTML tags,
wiki table lines, heading `=` signs, hidden comments: kept as written) and
**text** in between. Each piece of text the editor can handle becomes a leaf:

```
"tpl":    the wikitext with each leaf replaced by N
"view":   safe HTML for the editor, with <wst-leaf data-i="N"></wst-leaf> for each leaf
"leaves": [{ "wiki": original text, "html": current, "html0": as imported,
             "mode": "inline" | "block", "cell": in a table cell, "ks": keep spaces }]
```

On export a leaf whose `html` converts to the same wikitext as `html0` is
written back as `wiki`, unchanged. `build()` refuses (returns `None`) when it
meets an extension tag (`<syntaxhighlight>`, `<ref>`, `<gallery>`...), a
template that spans lines, an unclosed table, or a layout with no editable
text. As a safety net it also refuses if exporting the untouched block would
not give back exactly what came in.

## Testing

- **`python selftest.py`**: run before every commit. It builds every template,
  round-trips them, tests the regressions in this changelog, layouts, the
  Word and email readers, the web server (including its security checks).
- **`python dev/check_pages.py dev/pages --fuzz`**: runs real wiki pages
  through the tool. Save pages' wikitext as `.txt` files in `dev/pages/`
  (ignored by git: real pages can hold internal details). It reports pages
  that change on a second round trip, gain Check errors or lose words, and
  with `--fuzz` it edits every piece of layout text and checks the result.
  It also prints how much page text is left as plain wiki code: use that
  number to judge whether an import change helps.
- **`python dev/preview_pages.py file.txt ... --images docs/images -o preview.html`**:
  an approximate preview of wikitext without the wiki.
- **The wiki features without the wiki**: `python fake_wiki.py --port 8899`,
  then `python wiki_style_tool.py --wiki-api http://127.0.0.1:8899/w/api.php`
  and connect as `Tester@StyleTool` with the made-up password printed by
  `fake_wiki.py`. `selftest.py` does the same automatically, with both the
  older and newer MediaWiki content formats. Never test publishing against the
  real wiki with real pages; use a page in your own user space
  (`User:YourName/Test`) if you must.
- **The browser**: test editor changes by hand in Edge or Chrome. Headless
  Chromium with Playwright works for scripted checks; `window.WST` gives
  access to the page (`WST.doc`, `WST.load(doc)`, `WST.render()`).

## Releasing

1. Move the `[Unreleased]` notes in `CHANGELOG.md` under a new
   `## [x.y.z] - YYYY-MM-DD` heading.
2. Set `VERSION` in `wiki_style_tool.py` to match, and the version line at the
   top of `README.txt` (add a "Changes in version x.y" section there too).
3. `python dev/make_release.py`: runs the tests, checks the versions match and
   writes `dist/wiki_style_tool.zip`.
4. Commit, then tag: `git tag -a vx.y.z -m "x.y.z: what changed"`.
5. Put the zip in Application Development Team > 03_Python Projects.
6. Update the wiki: in `docs/build_docs.py` change the Version row and add a
   row to the version history, run `python docs/build_docs.py`, and publish
   the changed pages from `docs/pages/` (see `docs/README.md`).
7. Tell the team what changed, and anything they should re-check.

## Git

- Work on a branch per change: `git switch -c fix-table-pipes`.
- Commit messages: a short summary line, a blank line, then what changed and
  why. Mention the user-visible effect.
- Tags mark releases (`v3.2.0`). Never move a tag; release a new version.
- `.gitattributes` keeps `.bat` files in Windows line endings and everything
  else in LF, so diffs stay clean between Windows and other computers.
- To share the repository on a Git server: `git remote add origin <url>`, then
  `git push -u origin main --tags`.

## Things that have bitten us

MediaWiki
- The CSS `font:` shorthand resets `line-height`. Put `line-height` after
  `font:` or the number in a step circle sits at the top.
- `<nowiki>` text is shown exactly as written, including `<!-- -->`.
- Inside a wiki table cell, `|` and `||` split cells. Escape as `&#124;`.
- A line that starts with `*`, `#`, `:`, `;`, `{|`, `|`, `!`, `=` or a space
  is wiki markup. `rich.safe_line()` escapes the first character.
- `<DATA_NAME>` and other unknown tags are shown as text, not hidden.
- `[https://x https://x]` and a bare `https://x` look the same; the tool
  writes the bare form.
- `<u>`, `<font>` and `<center>` are old tags; use inline styles.
- The hidden first line must not contain `< > [ ] { } | =`: they break search.

Python
- `str.strip("abc")` strips a *set of characters*, not a string. That bug cut
  the B or R off list items in 3.0.0 and 3.1.0. Use a loop (see
  `rich._strip_br`).
- `%` formatting: a literal `%` in a style needs `%%`, and a `%%` that
  reaches a page breaks the style (Check now flags it).

Browser
- The `hidden` attribute loses to any CSS `display` rule; the stylesheet has
  `[hidden]{display:none !important}`.
- `contenteditable` produces untidy HTML. Everything that arrives in a field
  goes through `sanitize()` in `editor.js` and again through `rich.py`.
- The page in progress is saved to `localStorage` on every change and on
  `beforeunload`, so tests that load a document should use `WST.load()`.

## Known limits and ideas

- Layouts let people change text, not structure. A **table diagram block**
  (tables, columns, keys, relationships) would let people add a column
  without touching code, for pages like Explore and the database objects
  pages.
- Pictures in their own frames, preformatted (space-indented) text and
  `<syntaxhighlight>` stay as wiki code. `<syntaxhighlight lang="sql">` could
  open as an SQL code box.
- Batch conversion of a folder of files was dropped in 3.0.0.
- The wiki connection was built against the Wiki's API as the earlier
  wiki scripts used it, and tested against `fake_wiki.py` only. Its first runs
  on the real wiki should be on a test page.
- Publishing from the editor does not upload pictures. `wiki_api.upload()` exists, so
  the Picture block's 700px and full-size copies could be uploaded the same
  way (the bot password would need "Upload new files").
- Windows authentication (NTLM) in front of the wiki is not supported;
  `urllib` cannot do it without extra packages.
- Reading `.msg` files has not been tried on a wide range of real messages.
- Not yet confirmed which Windows and Python versions it runs on at work, or
  the Desktop shortcut and `.exe` build on a work computer.
