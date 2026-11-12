WIKI STYLE TOOL  (version 1.0.0: article editor)
==================================================

What it does
  Write knowledge articles for the Wiki straight onto a page that already
  looks like the wiki. Start from a template, add blocks (steps, callouts,
  tables, cards, code boxes, FAQs and more), then press Export to wiki to get
  the wikitext in our house style, ready to paste. Or connect to the wiki with
  your own bot password to open pages from it and publish them back.
  Everything runs on your computer. Nothing is sent anywhere except, when you
  connect, to the wiki itself.

How to start
  Windows:  double-click run_wiki_style_tool.bat
  Any OS:   python wiki_style_tool.py
  Your browser opens at http://127.0.0.1:8765/ (the number can change if the
  port is busy; the black window shows the address). Leave the black window
  open while you work. Close it, or press Ctrl+C, to stop.

What you need
  Python 3.8 or later. Nothing else.
  On a work computer you can install Python yourself, without
  administrator rights: from https://www.python.org/downloads/ download the
  standalone installer (not the Python install manager), double-click it,
  tick "Add python.exe to PATH" and click Install Now.
  Optional packages (the editor works without them):
    reading Outlook .msg emails:      py -m pip install extract-msg
  Use Edge or Chrome.

Writing a page
  1. Type the page title at the top (as it will be named on the wiki).
  2. Pick a template on the left, or start writing on a blank page.
  3. Grey italic text is a prompt. Click it and type to replace it. Prompts you
     leave are never shown on the wiki: they become hidden TODO notes, and
     Check lists every one of them.
  4. Add blocks with the + next to any block, the "+ Add a block" button, the
     "+ Insert" button, or by typing / on an empty line.
  5. Click a block to see its tools: colours, callout type, add a table row or
     column, add a card or stage, move, copy and delete. Drag the handle on the
     left to move a block.
  6. Fill in the Page panel: the search summary (the hidden first line) and at
     least one category.
  7. Press Check to see what still needs doing, then Export to wiki: Copy, and
     paste into the page on the wiki. "Open the wiki edit page" opens it for you.

Templates
  Page types: topic hub, how it works, data load procedure,
  change or upgrade procedure, database objects, checks, troubleshooting (by
  symptom), tool or application, data specification, team process, useful
  links, archive or superseded notes.
  Knowledge base: how-to article, troubleshooting article, ITSM known error,
  HR knowledge base hub, writing guidelines, FAQ page, release notes.
  Click a template to preview it. "Use this template" starts a page from it;
  "Add its sections to my page" adds its sections to the end of the page you
  are on. The templates live in templates.py.

Blocks
  Text, section heading, sub-heading, intro card, note, warning, stop, tip,
  superseded, numbered step, table, key facts, cards, flow, expandable section,
  SQL code box, text code box, picture, email thread, page banner, divider and
  wiki code (anything else, kept exactly as you type it).
  In text you can use bold, italic, underline, strike-through, inline code,
  links (to a wiki page or a web address), coloured status labels and lists.

Pictures
  Add a Picture block and drop, paste or choose a picture. If it is wider than
  700px, "Download wiki copies" gives you a 700px copy for the page and a
  full-size copy it links to, with the file names already filled in. Upload
  both to the wiki with those names. No widths are ever put on the page.

Bringing things in (Open menu)
  Existing wiki page: paste its wikitext. Parts in our house style become
                      editable blocks. Other layouts keep their exact look and
                      their text stays editable (a "Layout kept as on the wiki"
                      label). Only templates and special tags stay in a Wiki
                      code block, so nothing is lost.
  Word document:      headings, numbered steps, bullets, tables and code come
                      across. Pictures in the document do not.
  Plain text:         == Heading ==, numbered lines, * bullets, indented code
                      and tab-separated tables are recognised.
  Email (.eml, .msg): use the Email thread block's Import button, or drop the
                      file on the page. Names become "Role to be added" and
                      email addresses and phone numbers are removed. Read the
                      text for names and signatures before you publish.
  Check a page:       paste any page's wikitext to check it against the house
                      rules without changing it.
  You can also drop a .docx, .txt, .json draft, .eml, .msg or a picture on the
  window.

