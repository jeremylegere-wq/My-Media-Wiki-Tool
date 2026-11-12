/* Wiki Style Tool - article editor (browser side).
   This file is only the editing surface. Python (wiki_style_tool.py) owns the
   templates, the wikitext export and import, the checks and saving. */
(function () {
  'use strict';
  var ST = null, TPLS = [], DOC = null, SEL = null, LAST = '', HIST = [], FUT = [];
  var IMGS = {}, CODEHTML = {}, CODEEDIT = null, EXPORT = null, SLASH = null, INS_AFTER = null, INS_REPLACE = null;
  var timers = {};
  var READONLY = false;
  var $ = function (id) { return document.getElementById(id); };

  // ------------------------------------------------------------------ helpers
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function uid() { return Math.random().toString(16).slice(2, 12); }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function debounce(key, ms, fn) { clearTimeout(timers[key]); timers[key] = setTimeout(fn, ms); }
  function st(key, c, extra) {
    var s = ST.S[key];
    if (c) s = s.split('{c}').join(ST.colours[c] || c);
    if (extra) Object.keys(extra).forEach(function (k) { s = s.split('{' + k + '}').join(extra[k]); });
    return s;
  }
  function api(path, body, raw) {
    var init = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-WST': '1' } };
    if (body !== undefined) {
      if (raw) { init.body = body; init.headers['Content-Type'] = 'application/octet-stream'; }
      else { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
    }
    return fetch(path, init).then(function (r) {
      return r.text().then(function (t) {
        var j; try { j = JSON.parse(t); } catch (e) { j = { error: t }; }
        if (!r.ok) { var err = new Error(j.error || ('Error ' + r.status)); err.code = j.code || ''; err.status = r.status; throw err; }
        return j;
      });
    });
  }
  function toast(msg, err) {
    var t = $('toast'); t.textContent = msg; t.className = 'toast' + (err ? ' err' : ''); t.hidden = false;
    debounce('toast', err ? 6000 : 2600, function () { t.hidden = true; });
  }
  function status(msg) { $('status').textContent = msg; }
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } }
  function slugify(t) { return (String(t || '').replace(/[^A-Za-z0-9._ -]/g, '_').trim().replace(/\s+/g, '_').slice(0, 100)) || 'wiki_page'; }
  function blockById(id) { for (var i = 0; i < DOC.blocks.length; i++) if (DOC.blocks[i].id === id) return DOC.blocks[i]; return null; }
  function indexOf(id) { for (var i = 0; i < DOC.blocks.length; i++) if (DOC.blocks[i].id === id) return i; return -1; }
  function getPath(o, path) { return path.split('.').reduce(function (a, k) { return a == null ? a : a[/^\d+$/.test(k) ? +k : k]; }, o); }
  function setPath(o, path, v) {
    var ks = path.split('.'), cur = o;
    for (var i = 0; i < ks.length - 1; i++) { var k = /^\d+$/.test(ks[i]) ? +ks[i] : ks[i]; if (cur[k] == null) cur[k] = /^\d+$/.test(ks[i + 1]) ? [] : {}; cur = cur[k]; }
    cur[/^\d+$/.test(ks[ks.length - 1]) ? +ks[ks.length - 1] : ks[ks.length - 1]] = v;
  }

  // ------------------------------------------------------------------ sanitising
  var OK_TAGS = { P: 1, BR: 1, B: 1, STRONG: 1, I: 1, EM: 1, U: 1, S: 1, STRIKE: 1, DEL: 1, CODE: 1, A: 1, UL: 1, OL: 1, LI: 1, SUB: 1, SUP: 1, SPAN: 1 };
  var BLOCKISH = { DIV: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, BLOCKQUOTE: 1, SECTION: 1, ARTICLE: 1, TR: 1, PRE: 1, HEADER: 1, FOOTER: 1, FIGURE: 1, DT: 1, DD: 1 };
  function cleanNodes(node) {
    var out = '';
    node.childNodes.forEach(function (n) {
      if (n.nodeType === 3) { out += esc(n.nodeValue); return; }
      if (n.nodeType !== 1) return;
      var t = n.tagName, inner;
      if (/^(SCRIPT|STYLE|META|LINK|TITLE|HEAD|TEMPLATE|NOSCRIPT|IMG|SVG|BUTTON|INPUT|SELECT|TEXTAREA|IFRAME|OBJECT)$/.test(t)) return;
      inner = cleanNodes(n);
      var sty = (n.getAttribute('style') || '').toLowerCase();
      if (OK_TAGS[t]) {
        var attrs = '';
        if (t === 'A') {
          var h = n.getAttribute('href') || '';
          if (/^(https?:|mailto:|ftp:|file:|wiki:)/i.test(h)) attrs = ' href="' + esc(h) + '"'; else return void (out += inner);
        }
        if (t === 'SPAN') {
          var pc = n.getAttribute('data-pill');
          if (pc && ST.colours[pc]) attrs = ' data-pill="' + pc + '"';
          else if (n.hasAttribute('data-ph')) attrs = ' data-ph="1"';
          else {
            if (/font-weight:\s*(bold|[6-9]00)/.test(sty)) inner = '<b>' + inner + '</b>';
            if (/font-style:\s*italic/.test(sty)) inner = '<i>' + inner + '</i>';
            out += inner; return;
          }
        }
        if ((t === 'P' || t === 'LI') && n.hasAttribute('data-ph')) attrs = ' data-ph="1"';
        if (t === 'BR') { out += '<br>'; return; }
        var tag = t.toLowerCase();
        out += '<' + tag + attrs + '>' + inner + '</' + tag + '>';
      } else if (BLOCKISH[t]) {
        out += '<p>' + inner + '</p>';
      } else if (t === 'TD' || t === 'TH') {
        out += inner + ' ';
      } else {
        out += inner;
      }
    });
    return out;
  }
  function sanitize(html) {
    if (!html) return '';
    var d = new DOMParser().parseFromString('<body>' + html + '</body>', 'text/html');
    return cleanNodes(d.body).replace(/<p>\s*<\/p>/g, '');
  }
  function sanitizeDoc(doc) {
    (doc.blocks || []).forEach(function (b) {
      if (!b.id) b.id = uid();
      ['html', 'sub'].forEach(function (k) { if (typeof b[k] === 'string') b[k] = sanitize(b[k]); });
      (b.items || []).concat(b.stages || [], b.emails || []).forEach(function (it) { if (typeof it.html === 'string') it.html = sanitize(it.html); });
      (b.rows || []).forEach(function (r, i) { r.forEach(function (c, j) { r[j] = sanitize(String(c || '')); }); });
      (b.leaves || []).forEach(function (lf) { if (lf && typeof lf.html === 'string') lf.html = sanitize(lf.html); });
    });
    return doc;
  }
  function textToParas(t) {
    return String(t || '').replace(/\r/g, '').split(/\n\s*\n/).map(function (p) {
      return p.trim() ? '<p>' + esc(p.trim()).replace(/\n/g, '<br>') + '</p>' : '';
    }).join('');
  }

  // ------------------------------------------------------------------ field builders
  function pl(path, val, hint, b, cls) {
    var isph = b && b.ph && b.ph[path];
    return '<span class="pl' + (isph ? ' isph' : '') + (cls ? ' ' + cls : '') + '" contenteditable="' + (READONLY ? 'false' : 'true') +
      '" data-f="' + path + '" data-hint="' + esc(hint) + '" spellcheck="true">' + esc(val || '') + '</span>';
  }
  function rt(path, html, hint, cls) {
    var empty = !String(html || '').replace(/<[^>]*>/g, '').trim() && !/<li/.test(html || '');
    return '<div class="rt' + (cls ? ' ' + cls : '') + (empty ? ' empty' : '') + '" contenteditable="' + (READONLY ? 'false' : 'true') +
      '" data-f="' + path + '" data-hint="' + esc(hint || 'Type here') + '">' + (html || '') + '</div>';
  }

  // ------------------------------------------------------------------ block renderers
  var R = {};
  R.hero = function (b) {
    var pills = (b.pills || []).map(function (p, i) {
      return '<span class="hp" style="' + ST.S.hero_pill + '">' + pl('pills.' + i, p, 'Label', b) +
        (READONLY ? '' : '<button class="x" data-act="delPill" data-i="' + i + '" title="Remove this label" contenteditable="false">&times;</button>') + '</span>';
    }).join('');
    return '<div class="hero" style="' + ST.S.hero + '"><div style="' + ST.S.hero_kicker + '">' + pl('kicker', b.kicker, 'Kicker, e.g. Your Team · Topic', b) +
      '</div><div style="' + ST.S.hero_title + '">' + pl('title', b.title, DOC.title || 'Uses the page title', b, 'herotitle') +
      '</div><div style="' + ST.S.hero_sub + '">' + rt('sub', b.sub, 'One line under the title', 'inline') +
      '</div><div class="pills" style="' + ST.S.hero_pills + '">' + pills + '</div></div>';
  };
  R.card = function (b) { return '<div style="' + ST.S.card + '">' + rt('html', b.html, 'Opening summary: what this page is and who it is for.') + '</div>'; };
  R.h2 = function (b) { return '<h2 style="' + st('h2', b.color || 'blue') + '">' + pl('text', b.text, 'Section heading', b) + '</h2>'; };
  R.h3 = function (b) { return '<h3 style="' + st('h3', b.color || 'blue') + '">' + pl('text', b.text, 'Sub-heading', b) + '</h3>'; };
  R.text = function (b) { return rt('html', b.html, 'Type here, or press / to insert a block'); };
  R.step = function (b, ctx) {
    var c = b.color || 'blue';
    return '<div style="' + ST.S.step + '"><div style="' + ST.S.step_numwrap + '"><div style="' + st('step_num', c) + '">' + (ctx.num || 1) +
      '</div></div><div style="' + st('step_body', c) + '">' + rt('html', b.html, 'Describe this step. Start with a verb.') + '</div></div>';
  };
  R.callout = function (b) {
    var k = ST.callouts[b.kind] ? b.kind : 'note', v = ST.callouts[k];
    return '<div style="' + st('callout', v[2], { bg: v[0], bd: v[1], tx: v[3] ? 'color:' + v[3] + ';' : '' }) + '">' +
      pl('title', b.title, 'Optional bold lead, e.g. Before you start.', b, 'callout-title') +
      rt('html', b.html, ST.calloutLabels[k] + ': type the message') + '</div>';
  };
  R.table = function (b) {
    var rows = b.rows || [[]], c = b.color || 'navy', h = '<div class="tblwrap"><table style="' + ST.S.table + '">';
    rows.forEach(function (r, ri) {
      var head = b.header !== false && ri === 0;
      h += '<tr style="' + (head ? '' : ST.S.tr) + '">';
      r.forEach(function (cell, ci) {
        var style = head ? st('th', c) : (b.keyval && ci === 0 ? ST.S.tk : ST.S.td);
        var tag = head || (b.keyval && ci === 0) ? 'th' : 'td';
        h += '<' + tag + ' style="' + style + '">' + rt('rows.' + ri + '.' + ci, cell, head ? 'Heading' : '', 'cell') + '</' + tag + '>';
      });
      h += '</tr>';
    });
    return h + '</table></div>';
  };
  R.cards = function (b) {
    var h = '<div class="cards-ed" style="' + ST.S.cards + '">';
    (b.items || []).forEach(function (it, i) {
      var c = it.color || b.color || 'blue';
      h += '<div class="cardx" style="' + st('cardx', c) + '"><div style="' + st('cardx_title', c) + '">' + pl('items.' + i + '.title', it.title, 'Card title', b) +
        '</div>' + rt('items.' + i + '.html', it.html, 'Links or a few lines') + '</div>';
    });
    return h + '</div>';
  };
  R.flow = function (b) {
    var parts = [];
    (b.stages || []).forEach(function (sg, i) {
      var c = sg.color || b.color || 'blue';
      parts.push('<div class="flowst" style="' + st('flow_stage', c) + '--sc:' + ST.colours[c] + ';"><div style="' + st('flow_title', c) + '">' +
        pl('stages.' + i + '.title', sg.title, 'Stage', b) + '</div>' + rt('stages.' + i + '.html', sg.html, 'One item per line') + '</div>');
    });
    return '<div class="flow-ed" style="' + ST.S.flow + '">' + parts.join('<div style="' + ST.S.flow_arrow + '">&rarr;</div>') + '</div>';
  };
  R.code = function (b) {
    var lang = b.lang === 'text' ? 'text' : 'sql', body;
    if (CODEEDIT === b.id || !String(b.code || '').trim() || !CODEHTML[b.id]) {
      if (CODEEDIT !== b.id && String(b.code || '').trim()) fetchCode(b);
      body = '<textarea class="codeedit" data-f="code" spellcheck="false" placeholder="' + (lang === 'sql' ? 'Paste or type SQL here' : 'Paste or type text here') + '"' + (READONLY ? ' readonly' : '') + '>' + esc(b.code || '') + '</textarea>';
    } else {
      body = '<div class="codeview" data-act="editCode" title="Click to edit">' + CODEHTML[b.id] + '</div>';
    }
    return '<div style="' + ST.S.code_wrap + '"><div style="' + ST.S.code_tabbar + '"><span style="' + ST.S.code_tab + '">' +
      pl('title', b.title, lang === 'sql' ? 'SQLQuery1.sql' : 'Text', b, 'code-tab-edit') + '</span></div>' + body + '</div>';
  };
  R.collapse = function (b) {
    var c = b.color || 'navy';
    return '<div style="' + ST.S.collapse + '"><div class="collapse-h" style="' + st('collapse_head', c) + '"><span class="fold-badge" contenteditable="false">' +
      (b.collapsed === false ? 'Open on the wiki' : 'Folded on the wiki') + '</span>' + pl('title', b.title, 'Question or heading', b) +
      '</div><div style="' + ST.S.collapse_body + '">' + rt('html', b.html, 'The answer or the detail') + '</div></div>';
  };
  R.image = function (b) {
    var prev = IMGS[b.id] ? '<div class="figprev" style="' + ST.S.figure + '"><img alt="" src="' + IMGS[b.id] + '"></div>' :
      '<div class="imgdrop" data-act="pickImg" contenteditable="false"><b>Drop a picture here, paste a screenshot, or click to choose one.</b><br>' +
      '<span class="small">The tool makes the copies you upload: one 700px wide for the page and a full-size one it links to.</span></div>';
    return prev + '<div class="imgfields"><div class="f"><span class="lab">File name on the wiki</span>' + pl('file', b.file, 'Example_700.png', b) +
      '</div><div class="f"><span class="lab">Full-size file it opens (optional)</span>' + pl('full', b.full, 'Example_full.png', b) +
      '</div><div class="f wide"><span class="lab">Caption</span>' + pl('caption', b.caption, 'What the picture shows', b) + '</div></div>';
  };
  R.divider = function () { return '<hr style="' + ST.S.hr + '">'; };
  // a layout from the wiki the tool has no block for: drawn exactly as on the wiki, with every piece of text editable
  R.layout = function (b) {
    var leaves = b.leaves || [];
    var view = String(b.view || '').replace(/<wst-leaf data-i="(\d+)"><\/wst-leaf>/g, function (m, i) {
      var lf = leaves[+i]; if (!lf) return '';
      var block = lf.mode === 'block', tag = block ? 'div' : 'span';
      return '<' + tag + ' class="rt leaf' + (block ? '' : ' inline') + '" contenteditable="' + (READONLY ? 'false' : 'true') +
        '" data-f="leaves.' + i + '.html" data-hint="Text">' + (lf.html || '') + '</' + tag + '>';
    });
    return '<div class="layout"><div class="laylab" contenteditable="false">Layout kept as on the wiki &middot; click any text to change it</div>' + view + '</div>';
  };
  R.raw = function (b) {
    return '<div class="rawbox"><div class="lab">Wiki code, kept exactly as written</div><textarea data-f="wiki" spellcheck="false"' + (READONLY ? ' readonly' : '') + '>' + esc(b.wiki || '') + '</textarea></div>';
  };
  function initials(name) {
    var w = String(name || '').split(/[^A-Za-z0-9]+/).filter(function (x) { return x && ['of', 'and', 'the', 'to', 'for'].indexOf(x.toLowerCase()) < 0; });
    return (w.slice(0, 2).map(function (x) { return x[0]; }).join('').toUpperCase()) || '?';
  }
  function threadSubject(b) {
    var ems = b.emails || [];
    for (var i = 0; i < ems.length; i++) {
      if (b.ph && b.ph['emails.' + i + '.subject']) continue;
      var s = String(ems[i].subject || '').replace(/^\s*((re|fw|fwd)\s*:\s*)+/i, '').trim();
      if (s) return s;
    }
    return '';
  }
  R.email = function (b) {
    var ems = b.emails || [], colours = {}, n = 0;
    var h = '<div style="' + ST.S.ol_wrap + '"><div style="' + ST.S.ol_bar + '"><span>Mail</span><span style="' + ST.S.ol_bar_r + '">Conversation view</span></div>' +
      '<div style="' + ST.S.ol_head + '"><div style="' + ST.S.ol_subj + '">' + pl('caption', b.caption, threadSubject(b) || 'Thread subject', b) +
      '</div><div style="' + ST.S.ol_meta + '">' + ems.length + ' message' + (ems.length === 1 ? '' : 's') + ' &middot; newest first</div></div>';
    ems.forEach(function (em, i) {
      var key = b.ph && b.ph['emails.' + i + '.from'] ? '' : String(em.from || '').trim();
      if (!(key in colours)) { colours[key] = ST.badgeColours[n % ST.badgeColours.length]; n++; }
      var f = function (k, hint) { return pl('emails.' + i + '.' + k, em[k], hint, b); };
      h += '<div style="' + ST.S.ol_msg + '"><div style="' + ST.S.ol_row + '"><div style="' + st('ol_badge', colours[key]) + '">' + esc(key ? initials(key) : '?') +
        '</div><div style="' + ST.S.ol_main + '"><div style="' + ST.S.ol_top + '"><div style="' + ST.S.ol_from + '">' + f('from', 'Sender role title') +
        '</div><div style="' + ST.S.ol_sent + '">Sent: ' + f('sent', 'Date and time') + '</div></div>' +
        '<div style="' + ST.S.ol_to + '"><span style="' + ST.S.ol_lab + '">To:</span> ' + f('to', 'Role titles, separated by ;') + '</div>' +
        '<div style="' + ST.S.ol_cc + '"><span style="' + ST.S.ol_lab + '">Cc:</span> ' + f('cc', 'Optional') + '</div>' +
        '<div style="' + ST.S.ol_subline + '"><span style="' + ST.S.ol_lab + '">Subject:</span> ' + f('subject', 'Subject') + '</div>' +
        '<div style="' + ST.S.ol_body + '">' + rt('emails.' + i + '.html', em.html, 'The email text, as written') + '</div></div></div></div>';
    });
    return h + '</div>';
  };

  function stepNumbers(blocks) {
    var n = 0, out = {};
    blocks.forEach(function (b) {
      if (b.type === 'h2') n = 0;
      if (b.type === 'step') { var s = parseInt(b.start, 10); n = s > 0 ? s : n + 1; out[b.id] = n; }
    });
    return out;
  }
  function blockHTML(b, nums) {
    var r = R[b.type] || R.raw;
    var inner;
    try { inner = r(b, { num: nums[b.id] }); } catch (e) { inner = '<div class="rawbox">This block could not be drawn: ' + esc(e.message) + '</div>'; }
    return '<div class="blk blk-' + b.type + (SEL === b.id ? ' sel' : '') + '" data-id="' + b.id + '">' +
      (READONLY ? '' : '<div class="gut" contenteditable="false"><button class="handle" draggable="true" data-act="drag" title="Drag to move">&#8942;&#8942;</button>' +
        '<button data-act="addBelow" title="Add a block below">+</button></div>') +
      '<div class="bview">' + inner + '</div></div>';
  }
  function docHTML(doc) {
    var save = DOC; DOC = doc; READONLY = true;
    var nums = stepNumbers(doc.blocks), h = doc.blocks.map(function (b) { return blockHTML(b, nums); }).join('');
    READONLY = false; DOC = save;
    return h;
  }

  // ------------------------------------------------------------------ rendering
  function renderAll(focus) {
    var f = focus || captureFocus();
    var nums = stepNumbers(DOC.blocks);
    var html = DOC.blocks.map(function (b) { return blockHTML(b, nums); }).join('');
    if (!DOC.blocks.length) html = startPanel();
    $('blocks').innerHTML = html;
    var t = document.querySelector('.ptitle');
    if (t.textContent !== (DOC.title || '')) t.textContent = DOC.title || '';
    afterRender();
    restoreFocus(f);
  }
  function renderBlock(id, focus) {
    var el = document.querySelector('.blk[data-id="' + id + '"]'), b = blockById(id);
    if (!el || !b) return renderAll(focus);
    var f = focus || captureFocus();
    var tmp = document.createElement('div');
    tmp.innerHTML = blockHTML(b, stepNumbers(DOC.blocks));
    el.parentNode.replaceChild(tmp.firstChild, el);
    afterRender();
    restoreFocus(f);
  }
  function afterRender() {
    document.querySelectorAll('#blocks textarea').forEach(autosize);
    placeTools();
    renderOutline();
    renderPageBits();
    $('addEnd').hidden = !DOC.blocks.length;
  }
  function autosize(t) { t.style.height = 'auto'; t.style.height = (t.scrollHeight + 2) + 'px'; }
  function startPanel() {
    var pick = ['howto', 'troubleshoot-kb', 'known-error', 'hub', 'runbook', 'faq'];
    var cards = pick.map(function (id) { var t = TPLS.filter(function (x) { return x.id === id; })[0]; return t ? tcardHTML(t) : ''; }).join('');
    return '<div class="start" contenteditable="false"><h3>Start your article</h3><div class="muted">Give it a title above, then start from a template or just start writing.</div>' +
      '<div class="grid">' + cards + '</div><div class="row"><button data-act="allTemplates">See all ' + TPLS.length + ' templates</button>' +
      '<button data-act="blankText">Start writing on a blank page</button><button data-act="importMenu">Bring in an existing page</button></div></div>';
  }
  function captureFocus() {
    var a = document.activeElement;
    if (!a || !a.closest) return null;
    var f = a.closest('[data-f]'), blk = a.closest('.blk');
    if (!f || !blk) return null;
    var off = null, sel = window.getSelection();
    if (f.tagName === 'TEXTAREA') off = f.selectionStart;
    else if (sel.rangeCount && f.contains(sel.anchorNode)) { var r = document.createRange(); r.selectNodeContents(f); r.setEnd(sel.anchorNode, sel.anchorOffset); off = r.toString().length; }
    return { id: blk.dataset.id, f: f.dataset.f, off: off };
  }
  function restoreFocus(f) {
    if (!f) return;
    var blk = document.querySelector('.blk[data-id="' + f.id + '"]');
    if (!blk) return;
    var el = f.f ? blk.querySelector('[data-f="' + f.f + '"]') : null;
    if (!el) el = blk.querySelector('[data-f]');
    if (!el) return;
    focusAt(el, f.off == null ? 'end' : f.off);
  }
  function focusAt(el, off) {
    if (el.tagName === 'TEXTAREA') { el.focus(); var p = off === 'end' ? el.value.length : (off === 'start' ? 0 : off); el.setSelectionRange(p, p); return; }
    el.focus();
    var sel = window.getSelection(), r = document.createRange();
    if (off === 'end' || off === 'start') { r.selectNodeContents(el); r.collapse(off === 'start'); }
    else {
      var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), n, left = off, done = false;
      while ((n = w.nextNode())) { if (left <= n.nodeValue.length) { r.setStart(n, left); r.collapse(true); done = true; break; } left -= n.nodeValue.length; }
      if (!done) { r.selectNodeContents(el); r.collapse(false); }
    }
    sel.removeAllRanges(); sel.addRange(r);
  }
  var MAIN = { code: 'code', callout: 'html', step: 'html', card: 'html', text: 'html', collapse: 'title', h2: 'text', h3: 'text', hero: 'kicker',
    table: 'rows.0.0', cards: 'items.0.title', flow: 'stages.0.title', email: 'emails.0.from', raw: 'wiki', image: 'file' };
  function focusBlock(id, where) {
    var blk = document.querySelector('.blk[data-id="' + id + '"]'), b = blockById(id);
    if (!blk) return;
    var key = b && MAIN[b.type];
    var el = (key && blk.querySelector('[data-f="' + key + '"]')) || blk.querySelector('[data-f]');
    select(id);
    if (el) focusAt(el, where || 'end');
    blk.scrollIntoView({ block: 'nearest' });
  }

  // ------------------------------------------------------------------ outline, page panel, cats
  function renderOutline() {
    var h = '';
    DOC.blocks.forEach(function (b, i) {
      if (b.type === 'h2' || b.type === 'h3') h += '<a class="' + b.type + '" data-go="' + b.id + '"><span class="dot" style="background:' + (ST.colours[b.color] || ST.colours.blue) + '"></span>' + esc(b.text || '(heading with no text)') + '</a>';
    });
    $('outline').innerHTML = h || '<div class="muted">No headings yet. Add a section heading to build the contents box.</div>';
  }
  function renderPageBits() {
    $('pgSummary').value === (DOC.summary || '') || ($('pgSummary').value = DOC.summary || '');
    $('pgToc').checked = DOC.toc === true;
    $('tocHint').hidden = DOC.toc !== null;
    $('pgFile').value = slugify(DOC.title) + '.txt';
    var bad = /[<>\[\]{}|=]/.test(DOC.summary || '');
    var n = (DOC.summary || '').length;
    $('sumHint').innerHTML = (n ? n + ' characters. ' : '') + (bad ? '<b style="color:#b3261e">Take out &lt; &gt; [ ] { } | and = (they break the hidden line).</b>' : 'Plain words only. One or two sentences.');
    $('catChips').innerHTML = (DOC.categories || []).map(function (c, i) {
      var other = ST.categories.indexOf(c) < 0;
      return '<span class="chip' + (other ? ' other' : '') + '" title="' + (other ? 'Not one of the main categories' : '') + '">' + esc(c) + '<button data-delcat="' + i + '" aria-label="Remove ' + esc(c) + '">&times;</button></span>';
    }).join('');
    var tpl = TPLS.filter(function (t) { return t.id === DOC.template; })[0];
    $('tplInfo').textContent = tpl ? 'Started from the ' + tpl.name + ' template.' : '';
    var cats = DOC.categories || [];
    $('cats').innerHTML = 'Categories: ' + (cats.length ? cats.map(function (c) { return '<a data-act="pageTab">' + esc(c) + '</a>'; }).join(' | ') : '<span class="none">none yet (add one in the Page panel)</span>');
    var src = DOC._wiki, srcHtml = '';
    if (src && src.title) {
      srcHtml = '<span class="wsrc" title="Publish saves to this page">' + (src.exists ? 'From the wiki: <a href="' + esc(src.url || '#') + '" target="_blank" rel="noopener">' +
        esc(src.title) + '</a> &middot; revision ' + esc(src.revid) : 'New page on the wiki: <b>' + esc(src.title) + '</b> (created when you publish)') +
        (src.protected ? ' &middot; <b>protected</b>' : '') + '</span>';
    }
    $('crumb').innerHTML = srcHtml + (DOC.summary ? '<span title="Hidden first line. Edit it in the Page panel.">Search summary: ' + esc(DOC.summary) + '</span>' :
      '<a data-act="pageTab" style="color:#b86e00;cursor:pointer">Add a search summary</a>');
    document.querySelectorAll('.herotitle').forEach(function (h) { h.dataset.hint = DOC.title || 'Uses the page title'; });
  }

  // ------------------------------------------------------------------ history and saving
  function commit() {
    var s = JSON.stringify(DOC);
    if (s !== LAST) { HIST.push(LAST); if (HIST.length > 120) HIST.shift(); LAST = s; FUT = []; }
    changed();
  }
  function changed() {
    debounce('ls', 500, function () { lsSet('wst3.doc', JSON.stringify(DOC)); status('Kept on this computer'); });
    debounce('check', 1600, refreshCheck);
  }
  function undo() {
    commit();
    if (!HIST.length || !HIST[HIST.length - 1]) return toast('Nothing to undo.');
    FUT.push(LAST); LAST = HIST.pop(); DOC = JSON.parse(LAST); renderAll(); changed();
  }
  function redo() {
    if (!FUT.length) return toast('Nothing to redo.');
    HIST.push(LAST); LAST = FUT.pop(); DOC = JSON.parse(LAST); renderAll(); changed();
  }
  function hasContent() { return !!(DOC.title || DOC.blocks.length); }
  function loadDoc(doc, msg) {
    doc = sanitizeDoc(doc);
    doc.blocks = doc.blocks || []; doc.categories = doc.categories || [];
    if (doc.toc === undefined) doc.toc = true;
    commit();
    DOC = doc; SEL = null; IMGS = {}; CODEHTML = {}; CODEEDIT = null;
    renderAll(); commit();
    $('paperwrap').scrollTop = 0;
    if (msg) toast(msg);
    if (!DOC.title) setTimeout(function () { focusAt(document.querySelector('.ptitle'), 'end'); }, 30);
  }
  function saveDraft(quiet) {
    commit();
    return api('/api/draft', { doc: DOC, name: DOC._draft || '' }).then(function (r) {
      DOC._draft = r.name; LAST = JSON.stringify(DOC); lsSet('wst3.doc', LAST);
      var d = new Date(); status('Draft saved ' + d.toTimeString().slice(0, 5));
      if (!quiet) toast('Draft saved: output\\drafts\\' + r.name);
      return r;
    }).catch(function (e) { toast('Could not save the draft: ' + e.message, true); throw e; });
  }
  function confirmReplace(title, msg, go) {
    if (!hasContent()) return go();
    modal(title, '<p>' + msg + '</p><p class="muted">Your current page is saved as a draft first, so you can open it again from <b>Open</b>.</p>',
      [['Cancel', null], ['Continue', function () { saveDraft(true).then(go, go); return true; }, true]], true);
  }

  // ------------------------------------------------------------------ model updates from the page
  function fieldValue(el) {
    if (el.tagName === 'TEXTAREA') return el.value;
    if (el.classList.contains('rt')) {
      var h = el.innerHTML;
      if (!el.textContent.trim() && !/<li/i.test(h)) return '';
      return h.replace(/<p><br><\/p>$/i, '');
    }
    return el.textContent.replace(/ /g, ' ').replace(/\s+/g, ' ').replace(/^ /, '');
  }
  function onInput(e) {
    var el = e.target.closest && e.target.closest('[data-f]');
    if (!el) return;
    var path = el.dataset.f;
    if (path === '@title') {
      DOC.title = fieldValue(el).trim();
      renderPageBits();
      debounce('typing', 700, commit);
      return;
    }
    var blk = el.closest('.blk'); if (!blk) return;
    var b = blockById(blk.dataset.id); if (!b) return;
    if (b.ph && b.ph[path]) { delete b.ph[path]; el.classList.remove('isph'); }
    if (el.classList.contains('rt')) {
      var anc = phAncestor(el);
      if (anc) anc.removeAttribute('data-ph');
      el.classList.toggle('empty', !el.textContent.trim() && !el.querySelector('li'));
      checkSlash(el, blk);
    }
    if (el.tagName === 'TEXTAREA') autosize(el);
    setPath(b, path, fieldValue(el));
    if (b.type === 'h2' || b.type === 'h3') debounce('outline', 300, renderOutline);
    debounce('typing', 700, commit);
  }
  function phAncestor(root) {
    var sel = window.getSelection();
    if (!sel.rangeCount) return null;
    var n = sel.anchorNode;
    while (n && n !== root) { if (n.nodeType === 1 && n.hasAttribute('data-ph')) return n; n = n.parentNode; }
    return null;
  }
  function selectRange(node) {
    var r = document.createRange(); r.selectNodeContents(node);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }
  function selectPh(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.classList.contains('pl') && t.classList.contains('isph')) { setTimeout(function () { selectRange(t); }, 0); return; }
    var rtEl = t.closest('.rt');
    if (!rtEl || !rtEl.querySelector('[data-ph]')) return;
    var y = e.clientY;
    setTimeout(function () {
      if (document.activeElement !== rtEl) return;
      var s = window.getSelection();
      if (s.rangeCount && !s.isCollapsed) return;
      var ph = t.closest('[data-ph]') || phAncestor(rtEl);
      if (!ph) {
        var c = rtEl.cloneNode(true);
        c.querySelectorAll('[data-ph]').forEach(function (n) { n.remove(); });
        if (c.textContent.trim()) return;
        var phs = rtEl.querySelectorAll('[data-ph]');
        ph = phs[0];
        if (y != null) for (var i = 0; i < phs.length; i++) { var r = phs[i].getBoundingClientRect(); if (y >= r.top - 4 && y <= r.bottom + 4) { ph = phs[i]; break; } }
      }
      if (ph && rtEl.contains(ph)) selectRange(ph);
    }, 0);
  }

  // ------------------------------------------------------------------ block operations
  function makeBlock(kind) {
    var c = 'blue', m = {
      text: { type: 'text', html: '' }, h2: { type: 'h2', text: '', color: 'blue' }, h3: { type: 'h3', text: '', color: 'blue' },
      card: { type: 'card', html: '' }, step: { type: 'step', html: '', color: 'green' },
      note: { type: 'callout', kind: 'note', title: '', html: '' }, warning: { type: 'callout', kind: 'warning', title: '', html: '' },
      danger: { type: 'callout', kind: 'danger', title: '', html: '' }, tip: { type: 'callout', kind: 'tip', title: '', html: '' },
      old: { type: 'callout', kind: 'old', title: '', html: '' },
      table: { type: 'table', rows: [['', '', ''], ['', '', ''], ['', '', '']], header: true, keyval: false, color: 'navy' },
      facts: { type: 'table', rows: [['Owner', ''], ['Last reviewed', ''], ['', '']], header: false, keyval: true, color: 'navy' },
      cards: { type: 'cards', color: 'blue', items: [{ title: '', html: '' }, { title: '', html: '' }, { title: '', html: '' }] },
      flow: { type: 'flow', color: 'blue', stages: [{ title: '', html: '' }, { title: '', html: '' }, { title: '', html: '' }] },
      collapse: { type: 'collapse', title: '', html: '', collapsed: true, color: 'navy' },
      code: { type: 'code', lang: 'sql', title: '', code: '' }, codetext: { type: 'code', lang: 'text', title: '', code: '' },
      image: { type: 'image', file: '', full: '', caption: '' },
      email: { type: 'email', caption: '', emails: [{ from: '', sent: '', to: '', cc: '', subject: '', html: '' }] },
      hero: { type: 'hero', kicker: 'Your Team', title: '', sub: '', pills: [] },
      divider: { type: 'divider' }, raw: { type: 'raw', wiki: '' }
    }[kind];
    m = clone(m || { type: 'text', html: '' });
    m.id = uid();
    return m;
  }
  function insertAt(i, blocks) {
    commit();
    DOC.blocks.splice.apply(DOC.blocks, [i, 0].concat(blocks));
    SEL = blocks[0].id;
    renderAll(false);
    commit();
    focusBlock(blocks[0].id, 'start');
  }
  function insertKind(kind, afterId, replaceId) {
    var blocks = kind === 'steps3' ? [makeBlock('step'), makeBlock('step'), makeBlock('step')] : [makeBlock(kind)];
    if (kind === 'step' || kind === 'steps3') {
      var ref = blockById(replaceId || afterId);
      if (ref && ref.color && (ref.type === 'step' || ref.type === 'h2' || ref.type === 'h3')) blocks.forEach(function (b) { b.color = ref.color; });
    }
    if (replaceId) {
      var ri = indexOf(replaceId);
      commit();
      DOC.blocks.splice(ri, 1);
      insertAt(ri, blocks);
    } else {
      var i = afterId ? indexOf(afterId) + 1 : DOC.blocks.length;
      insertAt(i, blocks);
    }
    if (kind === 'image') setTimeout(function () { pickImage(blocks[0].id); }, 50);
  }
  function moveBlock(id, d) {
    var i = indexOf(id), j = i + d;
    if (i < 0 || j < 0 || j >= DOC.blocks.length) return;
    commit();
    var b = DOC.blocks.splice(i, 1)[0]; DOC.blocks.splice(j, 0, b);
    renderAll(); commit();
    var el = document.querySelector('.blk[data-id="' + id + '"]'); if (el) el.scrollIntoView({ block: 'nearest' });
  }
  function dupBlock(id) {
    var i = indexOf(id); if (i < 0) return;
    var b = clone(DOC.blocks[i]); b.id = uid();
    insertAt(i + 1, [b]);
  }
  function delBlock(id) {
    var i = indexOf(id); if (i < 0) return;
    commit();
    DOC.blocks.splice(i, 1);
    SEL = null;
    renderAll(false); commit();
    var prev = DOC.blocks[Math.max(0, i - 1)];
    if (prev) focusBlock(prev.id, 'end');
    toast('Block deleted. Press Ctrl+Z to bring it back.');
  }
  function select(id) {
    if (SEL === id) { placeTools(); return; }
    SEL = id;
    document.querySelectorAll('.blk.sel').forEach(function (x) { x.classList.remove('sel'); });
    var el = id && document.querySelector('.blk[data-id="' + id + '"]');
    if (el) el.classList.add('sel');
    placeTools();
  }

  // ------------------------------------------------------------------ block toolbar
  var COLOURS_ORDER = ['navy', 'blue', 'green', 'purple', 'amber', 'red', 'grey'];
  function swatches(b) {
    return COLOURS_ORDER.map(function (c) {
      return '<button class="sw' + ((b.color || '') === c ? ' on' : '') + '" data-act="color" data-c="' + c + '" style="background:' + ST.colours[c] + '" title="' + c + '"></button>';
    }).join('');
  }
  function toolsHTML(b) {
    var name = ST.blockNames[b.type] || b.type, h = '<span class="lab">' + esc(b.type === 'callout' ? (ST.calloutLabels[b.kind] || 'Callout') : name) + '</span>';
    var t = b.type;
    if (t === 'callout') {
      h += '<select data-act="kind" aria-label="Callout kind">' + Object.keys(ST.callouts).map(function (k) { return '<option value="' + k + '"' + (b.kind === k ? ' selected' : '') + '>' + ST.calloutLabels[k] + '</option>'; }).join('') + '</select>';
    }
    if (/^(h2|h3|step|cards|flow|table|collapse)$/.test(t)) h += '<span class="sep"></span>' + swatches(b);
    if (t === 'step') h += '<span class="sep"></span><label class="mini">Number <input type="number" min="1" data-act="start" value="' + esc(b.start || '') + '" placeholder="auto" title="Leave blank to number automatically"></label>';
    if (t === 'table') {
      h += '<span class="sep"></span><button data-act="addRow">+ Row</button><button data-act="addCol">+ Column</button><button data-act="delRow">&minus; Row</button><button data-act="delCol">&minus; Column</button>' +
        '<label class="mini"><input type="checkbox" data-act="header"' + (b.header !== false ? ' checked' : '') + '> Header row</label>' +
        '<label class="mini"><input type="checkbox" data-act="keyval"' + (b.keyval ? ' checked' : '') + '> Labels down the left</label>';
    }
    if (t === 'cards') h += '<span class="sep"></span><button data-act="addItem">+ Card</button><button data-act="delItem">&minus; Card</button>';
    if (t === 'flow') h += '<span class="sep"></span><button data-act="addStage">+ Stage</button><button data-act="delStage">&minus; Stage</button>';
    if (t === 'collapse') h += '<label class="mini"><input type="checkbox" data-act="collapsed"' + (b.collapsed !== false ? ' checked' : '') + '> Folded on the wiki</label>';
    if (t === 'code') h += '<select data-act="lang"><option value="sql"' + (b.lang !== 'text' ? ' selected' : '') + '>SQL (coloured)</option><option value="text"' + (b.lang === 'text' ? ' selected' : '') + '>Plain text</option></select>';
    if (t === 'image') h += '<button data-act="pickImg">Choose picture</button><button data-act="makeCopies"' + (IMGS[b.id] ? '' : ' disabled') + '>Download wiki copies</button>';
    if (t === 'email') h += '<button data-act="importMail">Import .eml or .msg</button><button data-act="addEmail">+ Email</button><button data-act="delEmail">&minus; Email</button>';
    if (t === 'hero') h += '<button data-act="addPill">+ Label</button>';
    if (t === 'layout') h += '<button data-act="toWiki" title="Show this layout as wiki code, to change the layout itself">Edit wiki code</button>';
    if (t === 'raw') h += '<button data-act="toLayout" title="Show this wiki code as it looks on the wiki, with its text editable">Show as layout</button>';
    if (t === 'text' || t === 'callout' || t === 'card') {
      h += '<select data-act="turn" aria-label="Turn into"><option value="">Turn into&hellip;</option><option value="text">Text</option><option value="card">Intro card</option>' +
        '<option value="note">Note</option><option value="warning">Warning</option><option value="danger">Stop</option><option value="tip">Tip</option><option value="old">Superseded</option>' +
        '<option value="steps">Numbered steps (one per paragraph)</option><option value="collapse">Expandable section</option></select>';
    }
    h += '<span class="sep"></span><button data-act="up" title="Move up (Alt+Up)">&uarr;</button><button data-act="down" title="Move down (Alt+Down)">&darr;</button>' +
      '<button data-act="dup" title="Copy this block">Copy</button><button data-act="del" class="del" title="Delete this block">Delete</button>';
    return h;
  }
  function placeTools() {
    var bt = $('btools'), el = SEL && document.querySelector('.blk[data-id="' + SEL + '"]'), b = SEL && blockById(SEL);
    if (!el || !b || READONLY) { bt.hidden = true; return; }
    bt.innerHTML = toolsHTML(b);
    bt.hidden = false;
    var wrap = $('paperwrap'), r = el.getBoundingClientRect(), w = wrap.getBoundingClientRect();
    bt.style.position = 'fixed';
    var top = r.top - bt.offsetHeight - 8;
    if (top < w.top + 2) top = Math.min(r.bottom + 8, w.bottom - bt.offsetHeight - 4);
    bt.style.top = Math.max(w.top + 2, top) + 'px';
    bt.style.left = Math.max(w.left + 8, Math.min(r.right - bt.offsetWidth, w.right - bt.offsetWidth - 16)) + 'px';
  }
  function toolAct(act, el) {
    var b = blockById(SEL); if (!b) return;
    var id = b.id;
    if (act === 'up') return moveBlock(id, -1);
    if (act === 'down') return moveBlock(id, 1);
    if (act === 'dup') return dupBlock(id);
    if (act === 'del') return delBlock(id);
    if (act === 'pickImg') return pickImage(id);
    if (act === 'makeCopies') return makeCopies(id);
    if (act === 'importMail') return importMail(id);
    if (act === 'toWiki') return layoutToWiki(b);
    if (act === 'toLayout') return wikiToLayout(b);
    commit();
    if (act === 'color') {
      b.color = el.dataset.c;
      (b.items || []).concat(b.stages || []).forEach(function (x) { delete x.color; });
    } else if (act === 'addRow') {
      var w = Math.max(1, (b.rows[0] || []).length); b.rows.push(new Array(w).fill(''));
    } else if (act === 'addCol') { b.rows.forEach(function (r) { r.push(''); });
    } else if (act === 'delRow') { if (b.rows.length > 1) b.rows.pop();
    } else if (act === 'delCol') { if ((b.rows[0] || []).length > 1) b.rows.forEach(function (r) { r.pop(); });
    } else if (act === 'addItem') { b.items.push({ title: '', html: '' });
    } else if (act === 'delItem') { if (b.items.length > 1) b.items.pop();
    } else if (act === 'addStage') { b.stages.push({ title: '', html: '' });
    } else if (act === 'delStage') { if (b.stages.length > 1) b.stages.pop();
    } else if (act === 'addEmail') { b.emails.push({ from: '', sent: '', to: '', cc: '', subject: '', html: '' });
    } else if (act === 'delEmail') { if (b.emails.length > 1) b.emails.pop();
    } else if (act === 'addPill') { b.pills = (b.pills || []).concat(['']);
    } else { return; }
    renderBlock(id); commit();
    if (act === 'addPill') { var ps = document.querySelectorAll('.blk[data-id="' + id + '"] [data-f^="pills."]'); if (ps.length) focusAt(ps[ps.length - 1], 'end'); }
  }
  function toolChange(act, el) {
    var b = blockById(SEL); if (!b) return;
    commit();
    if (act === 'kind') b.kind = el.value;
    else if (act === 'start') { var v = parseInt(el.value, 10); if (v > 0) b.start = v; else delete b.start; }
    else if (act === 'header') b.header = el.checked;
    else if (act === 'keyval') b.keyval = el.checked;
    else if (act === 'collapsed') b.collapsed = el.checked;
    else if (act === 'lang') { b.lang = el.value; delete CODEHTML[b.id]; }
    else if (act === 'turn') return turnInto(b, el.value);
    if (act === 'start') renderAll(); else renderBlock(b.id);
    commit();
  }
  function layoutToWiki(b) {
    api('/api/blockwiki', { block: b }).then(function (r) {
      commit();
      var i = indexOf(b.id); if (i < 0) return;
      DOC.blocks[i] = { id: b.id, type: 'raw', wiki: r.wiki || '' };
      renderBlock(b.id); commit();
      toast('Showing wiki code. Change the layout, then press Show as layout to go back.');
    }).catch(function (e) { toast(e.message, true); });
  }
  function wikiToLayout(b) {
    api('/api/layout', { wiki: b.wiki || '' }).then(function (r) {
      if (!r.block) return toast('This wiki code has no text the editor can change safely (for example templates or special tags), so it stays as wiki code.', true);
      commit();
      var i = indexOf(b.id); if (i < 0) return;
      r.block.id = b.id;
      DOC.blocks[i] = sanitizeDoc({ blocks: [r.block] }).blocks[0];
      renderBlock(b.id); commit();
    }).catch(function (e) { toast(e.message, true); });
  }
  function turnInto(b, to) {
    if (!to) return;
    var i = indexOf(b.id), html = b.html || '', nb;
    if (b.type === 'callout' && b.title) html = '<p><b>' + esc(b.title) + '</b></p>' + html;
    if (to === 'steps') {
      var d = document.createElement('div'); d.innerHTML = html;
      var parts = [];
      var loose = '';
      var flushLoose = function () { if (loose.replace(/<[^>]*>|&nbsp;/g, '').trim()) parts.push('<p>' + loose + '</p>'); loose = ''; };
      Array.prototype.forEach.call(d.childNodes, function (c) {
        if (c.nodeType === 3) { loose += esc(c.nodeValue); return; }
        if (c.nodeType !== 1) return;
        if (c.tagName === 'UL' || c.tagName === 'OL') { flushLoose(); Array.prototype.forEach.call(c.children, function (li) { parts.push('<p>' + li.innerHTML + '</p>'); }); }
        else if (/^(P|DIV)$/.test(c.tagName)) { flushLoose(); if (c.textContent.trim()) parts.push('<p>' + c.innerHTML + '</p>'); }
        else if (c.tagName === 'BR') flushLoose();
        else loose += c.outerHTML;
      });
      flushLoose();
      if (!parts.length) parts = [''];
      var steps = parts.map(function (p) { var s = makeBlock('step'); s.html = p; return s; });
      DOC.blocks.splice.apply(DOC.blocks, [i, 1].concat(steps));
      SEL = steps[0].id;
    } else {
      nb = to === 'text' ? makeBlock('text') : to === 'card' ? makeBlock('card') : to === 'collapse' ? makeBlock('collapse') : makeBlock(to);
      nb.html = html; nb.id = b.id;
      DOC.blocks[i] = nb;
    }
    renderAll(); commit();
  }

  // ------------------------------------------------------------------ the wiki: connect, open, publish
  var WIKI = { connected: false }, lastSummary = '';
  function showErr(id, msg) { var e = $(id); if (e) { e.textContent = msg; e.hidden = false; } else toast(msg, true); }
  function wikiLink(url, text) { return '<a href="' + esc(url || '#') + '" target="_blank" rel="noopener">' + esc(text) + '</a>'; }
  function wikiRefresh() {
    return api('/api/wiki/status').then(function (s) { WIKI = s; renderWiki(); return s; }).catch(function () { renderWiki(); });
  }
  function renderWiki() {
    var b = $('bWiki'); if (!b) return;
    b.classList.toggle('on', !!WIKI.connected);
    $('wikiLabel').textContent = WIKI.connected ? WIKI.user : 'Wiki';
    b.title = WIKI.connected ? 'Connected to the wiki as ' + WIKI.user + '. Click to see the connection or disconnect.' : 'Connect to the wiki to open and publish pages';
  }
  function busy(on) { var p = document.querySelector('#mFoot .primary'); if (p) { p.disabled = on; p.classList.toggle('busy', on); } }
  function wikiErr(e, errId, retry) {
    if (e.code === 'readapidenied' || e.code === 'notloggedin' || e.code === 'assertuserfailed' || e.code === 'assertbotfailed') {
      WIKI.connected = false; renderWiki(); closeModal();
      toast(e.message, true);
      return connectDialog(retry);
    }
    if (errId && $(errId)) showErr(errId, e.message); else toast(e.message, true);
  }
  function connectDialog(after) {
    var user = lsGet('wst.wikiUser') || '', apiUrl = lsGet('wst.wikiApi') || WIKI.defaultApi || '';
    modal('Connect to the wiki',
      '<p>Use your own <b>bot password</b>: a separate login for tools, made on the wiki. The tool uses it to log in and never saves it. ' +
      'Pages you publish are saved under your own name.</p>' +
      '<label for="wkUser">Bot username</label><input type="text" id="wkUser" autocomplete="off" spellcheck="false" placeholder="YourWikiName@BotName" value="' + esc(user) + '">' +
      '<label for="wkPass">Bot password</label><input type="password" id="wkPass" autocomplete="off" spellcheck="false">' +
      '<div class="hint">No bot password yet? ' + wikiLink(WIKI.botPasswordsUrl, 'Make one on Special:BotPasswords') +
      ' with <i>Edit existing pages</i> and <i>Create, edit, and move pages</i> ticked. ' + wikiLink(WIKI.helpUrl, 'Step-by-step help') + '.</div>' +
      '<details class="adv"><summary>Advanced</summary><label for="wkApi">Wiki API address</label><input type="text" id="wkApi" spellcheck="false" value="' + esc(apiUrl) + '">' +
      '<label class="chk"><input type="checkbox" id="wkNoProxy"> Do not use this computer\'s proxy settings</label></details>' +
      '<div class="err" id="wkErr" hidden></div>',
      [['Cancel', null], ['Connect', function () {
        var u = $('wkUser').value.trim(), a = $('wkApi').value.trim(), pw = $('wkPass').value;
        if (!u || !pw) { showErr('wkErr', 'Enter the bot username and the bot password.'); return false; }
        busy(true);
        api('/api/wiki/login', { api: a, username: u, password: pw, noProxy: $('wkNoProxy').checked }).then(function (s) {
          WIKI = s; renderWiki(); lsSet('wst.wikiUser', u); lsSet('wst.wikiApi', a); closeModal();
          toast('Connected to the wiki as ' + s.user + '.' + (s.canEdit ? '' : ' This bot password cannot edit pages: add Edit existing pages to it.'));
          if (after) after();
        }).catch(function (e) { busy(false); if ($('wkPass')) $('wkPass').value = ''; showErr('wkErr', e.message); });
        pw = null;
        return false;
      }, true]], true);
    setTimeout(function () { var f = user ? $('wkPass') : $('wkUser'); if (f) f.focus(); }, 30);
  }
  function wikiMenu() {
    if (!WIKI.connected) return connectDialog();
    modal('Connected to the wiki', '<p>Connected as <b>' + esc(WIKI.user) + '</b> to ' + esc(WIKI.api) + '.</p><p>' +
      (WIKI.canEdit ? 'Your bot password can edit pages' + (WIKI.canCreate ? ' and create new ones.' : ', but not create new ones (add <i>Create, edit, and move pages</i> to it).') :
        '<b>Your bot password cannot edit pages.</b> Add <i>Edit existing pages</i> to it on ' + wikiLink(WIKI.botPasswordsUrl, 'Special:BotPasswords') + '.') +
      '</p><p class="muted small">Disconnect when you finish. Closing the tool also ends the connection.</p>',
      [['Close', null], ['Disconnect', function () {
        api('/api/wiki/logout', {}).then(function (s) { WIKI = s; renderWiki(); toast('Disconnected from the wiki.'); }).catch(function (e) { toast(e.message, true); });
        return true;
      }, true]], true);
  }
  function openFromWiki(prefill) {
    modal('Open a page from the wiki',
      '<label for="wkTitle">Page title</label><input type="text" id="wkTitle" spellcheck="false" autocomplete="off" placeholder="Start typing, for example Sample Data Hub" value="' + esc(prefill || '') + '">' +
      '<div id="wkHits" class="hits"></div><div class="hint">Titles are case sensitive. Pick one from the list, or type it exactly.</div><div class="err" id="wkErr" hidden></div>',
      [['Cancel', null], ['Open', function () { openWikiTitle($('wkTitle').value.trim()); return false; }, true]], true);
    var inp = $('wkTitle');
    inp.addEventListener('input', function () { debounce('wksearch', 250, function () { searchWiki(inp.value); }); });
    $('wkHits').addEventListener('click', function (e) { var h = e.target.closest('[data-title]'); if (h) openWikiTitle(h.dataset.title); });
    setTimeout(function () { inp.focus(); if (prefill) searchWiki(prefill); }, 30);
  }
  function searchWiki(q) {
    if (!$('wkHits')) return;
    if (!q.trim()) { $('wkHits').innerHTML = ''; return; }
    api('/api/wiki/search?q=' + encodeURIComponent(q)).then(function (r) {
      if (!$('wkHits')) return;
      $('wkHits').innerHTML = r.titles.length ? r.titles.map(function (t) { return '<button type="button" class="hit" data-title="' + esc(t) + '">' + esc(t) + '</button>'; }).join('') :
        '<div class="muted small">No page titles start with that.</div>';
    }).catch(function (e) { wikiErr(e, 'wkErr', function () { openFromWiki(q); }); });
  }
  function openWikiTitle(t) {
    if (!t) return showErr('wkErr', 'Type a page title.');
    busy(true);
    api('/api/wiki/open?title=' + encodeURIComponent(t)).then(function (r) {
      busy(false);
      if (r.redirect) {
        $('wkTitle').value = r.redirect;
        return showErr('wkErr', r.source.title + ' redirects to ' + r.redirect + '. Press Open to open that page.');
      }
      closeModal();
      if (r.missing) {
        return modal('No page with that title', '<p>There is no page called <b>' + esc(r.source.title) + '</b> on the wiki yet. ' +
          'Start a new page with that title? Publishing creates it.</p>', [['Cancel', null], ['Start a new page', function () {
            confirmReplace('Replace the current page?', 'The new page will replace what is on the page now.', function () {
              loadDoc({ title: r.source.title, summary: '', toc: true, categories: [], blocks: [], _wiki: r.source }, 'New page: pick a template on the left to start.');
            });
            return true;
          }, true]], true);
      }
      confirmReplace('Replace the current page?', 'The page from the wiki will replace what is on the page now.', function () {
        var lays = r.doc.blocks.filter(function (b) { return b.type === 'layout'; }).length, raws = r.doc.blocks.filter(function (b) { return b.type === 'raw'; }).length;
        loadDoc(r.doc, 'Opened ' + r.source.title + ' from the wiki (revision ' + r.source.revid + ')' + (lays ? ', ' + lays + ' layouts with editable text' : '') +
          (raws ? ', ' + raws + ' kept as wiki code' : '') + '.');
        if (r.source.protected) setTimeout(function () { toast('This page is protected. You can edit it here, but only a wiki admin can publish it.', true); }, 2500);
      });
    }).catch(function (e) { busy(false); wikiErr(e, 'wkErr', function () { openFromWiki(t); }); });
  }
  function publishFlow() {
    if (!WIKI.connected) return connectDialog(publishFlow);
    commit();
    var title = (DOC._wiki && DOC._wiki.title) || DOC.title || '';
    if (!title.trim()) { toast('Give the page a title first.', true); return focusAt(document.querySelector('.ptitle'), 'end'); }
    showPublish(title);
  }
  function showPublish(title) {
    modal('Publish to the wiki', '<p class="muted">Comparing your page with the one on the wiki&hellip;</p>', [['Cancel', null]]);
    api('/api/wiki/preview', { doc: DOC, title: title }).then(function (r) {
      var w = [], errs = r.issues.filter(function (i) { return i.level === 'error'; }), blocked = false;
      if (r.protected) { w.push(['bad', 'This page is protected (' + esc(r.protected) + '). Only a wiki admin can change it, so the wiki will refuse to save it.']); blocked = true; }
      if (!r.canEdit) { w.push(['bad', 'Your bot password cannot edit pages. Add <i>Edit existing pages</i> to it on Special:BotPasswords.']); blocked = true; }
      if (!r.exists && !r.canCreate) { w.push(['bad', 'Your bot password cannot create pages. Add <i>Create, edit, and move pages</i> to it on Special:BotPasswords.']); blocked = true; }
      if (r.existsButNotOpened) { w.push(['bad', 'A page called <b>' + esc(r.title) + '</b> is already on the wiki. To change it, open it from the wiki first (Open, A page on the wiki). Or change the title below to publish a new page.']); blocked = true; }
      if (r.changedSinceOpen) w.push(['warn', 'Someone else changed this page after you opened it (revision ' + r.openedRevid + ' is now ' + r.currentRevid + '). Publishing replaces their change: the lines below include undoing it. To keep it, save a draft, open the page from the wiki again and redo your edit.']);
      if (errs.length) w.push(['bad', errs.length + ' Check error' + (errs.length === 1 ? '' : 's') + ': ' + errs.slice(0, 3).map(function (i) { return esc(i.message); }).join(' ') + (errs.length > 3 ? ' &hellip;' : '')]);
      if (r.todos.length) w.push(['warn', r.todos.length + ' hidden TODO note' + (r.todos.length === 1 ? '' : 's') + ' will go up with the page (they are not shown on it).']);
      if (r.missingFiles.length) w.push(['warn', 'These pictures are not on the wiki yet and will show as red links until you upload them (Special:Upload): ' + r.missingFiles.map(esc).join(', ') + '.']);
      var head = r.exists ? (r.samePage ? 'Updating ' + wikiLink(r.url, r.title) + ' (you opened revision ' + r.openedRevid + ').' : 'There is already a page called ' + wikiLink(r.url, r.title) + '.') :
        'Creating a new page: <b>' + esc(r.title) + '</b>.';
      var html = '<p>' + head + '</p>' + w.map(function (x) { return '<div class="pw ' + x[0] + '">' + x[1] + '</div>'; }).join('') +
        '<div class="pgrid"><div><label for="pbTitle">Page title on the wiki</label><input type="text" id="pbTitle" value="' + esc(r.title) + '"></div>' +
        '<div><label for="pbSum">Edit summary <span class="req">needed</span></label><input type="text" id="pbSum" maxlength="400" placeholder="What you changed, for example: Updated the steps for the new server" value="' + esc(lastSummary) + '"></div></div>' +
        '<label class="chk"><input type="checkbox" id="pbMinor"> Minor edit (spelling or layout only)</label>' +
        (errs.length ? '<label class="chk"><input type="checkbox" id="pbAck"> I have read the Check errors and want to publish anyway</label>' : '') +
        '<label>What will change on the wiki <span class="small muted">' + (r.exists ? '+' + r.added + ' / &minus;' + r.removed + ' lines' : 'a new page') + '</span></label>' +
        '<div class="diff">' + r.diff + '</div>' +
        (r.samePage ? '<div class="hint">A page opened from the wiki can change a little where you did not edit it (spacing, older styles brought up to date). Read the changes before you publish.</div>' : '');
      modal('Publish to the wiki', html, [['Cancel', null], [r.changedSinceOpen ? 'Publish over their change' : 'Publish', function () { return doPublish(r); }, true]]);
      if (blocked) busy(true);
      $('pbTitle').addEventListener('change', function () { var t = this.value.trim(); if (t && t !== r.title) showPublish(t); });
      setTimeout(function () { var s = $('pbSum'); if (s) s.focus(); }, 30);
    }).catch(function (e) { closeModal(); wikiErr(e, null, function () { showPublish(title); }); });
  }
  function doPublish(r) {
    var t = $('pbTitle').value.trim(), sum = $('pbSum').value.trim();
    if (t !== r.title) { showPublish(t); return false; }
    if ($('pbAck') && !$('pbAck').checked) { toast('Tick the box to say you have read the Check errors, or close this and fix them.', true); return false; }
    if (!sum) { $('pbSum').focus(); toast('Add an edit summary: one line on what you changed.', true); return false; }
    lastSummary = sum;
    busy(true);
    api('/api/wiki/publish', { doc: DOC, title: t, summary: sum, minor: $('pbMinor').checked, force: !!r.changedSinceOpen }).then(function (res) {
      commit(); DOC._wiki = res.source; commit(); renderPageBits();
      var x = res.result;
      modal('Published', '<p>' + (x.nochange ? 'Nothing to save: the wiki already has exactly this page.' :
        (x.new ? 'Created ' : 'Saved ') + '<b>' + esc(x.title) + '</b> on the wiki' + (x.newrevid ? ' (revision ' + x.newrevid + ')' : '') + '.') + '</p>' +
        (res.backup ? '<p class="muted small">A copy of the version it replaced is in ' + esc(res.backup) + '.</p>' : ''),
        [['Close', null], ['Open on the wiki', function () { window.open(res.source.url, '_blank', 'noopener'); return true; }, true]], true);
    }).catch(function (e) {
      busy(false);
      if (e.code === 'editconflict') {
        return modal('Someone else changed this page', '<p>' + esc(e.message) + ' Your page was not published.</p>' +
          '<p>Look at the changes again: they now include undoing the other person&rsquo;s edit. To keep their edit, save a draft, open the page from the wiki again and redo yours.</p>',
          [['Cancel', null], ['Look at the changes', function () { showPublish(t); return true; }, true]], true);
      }
      wikiErr(e, null, function () { showPublish(t); });
    });
    return false;
  }

  // ------------------------------------------------------------------ insert menu and slash command
  var INS = [
    ['Text', 'text', '¶', 'grey', 'Text', 'Paragraphs and lists'],
    ['Text', 'h2', 'H2', 'navy', 'Section heading', 'A coloured bar. Listed in the contents box.'],
    ['Text', 'h3', 'H3', 'navy', 'Sub-heading', 'A smaller heading inside a section.'],
    ['Text', 'card', '▭', 'navy', 'Intro card', 'A white card for the opening summary.'],
    ['Callouts', 'note', 'i', 'blue', 'Note', 'Useful context.'],
    ['Callouts', 'warning', '!', 'amber', 'Warning', 'Something that can go wrong.'],
    ['Callouts', 'danger', '✕', 'red', 'Stop', 'Something that causes harm or data loss.'],
    ['Callouts', 'tip', '✓', 'green', 'Tip', 'Good practice, or how to tell it worked.'],
    ['Callouts', 'old', '⌛', 'grey', 'Superseded', 'Older content kept for reference.'],
    ['Structure', 'step', '1', 'green', 'Numbered step', 'A step card. The numbers look after themselves.'],
    ['Structure', 'steps3', '1-3', 'green', 'Three steps', 'Three numbered steps at once.'],
    ['Structure', 'table', '▦', 'navy', 'Table', 'Rows and columns with a coloured header.'],
    ['Structure', 'facts', '≡', 'navy', 'Key facts', 'Labels down the left, like page properties.'],
    ['Structure', 'cards', '▥', 'blue', 'Cards', 'Two to four cards side by side.'],
    ['Structure', 'flow', '→', 'blue', 'Flow', 'Stages joined by arrows.'],
    ['Structure', 'collapse', '▸', 'navy', 'Expandable section', 'Folds away on the wiki. Good for FAQs.'],
    ['Media and code', 'code', 'SQL', 'navy', 'SQL code box', 'SSMS-style box with line numbers and colours.'],
    ['Media and code', 'codetext', '&lt;/&gt;', 'grey', 'Text code box', 'Commands, paths or output, no colours.'],
    ['Media and code', 'image', '▣', 'green', 'Picture', 'A 700px picture that opens full size.'],
    ['Media and code', 'email', '✉', 'blue', 'Email thread', 'Outlook-style thread, newest first. Can import .eml or .msg.'],
    ['Page', 'hero', '★', 'navy', 'Page banner', 'The blue banner at the top of a page.'],
    ['Page', 'divider', '—', 'grey', 'Divider', 'A thin line.'],
    ['Page', 'raw', '{ }', 'grey', 'Wiki code', 'Anything else, kept exactly as you type it.']
  ];
  var insSel = 0, insItems = [];
  function openInsert(rect, afterId, query, replaceId) {
    INS_AFTER = afterId; INS_REPLACE = replaceId || null;
    var pop = $('insertPop');
    pop.hidden = false;
    $('insSearch').value = query || '';
    fillInsert(query || '');
    var x = Math.min(rect.left, window.innerWidth - 350), y = rect.bottom + 6;
    if (y + 420 > window.innerHeight) y = Math.max(8, rect.top - 426);
    pop.style.left = Math.max(8, x) + 'px'; pop.style.top = y + 'px';
    if (!SLASH) setTimeout(function () { $('insSearch').focus(); }, 0);
  }
  function fillInsert(q) {
    q = (q || '').toLowerCase().trim();
    insItems = INS.filter(function (it) { return !q || (it[4] + ' ' + it[5] + ' ' + it[1] + ' ' + it[0]).toLowerCase().indexOf(q) >= 0; });
    if (insSel >= insItems.length) insSel = 0;
    var g = '', h = '';
    insItems.forEach(function (it, i) {
      if (it[0] !== g) { g = it[0]; h += '<div class="ig">' + g + '</div>'; }
      h += '<button class="ii' + (i === insSel ? ' on' : '') + '" data-kind="' + it[1] + '" data-i="' + i + '"><span class="ic" style="background:' + ST.colours[it[3]] + '">' + it[2] + '</span><span><b>' + it[4] + '</b><span class="d">' + it[5] + '</span></span></button>';
    });
    $('insList').innerHTML = h || '<div class="muted" style="padding:8px">No block matches. Press Esc.</div>';
  }
  function closeInsert() { $('insertPop').hidden = true; SLASH = null; }
  function chooseInsert(kind) {
    var after = INS_AFTER, replace = INS_REPLACE;
    if (SLASH) {
      var s = SLASH; SLASH = null;
      if (s.para && s.para.parentNode) {
        var rtEl = s.rt;
        if (s.para === rtEl) rtEl.innerHTML = ''; else s.para.parentNode.removeChild(s.para);
        var b = blockById(s.id);
        if (b) setPath(b, rtEl.dataset.f, fieldValue(rtEl));
        if (b && b.type === 'text' && !fieldValue(rtEl)) replace = s.id; else after = s.id;
      }
    }
    closeInsert();
    insertKind(kind, after, replace);
  }
  function checkSlash(rtEl, blk) {
    var sel = window.getSelection();
    if (!sel.rangeCount || !sel.isCollapsed) { if (SLASH) closeInsert(); return; }
    var n = sel.anchorNode, para = n;
    while (para && para !== rtEl && !/^(P|LI|DIV)$/.test(para.nodeName)) para = para.parentNode;
    if (!para) return;
    var txt = (para.textContent || '').replace(/ /g, ' ');
    if (/^\/[\w -]{0,24}$/.test(txt) && !rtEl.classList.contains('cell') && !rtEl.classList.contains('inline') && !rtEl.classList.contains('leaf')) {
      SLASH = { id: blk.dataset.id, para: para, rt: rtEl };
      var r = sel.getRangeAt(0).getBoundingClientRect();
      if (!r.height) r = rtEl.getBoundingClientRect();
      openInsert(r, blk.dataset.id, txt.slice(1));
    } else if (SLASH) closeInsert();
  }

  // ------------------------------------------------------------------ inline formatting
  function activeRt() {
    var sel = window.getSelection();
    if (!sel.rangeCount) return null;
    var n = sel.anchorNode; n = n && (n.nodeType === 1 ? n : n.parentNode);
    return n && n.closest ? n.closest('.rt') : null;
  }
  var savedRange = null;
  function saveRange() { var s = window.getSelection(); savedRange = s.rangeCount ? s.getRangeAt(0).cloneRange() : null; }
  function restoreRange() {
    if (!savedRange) return;
    var el = savedRange.startContainer; el = el.nodeType === 1 ? el : el.parentNode;
    var r = el.closest && el.closest('.rt'); if (r) r.focus();
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(savedRange);
  }
  function exec(cmd, val) {
    if (!activeRt()) return toast('Click into some text first.');
    document.execCommand(cmd, false, val || null);
    var r = activeRt(); if (r) r.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function toggleCode() {
    var r = activeRt(); if (!r) return toast('Click into some text first.');
    var sel = window.getSelection(), n = sel.anchorNode, code = (n.nodeType === 1 ? n : n.parentNode).closest('code');
    if (code && r.contains(code)) { code.outerHTML = esc(code.textContent); }
    else {
      var t = sel.toString() || 'code';
      document.execCommand('insertHTML', false, '<code>' + esc(t) + '</code>&#8203;');
    }
    r.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function clearFormat() {
    var r = activeRt(); if (!r) return;
    document.execCommand('removeFormat'); document.execCommand('unlink');
    var sel = window.getSelection();
    r.querySelectorAll('code,span[data-pill]').forEach(function (c) { if (sel.containsNode(c, true)) c.outerHTML = esc(c.textContent); });
    r.dispatchEvent(new Event('input', { bubbles: true }));
  }
  var PILLS = [['green', 'Live'], ['amber', 'In progress'], ['red', 'Blocked'], ['blue', 'Planned'], ['purple', 'Under review'], ['navy', 'Information'], ['grey', 'Retired']];
  function insertPill(c, label) {
    restoreRange();
    if (!activeRt()) return toast('Click into some text first.');
    var t = window.getSelection().toString().trim() || label;
    document.execCommand('insertHTML', false, '<span data-pill="' + c + '">' + esc(t) + '</span>&nbsp;');
    activeRt().dispatchEvent(new Event('input', { bubbles: true }));
  }
  function linkDialog() {
    var r = activeRt();
    if (!r) return toast('Click into some text, or select the words to link.');
    saveRange();
    var sel = window.getSelection(), n = sel.anchorNode, a = (n.nodeType === 1 ? n : n.parentNode).closest('a');
    var text = a ? a.textContent : sel.toString(), href = a ? a.getAttribute('href') : '';
    var target = href.indexOf('wiki:') === 0 ? href.slice(5) : href;
    modal(a ? 'Edit link' : 'Add a link',
      '<label for="lkTo">Link to</label><input type="text" id="lkTo" value="' + esc(target) + '" placeholder="A wiki page title, e.g. Sample Data Hub, or a web address starting https://">' +
      '<div class="hint" id="lkKind"></div><label for="lkText">Text to show</label><input type="text" id="lkText" value="' + esc(text) + '" placeholder="Leave blank to show the page title">' +
      '<div class="hint">Wiki page titles are case sensitive. Never link SharePoint sharing links; name the library and folder instead.</div>',
      [a ? ['Remove link', function () { restoreRange(); var aa = findLinkAtRange(); if (aa) { aa.outerHTML = esc(aa.textContent); r.dispatchEvent(new Event('input', { bubbles: true })); } return true; }] : null,
        ['Cancel', null], ['Save link', function () { return applyLink(r, a); }, true]].filter(Boolean), true);
    var upd = function () {
      var v = $('lkTo').value.trim();
      $('lkKind').textContent = !v ? '' : /^(https?:|mailto:|ftp:|file:)/i.test(v) ? 'Web address' : 'Wiki page: [[' + v + ']]';
    };
    $('lkTo').addEventListener('input', upd); upd();
    setTimeout(function () { $('lkTo').focus(); }, 30);
  }
  function findLinkAtRange() {
    if (!savedRange) return null;
    var n = savedRange.startContainer; n = n.nodeType === 1 ? n : n.parentNode;
    return n.closest('a');
  }
  function applyLink(r, existing) {
    var to = $('lkTo').value.trim(), text = $('lkText').value.trim();
    if (!to) { toast('Type a page title or a web address.', true); return false; }
    if (/sharepoint\.com\/.*(:[a-z]:|sharing|guestaccess|\?e=)/i.test(to)) { toast('That looks like a SharePoint sharing link. Name the library and folder in the text instead.', true); return false; }
    var href = /^(https?:|mailto:|ftp:|file:)/i.test(to) ? to : 'wiki:' + to.replace(/^\[\[|\]\]$/g, '');
    restoreRange();
    var a = existing && findLinkAtRange();
    if (a) { a.setAttribute('href', href); if (text) a.textContent = text; }
    else {
      var show = text || window.getSelection().toString() || to;
      document.execCommand('insertHTML', false, '<a href="' + esc(href) + '">' + esc(show) + '</a>');
    }
    r.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }
  function updateLinkTip() {
    var tip = $('linkTip'), sel = window.getSelection();
    if (!sel.rangeCount) { tip.hidden = true; return; }
    var n = sel.anchorNode; n = n && (n.nodeType === 1 ? n : n.parentNode);
    var a = n && n.closest && n.closest('.rt a');
    if (!a) { tip.hidden = true; return; }
    var h = a.getAttribute('href') || '';
    tip.innerHTML = (h.indexOf('wiki:') === 0 ? 'Wiki page: <b>' + esc(h.slice(5)) + '</b>' : 'Web: <b>' + esc(h.length > 60 ? h.slice(0, 57) + '...' : h) + '</b>') +
      '<button data-tip="edit">Edit</button><button data-tip="remove">Remove</button>';
    tip.hidden = false;
    var r = a.getBoundingClientRect();
    tip.style.left = Math.max(8, r.left) + 'px'; tip.style.top = (r.bottom + 6) + 'px';
    tip._a = a;
  }

  // ------------------------------------------------------------------ pictures
  function pickImage(id) {
    var fi = $('fileIn'); fi.value = ''; fi.accept = 'image/*';
    fi.onchange = function () { if (fi.files[0]) loadImage(id, fi.files[0]); };
    fi.click();
  }
  function cleanBase(n) { return String(n || 'image').replace(/\.[A-Za-z0-9]+$/, '').trim().replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[_.]+|[_.]+$/g, '') || 'image'; }
  function loadImage(id, file) {
    if (!/^image\//.test(file.type || '')) return toast('That is not a picture.', true);
    var fr = new FileReader();
    fr.onload = function () {
      var img = new Image();
      img.onload = function () {
        var b = blockById(id); if (!b) return;
        commit();
        IMGS[id] = fr.result;
        var base = cleanBase(/^image\.(png|jpe?g)$/i.test(file.name) ? (DOC.title || 'Screenshot') : file.name);
        if (img.naturalWidth > 700) { b.file = b.file || base + '_700.png'; b.full = b.full || base + '_full.png'; }
        else { b.file = b.file || base + '.png'; }
        b._w = img.naturalWidth; b._h = img.naturalHeight;
        renderBlock(id); commit();
        toast(img.naturalWidth > 700 ? 'Picture added. Press Download wiki copies to get the 700px and full-size files to upload.' : 'Picture added. It is already 700px or less.');
      };
      img.src = fr.result;
    };
    fr.readAsDataURL(file);
  }
  function makeCopies(id) {
    var b = blockById(id), src = IMGS[id];
    if (!b || !src) return toast('Choose a picture first.');
    var img = new Image();
    img.onload = function () {
      var w = img.naturalWidth, h = img.naturalHeight;
      var out = function (cw, ch, name) {
        var c = document.createElement('canvas'); c.width = cw; c.height = ch;
        var x = c.getContext('2d'); x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high'; x.drawImage(img, 0, 0, cw, ch);
        c.toBlob(function (bl) { download(name, bl); }, 'image/png');
      };
      if (w > 700) { out(700, Math.round(h * 700 / w), b.file || 'image_700.png'); setTimeout(function () { out(w, h, b.full || 'image_full.png'); }, 400); }
      else out(w, h, b.file || 'image.png');
      toast('Upload the downloaded files to the wiki with these exact names.');
    };
    img.src = src;
  }
  function download(name, data) {
    var blob = data instanceof Blob ? data : new Blob([data], { type: 'text/plain;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  // ------------------------------------------------------------------ code boxes
  function fetchCode(b) {
    var key = b.id, snap = b.lang + '|' + b.title + '|' + b.code;
    if (fetchCode.pending && fetchCode.pending[key] === snap) return;
    (fetchCode.pending = fetchCode.pending || {})[key] = snap;
    api('/api/codebox', { title: b.title, code: b.code, lang: b.lang }).then(function (r) {
      var d = document.createElement('div'); d.innerHTML = r.html;
      var body = d.firstChild && d.firstChild.children[1];
      CODEHTML[key] = body ? body.outerHTML : '';
      delete fetchCode.pending[key];
      if (CODEEDIT !== key && document.querySelector('.blk[data-id="' + key + '"]')) renderBlock(key, captureFocus());
    }).catch(function () { delete fetchCode.pending[key]; });
  }

  // ------------------------------------------------------------------ email import
  function importMail(id) {
    var fi = $('fileIn'); fi.value = ''; fi.accept = '.eml,.msg';
    fi.onchange = function () {
      var f = fi.files[0]; if (!f) return;
      f.arrayBuffer().then(function (buf) {
        return api('/api/mail?name=' + encodeURIComponent(f.name) + '&anon=1&strip=1', buf, true);
      }).then(function (r) {
        var b = blockById(id); if (!b) return;
        commit();
        var empty = (b.emails || []).every(function (e) { return !e.from && !e.subject && !String(e.html || '').replace(/<[^>]*>/g, '').trim(); });
        var start = empty ? 0 : b.emails.length;
        if (empty) { b.emails = []; b.ph = {}; }
        r.block.emails.forEach(function (e, i) { b.emails.push(e); });
        Object.keys(r.block.ph || {}).forEach(function (k) { var m = k.split('.'); b.ph = b.ph || {}; b.ph['emails.' + (start + (+m[1])) + '.' + m[2]] = true; });
        renderBlock(id); commit();
        toast('Imported ' + r.block.emails.length + ' email(s). Names became "Role to be added": type the role titles. Check the text for names and signatures.');
      }).catch(function (e) { toast(e.message, true); });
    };
    fi.click();
  }

  // ------------------------------------------------------------------ export and check
  function refreshCheck() {
    return api('/api/export', DOC).then(function (r) {
      EXPORT = r;
      var probs = r.notes.filter(function (n) { return n.level !== 'info'; }).length + r.issues.filter(function (i) { return i.level !== 'info'; }).length;
      var cc = $('checkCount'), b = $('bCheck');
      cc.textContent = probs ? probs + ' to check' : 'All good';
      b.classList.toggle('bad', probs > 0); b.classList.toggle('ok', probs === 0);
      if (!$('drawer').hidden) fillDrawer();
      return r;
    }).catch(function (e) { status('Check failed: ' + e.message); });
  }
  function openDrawer(tab) {
    commit();
    $('drawer').hidden = false;
    dtab(tab || 'code');
    refreshCheck().then(function () { setTimeout(placeTools, 30); });
  }
  function dtab(t) {
    document.querySelectorAll('.dhead .tabs button').forEach(function (b) { b.classList.toggle('on', b.dataset.dtab === t); });
    $('dpane-code').hidden = t !== 'code'; $('dpane-check').hidden = t !== 'check';
  }
  function fillDrawer() {
    if (!EXPORT) return;
    $('dText').value = EXPORT.text;
    var lines = EXPORT.text.split('\n').length;
    $('dInfo').textContent = lines + ' lines, ' + EXPORT.text.length + ' characters. Paste it into the page "' + (DOC.title || 'untitled') + '" on the wiki.';
    var t = (DOC.title || '').replace(/ /g, '_');
    $('dWiki').href = ST.wikiEdit.replace('%s', encodeURIComponent(t));
    $('dWiki').style.visibility = t ? 'visible' : 'hidden';
    var items = EXPORT.notes.map(function (n) { return { level: n.level, msg: n.message, block: n.block, src: 'page' }; })
      .concat(EXPORT.issues.map(function (i) { return { level: i.level, msg: i.message, line: i.line, src: 'wiki' }; }));
    var order = { error: 0, warn: 1, info: 2 };
    items.sort(function (a, b) { return order[a.level] - order[b.level]; });
    var probs = items.filter(function (i) { return i.level !== 'info'; }).length;
    $('dCount').textContent = probs ? '(' + probs + ')' : '';
    $('dIssues').innerHTML = (probs ? '' : '<div class="okbox"><b>Nothing to fix.</b> The page follows the house rules. Read it through once more before you publish.</div>') +
      items.map(function (i, k) {
        var where = i.block >= 0 && i.src === 'page' ? 'Click to show it on the page' : (i.line ? 'Line ' + i.line + ' of the wiki code' : (i.block === -1 ? 'Page panel' : ''));
        return '<div class="issue ' + i.level + '" data-k="' + k + '"><span class="lv">' + (i.level === 'warn' ? 'check' : i.level === 'error' ? 'fix' : 'note') + '</span>' + esc(i.msg) +
          (where ? '<div class="small muted">' + where + '</div>' : '') + '</div>';
      }).join('');
    $('dIssues')._items = items;
  }
  function goIssue(it) {
    if (it.src === 'page' && it.block >= 0) {
      var b = DOC.blocks[it.block]; if (!b) return;
      var el = document.querySelector('.blk[data-id="' + b.id + '"]'); if (!el) return;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el.classList.add('flash'); setTimeout(function () { el.classList.remove('flash'); }, 1600);
      var m = /Still to do: (.*)$/.exec(it.msg), target = null;
      if (m) el.querySelectorAll('[data-ph],.pl.isph').forEach(function (p) { if (!target && p.textContent.trim() === m[1].trim()) target = p; });
      select(b.id);
      if (target) { target.click(); var rr = document.createRange(); rr.selectNodeContents(target); var s = window.getSelection(); (target.closest('[contenteditable="true"]') || target).focus(); s.removeAllRanges(); s.addRange(rr); }
    } else if (it.block === -1) { sideTab('page'); $('pgSummary').focus(); }
    else if (it.line) {
      dtab('code');
      var lines = $('dText').value.split('\n'), a = 0;
      for (var i = 0; i < it.line - 1 && i < lines.length; i++) a += lines[i].length + 1;
      $('dText').focus(); $('dText').setSelectionRange(a, a + (lines[it.line - 1] || '').length);
    }
  }
  function copyText(t) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
    var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
    var ok = document.execCommand('copy'); ta.remove();
    return ok ? Promise.resolve() : Promise.reject(new Error('copy blocked'));
  }

  // ------------------------------------------------------------------ templates
  function tcardHTML(t) {
    return '<button class="tcard" data-tpl="' + t.id + '" style="--c:' + (ST.colours[t.colour] || ST.colours.blue) + '"><span class="ti">' + esc(t.icon) +
      '</span><span><b>' + esc(t.name) + '</b><span>' + esc(t.use) + '</span></span></button>';
  }
  function renderTemplates() {
    var q = ($('tplSearch').value || '').toLowerCase(), g = '', h = '';
    TPLS.forEach(function (t) {
      if (q && (t.name + ' ' + t.use + ' ' + t.desc + ' ' + t.group).toLowerCase().indexOf(q) < 0) return;
      if (t.group !== g) { g = t.group; h += '<div class="tgroup">' + esc(g === 'Page types' ? 'Page types' : g) + '</div>'; }
      h += tcardHTML(t);
    });
    $('tplList').innerHTML = h || '<div class="muted">No template matches.</div>';
  }
  function previewTemplate(id) {
    api('/api/template?id=' + encodeURIComponent(id)).then(function (doc) {
      var t = TPLS.filter(function (x) { return x.id === id; })[0];
      doc = sanitizeDoc(doc);
      var cats = (t.categories || []).length ? '<p><b>Categories added:</b> ' + t.categories.map(esc).join(', ') + '</p>' : '';
      var body = '<div class="tprev"><div class="about"><p><b>Use it for:</b> ' + esc(t.use) + '</p><p>' + esc(t.desc) + '</p>' + cats +
        '<p class="muted small">Grey italic text is a prompt. Click it and type. Anything you leave becomes a hidden TODO note, so nothing made up appears on the wiki.</p></div>' +
        '<div class="mini"><div class="paper"><div class="ptitle" style="color:#9aa5b1;font-style:italic">Your page title</div>' + (doc.blocks.length ? docHTML(doc) : '<p class="muted">An empty page.</p>') + '</div></div></div>';
      var go = function (append) {
        if (append) {
          commit();
          doc.blocks.forEach(function (b) { b.id = uid(); });
          var hero = doc.blocks.filter(function (b) { return b.type === 'hero'; });
          var add = DOC.blocks.some(function (b) { return b.type === 'hero'; }) ? doc.blocks.filter(function (b) { return b.type !== 'hero'; }) : doc.blocks;
          DOC.blocks = DOC.blocks.concat(add);
          (doc.categories || []).forEach(function (c) { if (DOC.categories.indexOf(c) < 0) DOC.categories.push(c); });
          renderAll(); commit();
          if (add[0]) { var el = document.querySelector('.blk[data-id="' + add[0].id + '"]'); if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
          toast('Added the ' + t.name + ' sections to the end of your page.');
          return;
        }
        var keep = DOC.blocks.length ? '' : (DOC.title || '');
        var src = DOC.blocks.length ? null : DOC._wiki;   // a new wiki page started by title keeps its target
        var start = function () {
          doc.title = keep;
          if (src) doc._wiki = src;
          loadDoc(doc, 'New page from the ' + t.name + ' template.' + (keep ? '' : ' Type the title first.'));
          if (keep) setTimeout(function () { var f = document.querySelector('.blk [data-ph], .blk .pl.isph'); if (f) { f.scrollIntoView({ block: 'center' }); } }, 60);
        };
        if (DOC.blocks.length) saveDraft(true).then(start, start); else start();
      };
      var btns = [['Cancel', null]];
      if (DOC.blocks.length && id !== 'blank') btns.push(['Add its sections to my page', function () { go(true); return true; }]);
      btns.push([DOC.blocks.length ? 'Start a new page from it' : 'Use this template', function () { go(false); return true; }, true]);
      modal(t.name + ' template', body, btns);
      if (DOC.blocks.length) $('mFoot').insertAdjacentHTML('afterbegin', '<span class="muted small" style="margin-right:auto;align-self:center">Your current page is saved as a draft first.</span>');
    }).catch(function (e) { toast(e.message, true); });
  }

  // ------------------------------------------------------------------ modal
  function modal(title, html, buttons, narrow) {
    $('mTitle').textContent = title;
    $('mBody').innerHTML = html;
    var f = $('mFoot'); f.innerHTML = '';
    (buttons || []).forEach(function (b) {
      var btn = document.createElement('button');
      btn.textContent = b[0]; if (b[2]) btn.className = 'primary';
      btn.onclick = function () { var keep = b[1] ? b[1]() === false : false; if (!keep) closeModal(); };
      f.appendChild(btn);
    });
    document.querySelector('.mbox').classList.toggle('narrow', !!narrow);
    $('modal').hidden = false;
  }
  function closeModal() { $('modal').hidden = true; $('mBody').innerHTML = ''; }

  // ------------------------------------------------------------------ open and import
  function loadDrafts() {
    api('/api/drafts').then(function (list) {
      $('draftList').innerHTML = list.length ? list.map(function (d) {
        return '<button data-draft="' + esc(d.name) + '">' + esc(d.title) + '<small>' + esc(d.when) + ' &middot; ' + esc(d.name) + '</small></button>';
      }).join('') : '<div class="muted">No drafts saved yet.</div>';
    }).catch(function () { });
  }
  function openDraft(name) {
    confirmReplace('Open this draft?', 'The draft will replace what is on the page now.', function () {
      api('/api/draft?name=' + encodeURIComponent(name)).then(function (doc) { doc._draft = name; loadDoc(doc, 'Opened ' + name); }).catch(function (e) { toast(e.message, true); });
    });
  }
  function pasteImport(kind) {
    var wiki = kind === 'wiki';
    modal(wiki ? 'Bring in an existing wiki page' : 'Bring in plain text',
      (wiki ? '<p>On the wiki, open the page, choose <b>Edit</b>, select all the text and copy it. Paste it here.</p>' +
        '<p class="muted small">Parts in our house style become editable blocks. Other layouts (boxes inside boxes, diagrams, tables with merged or coloured cells) keep their exact look and you can still change their text. Only things like templates stay as <b>Wiki code</b>, so nothing is lost.</p>' :
        '<p>Paste plain text. Lines like <code>== Heading ==</code> become headings, numbered lines become steps, <code>*</code> lines become bullets, indented lines become a code box and tab-separated lines become a table.</p>') +
      '<textarea id="impText" class="big" spellcheck="false"></textarea>' +
      (wiki ? '<label for="impTitle">Page title on the wiki (as it appears at the top of the page)</label><input type="text" id="impTitle" placeholder="Taken from the hidden first line if there is one">' : ''),
      [['Cancel', null], ['Open in the editor', function () {
        var text = $('impText').value, title = wiki ? $('impTitle').value.trim() : '';
        if (!text.trim()) { toast('Paste something first.', true); return false; }
        api(wiki ? '/api/import' : '/api/import-plain', { text: text }).then(function (doc) {
          if (title) doc.title = title;
          var raws = doc.blocks.filter(function (b) { return b.type === 'raw'; }).length;
          var lays = doc.blocks.filter(function (b) { return b.type === 'layout'; }).length;
          confirmReplace('Replace the current page?', 'The imported page will replace what is on the page now.', function () {
            loadDoc(doc, doc.blocks.length + ' blocks brought in' + (lays ? ', ' + lays + ' kept as layouts with editable text' : '') + (raws ? ', ' + raws + ' kept as wiki code' : '') + '.');
          });
        }).catch(function (e) { toast(e.message, true); });
        return true;
      }, true]]);
    setTimeout(function () { $('impText').focus(); }, 30);
  }
  function importWord() {
    var fi = $('fileIn'); fi.value = ''; fi.accept = '.docx';
    fi.onchange = function () { if (fi.files[0]) importFile(fi.files[0]); };
    fi.click();
  }
  function importFile(f) {
    var ext = (f.name.split('.').pop() || '').toLowerCase();
    if (ext === 'json') {
      return f.text().then(function (t) {
        var doc; try { doc = JSON.parse(t); } catch (e) { return toast('That draft file could not be read.', true); }
        if (!doc || !Array.isArray(doc.blocks)) return toast('That is not a draft from this tool.', true);
        confirmReplace('Open this draft?', 'The draft will replace what is on the page now.', function () { loadDoc(doc, 'Opened ' + f.name); });
      });
    }
    if (ext === 'docx') {
      return f.arrayBuffer().then(function (buf) { return api('/api/docx?name=' + encodeURIComponent(f.name), buf, true); }).then(function (doc) {
        confirmReplace('Replace the current page?', 'The Word document will replace what is on the page now.', function () {
          loadDoc(doc, 'Word document brought in. Pictures in it were not carried over.');
        });
      }).catch(function (e) { toast(e.message, true); });
    }
    if (ext === 'txt' || ext === 'wiki') {
      return f.text().then(function (t) {
        var looksWiki = /^<div style="display:none">|<div style=|\{\||\[\[Category:/.test(t);
        return api(looksWiki ? '/api/import' : '/api/import-plain', { text: t }).then(function (doc) {
          confirmReplace('Replace the current page?', 'The file will replace what is on the page now.', function () { loadDoc(doc, 'Opened ' + f.name); });
        });
      }).catch(function (e) { toast(e.message, true); });
    }
    if (ext === 'eml' || ext === 'msg') {
      var b = makeBlock('email'); var i = SEL ? indexOf(SEL) + 1 : DOC.blocks.length;
      insertAt(i, [b]); select(b.id);
      var dt = new DataTransfer(); dt.items.add(f); var fi = $('fileIn'); fi.files = dt.files;
      importMailFile(b.id, f);
      return;
    }
    if (/^image\//.test(f.type)) {
      var ib = SEL && blockById(SEL);
      if (ib && ib.type === 'image') return loadImage(ib.id, f);
      var nb = makeBlock('image'); insertAt(SEL ? indexOf(SEL) + 1 : DOC.blocks.length, [nb]); return loadImage(nb.id, f);
    }
    toast('Drop a .docx, .txt, .json draft, .eml, .msg or a picture.', true);
  }
  function importMailFile(id, f) {
    f.arrayBuffer().then(function (buf) { return api('/api/mail?name=' + encodeURIComponent(f.name) + '&anon=1&strip=1', buf, true); }).then(function (r) {
      var b = blockById(id); if (!b) return;
      commit(); b.emails = r.block.emails; b.ph = r.block.ph || {}; renderBlock(id); commit();
      toast('Imported ' + b.emails.length + ' email(s). Type role titles where it says "Role to be added".');
    }).catch(function (e) { toast(e.message, true); });
  }
  function checkOnly() {
    var show = function (r, applied) {
      $('chkOut').innerHTML = (applied && applied.length ? '<div class="okbox" style="margin-bottom:8px"><b>Fixed:</b><ul style="margin:.3em 0 0 1.2em;padding:0">' +
        applied.map(function (a) { return '<li>' + esc(typeof a === 'string' ? a : (a.message || JSON.stringify(a))) + '</li>'; }).join('') + '</ul></div>' : '') +
        (r.issues.length ? r.issues.map(function (i) {
          return '<div class="issue ' + i.level + '"><span class="lv">' + i.level + '</span>' + esc(i.message) + (i.fixable ? ' <span class="small muted">(Fix can repair this)</span>' : '') +
            (i.line ? '<div class="small muted">Line ' + i.line + (i.text ? ': ' + esc(i.text) : '') + '</div>' : '') + '</div>';
        }).join('') : '<div class="okbox">No problems found.</div>');
    };
    modal('Check a page without editing it', '<p>Paste the wikitext of any page and press <b>Check</b>. <b>Fix the safe things</b> only makes mechanical repairs that cannot change what the page means, and lists them. To change the page properly, use <b>Open, Existing wiki page</b> instead.</p>' +
      '<textarea id="chkText" class="big" spellcheck="false"></textarea><div id="chkOut" style="margin-top:10px"></div>',
      [['Close', null],
        ['Copy', function () { copyText($('chkText').value).then(function () { toast('Copied.'); }); return false; }],
        ['Fix the safe things', function () {
          api('/api/fix', { text: $('chkText').value }).then(function (r) { $('chkText').value = r.text; show(r, r.applied); }).catch(function (e) { toast(e.message, true); });
          return false;
        }],
        ['Check', function () { api('/api/lint', { text: $('chkText').value }).then(function (r) { show(r); }).catch(function (e) { toast(e.message, true); }); return false; }, true]]);
  }

  // ------------------------------------------------------------------ side tabs
  function sideTab(t) {
    document.querySelectorAll('.side .tabs button').forEach(function (b) { b.classList.toggle('on', b.dataset.tab === t); });
    ['tpl', 'outline', 'page', 'help'].forEach(function (x) { $('pane-' + x).hidden = x !== t; });
  }

  // ------------------------------------------------------------------ events
  function wire() {
    document.execCommand('defaultParagraphSeparator', false, 'p');
    var paper = $('paper');
    paper.addEventListener('input', onInput);
    paper.addEventListener('focusin', function (e) {
      var blk = e.target.closest('.blk'); if (blk) select(blk.dataset.id);
      if (blk && e.target.classList.contains('codeedit')) CODEEDIT = blk.dataset.id;
      selectPh(e);
    });
    paper.addEventListener('mousedown', function (e) {
      var blk = e.target.closest('.blk');
      if (blk) select(blk.dataset.id);
      else if (!e.target.closest('.btools')) select(null);
    });
    paper.addEventListener('click', function (e) {
      selectPh(e);
      var act = e.target.closest('[data-act]');
      if (act) {
        var a = act.dataset.act, blk = act.closest('.blk');
        if (a === 'addBelow') { var r = act.getBoundingClientRect(); return openInsert(r, blk.dataset.id, ''); }
        if (a === 'delPill') { var b = blockById(blk.dataset.id); commit(); b.pills.splice(+act.dataset.i, 1); renderBlock(b.id); commit(); return; }
        if (a === 'pickImg') return pickImage(blk.dataset.id);
        if (a === 'editCode') { CODEEDIT = blk.dataset.id; renderBlock(CODEEDIT); var ta = document.querySelector('.blk[data-id="' + CODEEDIT + '"] textarea'); if (ta) { ta.focus(); } return; }
        if (a === 'allTemplates') { sideTab('tpl'); $('tplSearch').focus(); return; }
        if (a === 'blankText') { insertKind('text', null); return; }
        if (a === 'importMenu') { toggleOpen(true); return; }
        if (a === 'pageTab') { sideTab('page'); $('pgSummary').focus(); return; }
      }
      var tc = e.target.closest('[data-tpl]'); if (tc) return previewTemplate(tc.dataset.tpl);
    });
    paper.addEventListener('focusout', function (e) {
      var t = e.target;
      if (t.classList && t.classList.contains('codeedit')) {
        var blk = t.closest('.blk'), id = blk && blk.dataset.id;
        setTimeout(function () {
          var a = document.activeElement;
          if (a && a.classList && a.classList.contains('codeedit') && a.closest('.blk[data-id="' + id + '"]')) return;
          if (CODEEDIT === id) CODEEDIT = null;
          var b = blockById(id); if (b && String(b.code || '').trim()) { delete CODEHTML[id]; fetchCode(b); }
        }, 120);
      }
    });
    paper.addEventListener('paste', function (e) {
      var el = e.target.closest && e.target.closest('[data-f]');
      if (!el || el.tagName === 'TEXTAREA') return;
      var cd = e.clipboardData;
      var files = cd.files && cd.files.length ? cd.files : null;
      if (files && /^image\//.test(files[0].type)) {
        e.preventDefault();
        var blk = el.closest('.blk'), b = blk && blockById(blk.dataset.id);
        if (b && b.type === 'image') return loadImage(b.id, files[0]);
        var nb = makeBlock('image'); insertAt(indexOf(blk.dataset.id) + 1, [nb]); return loadImage(nb.id, files[0]);
      }
      e.preventDefault();
      if (el.classList.contains('rt')) {
        var html = cd.getData('text/html'), text = cd.getData('text/plain');
        var clean = html ? sanitize(html) : textToParas(text);
        if (el.classList.contains('cell') || el.classList.contains('inline')) clean = clean.replace(/<\/p>\s*<p>/g, '<br>').replace(/<\/?p>/g, '').replace(/<\/?(ul|ol)>/g, '').replace(/<li>/g, '').replace(/<\/li>/g, '<br>');
        document.execCommand('insertHTML', false, clean || esc(text));
      } else {
        document.execCommand('insertText', false, (cd.getData('text/plain') || '').replace(/\s*\n\s*/g, ' '));
      }
    });
    paper.addEventListener('keydown', onKey);
    paper.addEventListener('beforeinput', function (e) {
      var rtEl = e.target.closest && e.target.closest('.rt');
      if (rtEl) { var anc = phAncestor(rtEl); if (anc) anc.removeAttribute('data-ph'); }
      var el = e.target.closest && e.target.closest('.pl.isph');
      if (el) { el.classList.remove('isph'); var blk = el.closest('.blk'), b = blk && blockById(blk.dataset.id); if (b && b.ph) delete b.ph[el.dataset.f]; }
    });
    // drag and drop of blocks
    var dragId = null;
    paper.addEventListener('dragstart', function (e) {
      var h = e.target.closest && e.target.closest('.handle'); if (!h) return;
      var blk = h.closest('.blk'); dragId = blk.dataset.id;
      e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', 'block:' + dragId);
      try { e.dataTransfer.setDragImage(blk, 20, 20); } catch (x) { }
      setTimeout(function () { blk.classList.add('dragging'); }, 0);
    });
    paper.addEventListener('dragover', function (e) {
      if (!dragId) return;
      e.preventDefault();
      document.querySelectorAll('.drop-before,.drop-after').forEach(function (x) { x.classList.remove('drop-before', 'drop-after'); });
      var blk = e.target.closest && e.target.closest('.blk'); if (!blk || blk.dataset.id === dragId) return;
      var r = blk.getBoundingClientRect();
      blk.classList.add(e.clientY < r.top + r.height / 2 ? 'drop-before' : 'drop-after');
    });
    paper.addEventListener('drop', function (e) {
      if (!dragId) return;
      e.preventDefault(); e.stopPropagation();
      var tgt = document.querySelector('.drop-before,.drop-after');
      if (tgt) {
        var after = tgt.classList.contains('drop-after'), tid = tgt.dataset.id;
        commit();
        var b = DOC.blocks.splice(indexOf(dragId), 1)[0];
        var j = indexOf(tid) + (after ? 1 : 0);
        DOC.blocks.splice(j, 0, b);
        renderAll(); commit();
      }
      dragEnd();
    });
    function dragEnd() { dragId = null; document.querySelectorAll('.dragging,.drop-before,.drop-after').forEach(function (x) { x.classList.remove('dragging', 'drop-before', 'drop-after'); }); }
    paper.addEventListener('dragend', dragEnd);
    // image drop zones
    paper.addEventListener('dragover', function (e) { var z = e.target.closest && e.target.closest('.imgdrop'); if (z && !dragId) { e.preventDefault(); z.classList.add('over'); } });
    paper.addEventListener('dragleave', function (e) { var z = e.target.closest && e.target.closest('.imgdrop'); if (z) z.classList.remove('over'); });
    paper.addEventListener('drop', function (e) {
      var z = e.target.closest && e.target.closest('.imgdrop'); if (!z || dragId) return;
      e.preventDefault(); e.stopPropagation();
      var f = e.dataTransfer.files[0]; if (f) loadImage(z.closest('.blk').dataset.id, f);
    });
    // files dropped anywhere else
    window.addEventListener('dragover', function (e) { if (!dragId && e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) e.preventDefault(); });
    window.addEventListener('drop', function (e) {
      if (dragId || !e.dataTransfer || !e.dataTransfer.files.length) return;
      e.preventDefault(); importFile(e.dataTransfer.files[0]);
    });

    // block toolbar
    var bt = $('btools');
    bt.addEventListener('mousedown', function (e) { if (!/^(SELECT|INPUT|OPTION)$/.test(e.target.tagName)) e.preventDefault(); });
    bt.addEventListener('click', function (e) { var a = e.target.closest('button[data-act]'); if (a) toolAct(a.dataset.act, a); });
    bt.addEventListener('change', function (e) { var a = e.target.closest('[data-act]'); if (a) toolChange(a.dataset.act, a); });
    $('paperwrap').addEventListener('scroll', function () { placeTools(); $('linkTip').hidden = true; });
    window.addEventListener('resize', placeTools);

    // formatting toolbar
    $('fmt').addEventListener('mousedown', function (e) { if (e.target.closest('button')) e.preventDefault(); });
    $('fmt').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var c = b.dataset.cmd;
      if (b.dataset.pill) { $('pillMenu').hidden = true; return insertPill(b.dataset.pill, b.dataset.label); }
      if (!c) return;
      if (c === 'code') return toggleCode();
      if (c === 'link') return linkDialog();
      if (c === 'removeFormat') return clearFormat();
      if (c === 'pillMenu') { saveRange(); $('pillMenu').hidden = !$('pillMenu').hidden; return; }
      if (c === 'insert') {
        var r = b.getBoundingClientRect(), blk = SEL;
        return openInsert(r, blk || (DOC.blocks.length ? DOC.blocks[DOC.blocks.length - 1].id : null), '');
      }
      exec(c);
    });
    $('pillMenu').innerHTML = PILLS.map(function (p) { return '<button data-pill="' + p[0] + '" data-label="' + p[1] + '"><span style="background:' + ST.colours[p[0]] + '">' + p[1] + '</span></button>'; }).join('');

    // insert popover
    $('insSearch').addEventListener('input', function () { insSel = 0; fillInsert(this.value); });
    $('insSearch').addEventListener('keydown', function (e) { insertKeys(e); });
    $('insList').addEventListener('mousedown', function (e) { e.preventDefault(); });
    $('insList').addEventListener('click', function (e) { var b = e.target.closest('.ii'); if (b) chooseInsert(b.dataset.kind); });
    $('addEnd').addEventListener('click', function () { openInsert(this.getBoundingClientRect(), DOC.blocks.length ? DOC.blocks[DOC.blocks.length - 1].id : null, ''); });

    // link tip
    document.addEventListener('selectionchange', function () { debounce('tip', 120, updateLinkTip); });
    $('linkTip').addEventListener('mousedown', function (e) { e.preventDefault(); });
    $('linkTip').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var a = $('linkTip')._a; if (!a) return;
      if (b.dataset.tip === 'remove') { var r = a.closest('.rt'); a.outerHTML = esc(a.textContent); r.dispatchEvent(new Event('input', { bubbles: true })); $('linkTip').hidden = true; }
      else { var rr = document.createRange(); rr.selectNodeContents(a); var s = window.getSelection(); s.removeAllRanges(); s.addRange(rr); linkDialog(); }
    });

    // header
    $('bNew').onclick = function () {
      if (!hasContent()) { sideTab('tpl'); return toast('Pick a template on the left, or just start typing.'); }
      modal('Start a new page', '<p>Start from a template, or with a blank page?</p><p class="muted">Your current page is saved as a draft first, so you can open it again from <b>Open</b>.</p>',
        [['Cancel', null], ['Choose a template', function () { sideTab('tpl'); $('tplSearch').focus(); return true; }],
          ['Blank page', function () { saveDraft(true).then(blank, blank); return true; }, true]], true);
      function blank() { loadDoc({ title: '', summary: '', toc: true, categories: [], blocks: [] }); }
    };
    $('bOpen').onclick = function (e) { e.stopPropagation(); toggleOpen(); };
    $('openMenu').addEventListener('click', function (e) {
      var d = e.target.closest('[data-draft]'), a = e.target.closest('[data-act]');
      toggleOpen(false);
      if (d) return openDraft(d.dataset.draft);
      if (!a) return;
      var act = a.dataset.act;
      if (act === 'openFromWiki') openFromWiki();
      if (act === 'importWiki') pasteImport('wiki');
      if (act === 'importText') pasteImport('text');
      if (act === 'importWord') importWord();
      if (act === 'openFile') { var fi = $('fileIn'); fi.value = ''; fi.accept = '.json'; fi.onchange = function () { if (fi.files[0]) importFile(fi.files[0]); }; fi.click(); }
      if (act === 'checkOnly') checkOnly();
    });
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.menu')) { toggleOpen(false); $('pillMenu').hidden = true; }
      if (!$('insertPop').hidden && !e.target.closest('#insertPop') && !e.target.closest('[data-act="addBelow"]') && !e.target.closest('[data-cmd="insert"]') && !e.target.closest('#addEnd')) closeInsert();
    });
    $('bSave').onclick = function () { saveDraft(); };
    $('bUndo').onclick = undo; $('bRedo').onclick = redo;
    $('bExport').onclick = function () { openDrawer('code'); };
    $('bWiki').onclick = wikiMenu;
    $('bPublish').onclick = publishFlow;
    $('bCheck').onclick = function () { openDrawer('check'); };
    $('dClose').onclick = function () { $('drawer').hidden = true; setTimeout(placeTools, 30); };
    document.querySelectorAll('.dhead .tabs button').forEach(function (b) { b.onclick = function () { dtab(b.dataset.dtab); }; });
    $('dCopy').onclick = function () { copyText($('dText').value).then(function () { toast('Wiki code copied. Paste it into the wiki edit box.'); }, function () { $('dText').select(); toast('Press Ctrl+C to copy.'); }); };
    $('dDownload').onclick = function () { download(EXPORT.filename, $('dText').value); };
    $('dSaveTxt').onclick = function () { api('/api/save', { name: EXPORT.filename, text: $('dText').value }).then(function (r) { toast('Saved to ' + r.path); }).catch(function (e) { toast(e.message, true); }); };
    $('dIssues').addEventListener('click', function (e) { var d = e.target.closest('.issue'); if (d) goIssue($('dIssues')._items[+d.dataset.k]); });

    // side panel
    document.querySelectorAll('.side .tabs button').forEach(function (b) { b.onclick = function () { sideTab(b.dataset.tab); }; });
    $('tplSearch').addEventListener('input', renderTemplates);
    $('tplList').addEventListener('click', function (e) { var t = e.target.closest('[data-tpl]'); if (t) previewTemplate(t.dataset.tpl); });
    $('outline').addEventListener('click', function (e) { var a = e.target.closest('[data-go]'); if (a) focusBlock(a.dataset.go, 'end'); });
    $('pgSummary').addEventListener('input', function () { DOC.summary = this.value.replace(/\s+/g, ' ').trim() ? this.value : ''; renderPageBits(); debounce('typing', 700, commit); });
    $('pgToc').addEventListener('change', function () { commit(); DOC.toc = this.checked; commit(); });
    $('catPick').innerHTML = '<option value="">Add a category&hellip;</option>' + ST.categories.map(function (c) { return '<option>' + esc(c) + '</option>'; }).join('') + '<option value="@other">Another category&hellip;</option>';
    $('catPick').addEventListener('change', function () {
      var v = this.value; this.value = '';
      if (!v) return;
      if (v === '@other') {
        return modal('Another category', '<label for="catOther">Category name, exactly as on the wiki</label><input type="text" id="catOther"><div class="hint">The style guide asks us to use the existing categories. Check this one exists first.</div>',
          [['Cancel', null], ['Add', function () { var c = $('catOther').value.replace(/^\s*Category\s*:/i, '').trim(); if (c) addCat(c); return true; }, true]], true);
      }
      addCat(v);
    });
    $('catChips').addEventListener('click', function (e) { var b = e.target.closest('[data-delcat]'); if (b) { commit(); DOC.categories.splice(+b.dataset.delcat, 1); renderPageBits(); commit(); } });
    $('cats').addEventListener('click', function (e) { if (e.target.closest('[data-act="pageTab"]')) { sideTab('page'); } });
    $('crumb').addEventListener('click', function (e) { if (e.target.closest('[data-act="pageTab"]')) { sideTab('page'); $('pgSummary').focus(); } });

    // modal
    $('mClose').onclick = closeModal;
    $('modal').addEventListener('mousedown', function (e) { if (e.target === $('modal')) closeModal(); });
    $('modal').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && e.target.tagName === 'INPUT') { var p = $('mFoot').querySelector('.primary'); if (p) { e.preventDefault(); p.click(); } }
    });

    document.addEventListener('keydown', globalKeys, true);
    window.addEventListener('beforeunload', function () { lsSet('wst3.doc', JSON.stringify(DOC)); });
  }
  function addCat(c) { commit(); if (DOC.categories.indexOf(c) < 0) DOC.categories.push(c); renderPageBits(); commit(); }
  function toggleOpen(force) {
    var m = $('openMenu'), show = force === undefined ? m.hidden : force;
    m.hidden = !show;
    if (show) loadDrafts();
  }
  function insertKeys(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); insSel = Math.min(insItems.length - 1, insSel + 1); fillInsert($('insSearch').value); scrollIns(); return true; }
    if (e.key === 'ArrowUp') { e.preventDefault(); insSel = Math.max(0, insSel - 1); fillInsert($('insSearch').value); scrollIns(); return true; }
    if (e.key === 'Enter') { e.preventDefault(); if (insItems[insSel]) chooseInsert(insItems[insSel][1]); return true; }
    if (e.key === 'Escape') { e.preventDefault(); closeInsert(); return true; }
    return false;
  }
  function scrollIns() { var on = $('insList').querySelector('.ii.on'); if (on) on.scrollIntoView({ block: 'nearest' }); }

  function onKey(e) {
    var el = e.target.closest && e.target.closest('[data-f]');
    if (SLASH && !$('insertPop').hidden && /^(ArrowDown|ArrowUp|Enter|Escape)$/.test(e.key)) { insertKeys(e); return; }
    if (!el) return;
    var blk = el.closest('.blk'), b = blk && blockById(blk.dataset.id);
    var isRt = el.classList.contains('rt'), isPl = el.classList.contains('pl'), isTa = el.tagName === 'TEXTAREA';
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && b) {
      e.preventDefault();
      var kind = b.type === 'callout' ? b.kind : b.type === 'code' ? (b.lang === 'text' ? 'codetext' : 'code') : b.type;
      var nb = makeBlock(kind); if (b.color) nb.color = b.color;
      return insertAt(indexOf(b.id) + 1, [nb]);
    }
    if (isPl && (e.ctrlKey || e.metaKey) && /^[biu]$/i.test(e.key)) { e.preventDefault(); return; }
    if (e.key === 'Enter' && !e.shiftKey && (isPl || el.classList.contains('inline'))) {
      e.preventDefault();
      if (el.dataset.f === '@title') {
        if (DOC.blocks.length) focusBlock(DOC.blocks[0].id, 'start'); else insertKind('text', null);
        return;
      }
      if (b && (b.type === 'h2' || b.type === 'h3' || b.type === 'hero')) return insertKind('text', b.id);
      var fields = Array.prototype.slice.call(blk.querySelectorAll('[data-f]')), k = fields.indexOf(el);
      if (fields[k + 1]) focusAt(fields[k + 1], 'end');
      return;
    }
    if (isRt && el.classList.contains('cell')) {
      if (e.key === 'Tab') {
        e.preventDefault();
        var cells = Array.prototype.slice.call(blk.querySelectorAll('.rt.cell')), ci = cells.indexOf(el);
        if (e.shiftKey) { if (cells[ci - 1]) focusAt(cells[ci - 1], 'end'); return; }
        if (cells[ci + 1]) return focusAt(cells[ci + 1], 'end');
        commit(); b.rows.push(new Array(b.rows[0].length).fill('')); renderBlock(b.id); commit();
        var nc = document.querySelectorAll('.blk[data-id="' + b.id + '"] .rt.cell'); focusAt(nc[cells.length], 'start');
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.execCommand('insertLineBreak'); return; }
    }
    if (isTa && e.key === 'Tab' && b && b.type === 'code') {
      e.preventDefault(); var s = el.selectionStart; el.setRangeText('    ', s, el.selectionEnd, 'end'); el.dispatchEvent(new Event('input', { bubbles: true })); return;
    }
    if (e.key === 'Backspace' && isRt && b && b.type === 'text' && !el.textContent.trim() && !el.querySelector('li') && DOC.blocks.length > 1) {
      e.preventDefault();
      var i = indexOf(b.id); commit(); DOC.blocks.splice(i, 1); SEL = null; renderAll(false); commit();
      var prev = DOC.blocks[Math.max(0, i - 1)]; if (prev) focusBlock(prev.id, 'end');
    }
  }
  function globalKeys(e) {
    var mod = e.ctrlKey || e.metaKey, k = (e.key || '').toLowerCase();
    if (!$('modal').hidden) { if (e.key === 'Escape') { e.preventDefault(); closeModal(); } return; }
    if (e.key === 'Escape') {
      if (!$('insertPop').hidden) { closeInsert(); e.preventDefault(); return; }
      $('openMenu').hidden = true; $('pillMenu').hidden = true;
      return;
    }
    if (mod && k === 's') { e.preventDefault(); saveDraft(); return; }
    var inSearch = e.target.id === 'insSearch' || e.target.id === 'tplSearch' || e.target.id === 'pgSummary' || e.target.id === 'dText';
    if (mod && !inSearch && (k === 'z' || k === 'y')) {
      e.preventDefault();
      if (k === 'y' || (k === 'z' && e.shiftKey)) redo(); else undo();
      return;
    }
    if (mod && k === 'k') { if (activeRt()) { e.preventDefault(); linkDialog(); } return; }
    if (mod && k === 'e') { if (activeRt()) { e.preventDefault(); toggleCode(); } return; }
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && SEL) { e.preventDefault(); moveBlock(SEL, e.key === 'ArrowUp' ? -1 : 1); }
  }

  // ------------------------------------------------------------------ start up
  function boot() {
    Promise.all([api('/api/style'), api('/api/templates')]).then(function (r) {
      ST = r[0]; TPLS = r[1];
      $('verInfo').textContent = 'Version ' + ST.version + '. Runs on this computer; nothing is sent anywhere.';
      wire();
      renderTemplates();
      var saved = lsGet('wst3.doc'), doc = null;
      if (saved) { try { doc = JSON.parse(saved); } catch (e) { doc = null; } }
      DOC = sanitizeDoc(doc && Array.isArray(doc.blocks) ? doc : { title: '', summary: '', toc: true, categories: [], blocks: [] });
      DOC.categories = DOC.categories || [];
      LAST = JSON.stringify(DOC);
      renderAll();
      if (doc && (doc.title || doc.blocks.length)) { status('Restored your last page'); toast('Welcome back. Your last page is as you left it.'); }
      else { focusAt(document.querySelector('.ptitle'), 'end'); }
      refreshCheck();
      wikiRefresh();
    }).catch(function (e) {
      document.body.innerHTML = '<div style="padding:40px;font:16px sans-serif"><h2>The Wiki Style Tool could not start</h2><p>' + esc(e.message) +
        '</p><p>Start it with <b>run_wiki_style_tool.bat</b> (or <code>python wiki_style_tool.py</code>) and use the address it shows. Opening this file directly does not work.</p></div>';
    });
  }
  window.WST = { get doc() { return DOC; }, refresh: refreshCheck, render: function () { renderAll(); }, load: function (d) { loadDoc(d); } };
  boot();
})();