Opening and publishing on the wiki (optional)
  1. Make a bot password once: on the wiki open Special:BotPasswords, type a
     bot name (for example WikiStyleTool), tick "Edit existing pages" and
     "Create, edit, and move pages", and save. Copy the password: it is shown
     once. Your bot username is YourWikiName@WikiStyleTool.
  2. In the tool press Wiki (top right), enter the bot username and password,
     and press Connect. The tool uses the password to log in and never saves it.
  3. Open > A page on the wiki: type a title and pick the page.
  4. Edit it, press Check, then Publish. The Publish window shows what will
     change, Check errors, hidden TODO notes and pictures not yet uploaded.
     Add an edit summary and press Publish. The edit is saved under your name.
  If someone else changed the page after you opened it, the wiki refuses the
  save and the tool tells you. A copy of each version you replace is kept in
  output\wiki_backups. Publishing does not upload pictures: use Special:Upload.
  You need the company network or VPN. The wiki's API address is
  https://your-wiki.example.com/Wiki/api.php (change it under Advanced
  in the Connect window, or start the tool with --wiki-api ADDRESS).
  Full guide: the "Wiki Style Tool - Connecting to the wiki" page on the wiki.


Drafts and saving
  The page you are working on is kept in your browser as you type, so it is
  there next time you start the tool. Save draft (Ctrl+S) writes a draft file
  to output\drafts, and Open lists them. Starting a new page or opening another
  one saves the current page as a draft first. Undo (Ctrl+Z) also undoes
  starting a new page.

Where files go
  A folder called "output" next to wiki_style_tool.py (drafts in output\drafts,
  copies of wiki pages you replaced in output\wiki_backups). Keep this folder
  when you update the tool: copy it into the new tool folder.

Keyboard
  Ctrl+B / I / U   bold, italic, underline      Ctrl+K   link
  Ctrl+E           inline code                  /        insert a block
  Ctrl+Enter       another block like this one  Alt+Up / Alt+Down  move block
  Tab              next table cell (adds a row at the end)
  Ctrl+Z / Ctrl+Y  undo, redo                   Ctrl+S   save a draft

Rules the export keeps for you
  Hidden first line (title and summary), contents box (__TOC__) before the
  first section, house colours and layouts, numbered steps that renumber
  themselves, no image widths, pictures that open full size, categories at the
  bottom. Check also warns about passwords, keys, SharePoint sharing links,
  email addresses and phone numbers.

Safety notes
  The program only listens on this computer (127.0.0.1) and refuses requests
  that come from other web sites. Use role titles instead of people's names,
  and never put passwords, keys or tokens on a wiki page.
  The bot password is used once to log in and is never saved, logged or sent
  anywhere but the wiki. The wiki connection lives in memory and ends when you
  press Disconnect or close the tool. Use your own bot password; never share
  one, and delete it on Special:BotPasswords when you no longer need it.

Files
  wiki_style_tool.py        the program (web server and launcher)
  house_style.py            every colour and style used on exported pages
  exporter.py               page to wikitext
  importer.py               wikitext, plain text and Word text back to blocks
  layout.py                 keeps other layouts exactly, with editable text
  rich.py                   text formatting to wikitext and back
  templates.py              the templates
  doc_import.py             reads Word and email files
  wiki_lint.py              the house-rule checker
  wiki_api.py               talks to the wiki: log in, open, publish, rename, upload
  fake_wiki.py              a stand-in wiki the self test uses
  static\                   the screens you see in the browser
  selftest.py               checks it all works
  test_files\               sample files to try
  run_wiki_style_tool.bat   Windows launcher
  make_desktop_shortcut.bat puts a shortcut on your Desktop
  build_exe.bat             optional: builds a single .exe (not tested yet)

Checking it works
  python selftest.py   (Windows: py selftest.py)
  Builds and checks every template, checks that pages read back in exactly,
  reads the sample Word and email files, tests the web server and its
  security checks, opens and publishes pages on a stand-in wiki, (the real wiki is never
  touched). No browser needed.



Changes in version 3.2
  Opening existing pages works all the way down. Boxes inside boxes, table
  diagrams, hand-made emails and tables with merged or coloured cells keep
  their exact look, and you can click any text in them to change it (Edit
  wiki code / Show as layout switch between the two). Older side-by-side
  boxes and arrow diagrams become Cards and Flow blocks. <nowiki> inside code
  is read properly.
  Fixed: list items starting or ending with a capital B or R lost that
  letter on export ("Run the job" became "un the job"). Code boxes with
  highlighted lines lost those lines when a page was opened. A picture's file
  name was sometimes turned into a caption.

Changes in version 3.1
  Email threads come out in the Outlook style from the Wiki page templates
  (modern layout) page. SQL code boxes use the full SSMS colours (numbers,
  variables, functions and system objects). Underlined text passes Check.

Changes from version 2
  The four tabs (Page converter, Design elements, Images, Check and batch) are
  replaced by the editor. Design elements are now blocks you add in the page,
  the Images tab is the Picture block, converting a Word file or an email is in
  the Open menu, and checking is built in. Converting a whole folder of files
  at once is not in this version.

Licence
  Add a LICENSE file before sharing this code.
