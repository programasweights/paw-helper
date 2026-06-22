/* paw-helper embeddable widget (self-contained, framework-agnostic).
 *
 * Drop onto any site with:
 *   <script src="https://helper.yuntiandeng.com/widget.js"
 *           data-page="site:neuralos"></script>
 *
 * Config (script data-* attributes):
 *   data-endpoint  inference service base URL (default: this script's origin)
 *   data-page      page key sent to /ask so the router can apply a page prior
 *                  (default: "site")
 *
 * Renders into a Shadow DOM so the host page's CSS cannot break the widget and
 * the widget's CSS cannot leak into the host. Styling uses the host site's CSS
 * custom properties (--brand, --fg, ...) WHERE THEY EXIST (so it theme-adapts on
 * yuntiandeng.com) and falls back to sane defaults everywhere else. This is the
 * single, portable port of _includes/helper.html + js/helper.js + _sass/_helper.scss.
 */
(function () {
  'use strict';

  var thisScript = document.currentScript;
  if (!thisScript) {
    // Fallback: last script tag pointing at widget.js.
    var all = document.getElementsByTagName('script');
    for (var i = all.length - 1; i >= 0; i--) {
      if (/widget\.js(\?|$)/.test(all[i].src)) { thisScript = all[i]; break; }
    }
  }
  var ds = (thisScript && thisScript.dataset) || {};

  function scriptOrigin() {
    try { return new URL(thisScript.src).origin; } catch (e) { return ''; }
  }

  var ENDPOINT = (ds.endpoint || scriptOrigin() || '').replace(/\/$/, '');
  var PAGE = ds.page || 'site';
  // Optional labels/contact for a generic deployment. A content pack that ships
  // its own widget.js (served in place of this one) can hardcode richer copy.
  var NAME = ds.name || '';                       // e.g. data-name="Ada Lovelace"
  var EMAIL = ds.email || '';                     // e.g. data-email="ada@example.com"
  var ASK_LABEL = NAME ? ('Ask about ' + NAME) : 'Ask';

  if (document.getElementById('paw-helper-host')) return; // never double-inject

  // --- Styles (ported from _sass/_helper.scss; var(--x) -> var(--paw-x) with
  //     fallbacks defined on :host so it theme-adapts when the host defines them). ---
  var CSS = [
    ':host{',
    '  all: initial;',
    '  --paw-brand: var(--brand, #2563eb);',
    '  --paw-accent: var(--accent, #2563eb);',
    '  --paw-bg: var(--bg, #f1f5f9);',
    '  --paw-bg-elevated: var(--bg-elevated, #ffffff);',
    '  --paw-fg: var(--fg, #0f172a);',
    '  --paw-fg-muted: var(--fg-muted, #64748b);',
    '  --paw-border: var(--border, #e2e8f0);',
    '  --paw-shadow-md: var(--shadow-md, 0 4px 16px rgba(15,23,42,.12));',
    '  --paw-shadow-lg: var(--shadow-lg, 0 8px 24px rgba(15,23,42,.22));',
    '  font-family: inherit;',
    '}',
    // Dark fallbacks for FOREIGN sites that define none of the host CSS vars: when
    // the host defines --bg-elevated etc. (e.g. yuntiandeng.com) those always win,
    // so this only affects bare embeds under an OS dark preference (no impact on
    // the home site, which sets its own dark values via [data-theme="dark"]).
    '@media (prefers-color-scheme: dark){',
    '  :host{',
    '    --paw-bg: var(--bg, #0f172a);',
    '    --paw-bg-elevated: var(--bg-elevated, #1e293b);',
    '    --paw-fg: var(--fg, #e2e8f0);',
    '    --paw-fg-muted: var(--fg-muted, #94a3b8);',
    '    --paw-border: var(--border, #334155);',
    '  }',
    '}',
    '*, *::before, *::after { box-sizing: border-box; }',
    '.paw-helper__launch{',
    '  position: fixed;',
    '  bottom: max(1.5rem, env(safe-area-inset-bottom));',
    '  right: max(1.5rem, env(safe-area-inset-right));',
    '  z-index: 2147483000;',
    '  display: inline-flex; align-items: center; justify-content: center;',
    '  gap: 0.6rem; min-height: 52px; padding: 0.85rem 1.35rem;',
    '  border: none; border-radius: 999px;',
    '  background: var(--paw-brand); color: #fff;',
    '  font-family: inherit; font-weight: 600; font-size: 1rem; line-height: 1;',
    '  cursor: pointer; box-shadow: var(--paw-shadow-md);',
    '  transition: transform 0.15s ease, filter 0.15s ease, box-shadow 0.15s ease;',
    '  animation: paw-helper-attention 2.4s ease-in-out 1s 2;',
    '}',
    '.paw-helper__launch:hover{ transform: translateY(-2px); filter: brightness(1.08); box-shadow: var(--paw-shadow-lg); }',
    '.paw-helper__launch:focus-visible{ outline: 2px solid var(--paw-accent); outline-offset: 3px; }',
    '.paw-helper__launch svg{ width: 24px; height: 24px; flex: 0 0 auto; }',
    ':host-context([data-theme="dark"]) .paw-helper__launch{ color: #0f172a; }',
    '.paw-helper__overlay{ position: fixed; inset: 0; z-index: 2147483000; background: rgba(15,23,42,0.45); backdrop-filter: blur(2px); }',
    '.paw-helper__dialog{',
    '  position: fixed; z-index: 2147483001; top: 12vh; left: 50%;',
    '  transform: translateX(-50%); width: min(36rem, calc(100vw - 2rem));',
    '  background: var(--paw-bg-elevated); color: var(--paw-fg);',
    '  border: 1px solid var(--paw-border); border-radius: 12px;',
    '  box-shadow: var(--paw-shadow-md); overflow: hidden;',
    '  font-family: inherit; font-size: 1rem;',
    '}',
    '.paw-helper__bar{ display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0.75rem; border-bottom: 1px solid var(--paw-border); margin: 0; }',
    '.paw-helper__search{ color: var(--paw-fg-muted); flex: 0 0 auto; }',
    '.paw-helper__input{',
    '  flex: 1 1 auto; border: none; background: transparent; color: var(--paw-fg);',
    '  font-family: inherit; font-size: 1rem; padding: 0.85rem 0.25rem;',
    '}',
    '.paw-helper__input::placeholder{ color: var(--paw-fg-muted); }',
    '.paw-helper__input:focus{ outline: none; }',
    '.paw-helper__spinner{ flex: 0 0 auto; width: 16px; height: 16px; border: 2px solid var(--paw-border); border-top-color: var(--paw-brand); border-radius: 50%; animation: paw-helper-spin 0.7s linear infinite; }',
    '.paw-helper__close{ flex: 0 0 auto; display: inline-flex; padding: 0.4rem; border: none; background: transparent; color: var(--paw-fg-muted); cursor: pointer; border-radius: 6px; }',
    '.paw-helper__close:hover{ color: var(--paw-fg); background: var(--paw-bg); }',
    '.paw-helper__close:focus-visible{ outline: 2px solid var(--paw-accent); outline-offset: 1px; }',
    '.paw-helper__results{ max-height: 60vh; overflow-y: auto; }',
    '.paw-helper__placeholder{ margin: 0; padding: 1rem 1.1rem; color: var(--paw-fg-muted); font-size: 0.9rem; }',
    '.paw-helper__result{ display: block; padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--paw-border); }',
    '.paw-helper__result--link{ text-decoration: none; color: var(--paw-fg); transition: background 0.12s ease; }',
    '.paw-helper__result--link:hover{ background: var(--paw-bg); }',
    '.paw-helper__result-title{ display: block; font-weight: 600; color: var(--paw-brand); }',
    '.paw-helper__result-desc{ display: block; margin-top: 0.15rem; font-size: 0.85rem; color: var(--paw-fg-muted); }',
    '.paw-helper__answer-text{ margin: 0; line-height: 1.55; color: var(--paw-fg); }',
    '.paw-helper__answer-text a{ color: var(--paw-brand); text-decoration: underline; }',
    '.paw-helper__answer-text a:hover{ filter: brightness(1.1); }',
    '.paw-helper__result--none{ color: var(--paw-fg-muted); font-size: 0.92rem; }',
    '.paw-helper__result--none a{ color: var(--paw-brand); }',
    '.paw-helper__inline-btn{ border: none; background: none; padding: 0; font: inherit; color: var(--paw-brand); cursor: pointer; text-decoration: underline; }',
    '.paw-helper__feedback{ padding: 1rem 1.1rem; display: flex; flex-direction: column; gap: 0.6rem; }',
    '.paw-helper__textarea, .paw-helper__email{ width: 100%; box-sizing: border-box; border: 1px solid var(--paw-border); border-radius: 8px; background: var(--paw-bg); color: var(--paw-fg); font: inherit; padding: 0.6rem 0.7rem; }',
    '.paw-helper__textarea:focus, .paw-helper__email:focus{ outline: none; border-color: var(--paw-brand); }',
    '.paw-helper__textarea{ min-height: 5.5rem; resize: vertical; }',
    '.paw-helper__send{ align-self: flex-start; border: none; border-radius: 8px; background: var(--paw-brand); color: #fff; font: inherit; font-weight: 600; padding: 0.55rem 1rem; cursor: pointer; }',
    '.paw-helper__send:disabled{ opacity: 0.6; cursor: default; }',
    '.paw-helper__send:focus-visible{ outline: 2px solid var(--paw-accent); outline-offset: 2px; }',
    ':host-context([data-theme="dark"]) .paw-helper__send{ color: #0f172a; }',
    '.paw-helper__fb-status{ margin: 0; font-size: 0.85rem; color: var(--paw-fg-muted); }',
    '.paw-helper__footer{ display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 1.1rem; border-top: 1px solid var(--paw-border); font-size: 0.78rem; color: var(--paw-fg-muted); }',
    '.paw-helper__footer a{ color: var(--paw-fg-muted); text-decoration: underline; }',
    '.paw-helper__kbd{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.72rem; padding: 0.1rem 0.4rem; border: 1px solid var(--paw-border); border-radius: 4px; }',
    '@keyframes paw-helper-spin{ to { transform: rotate(360deg); } }',
    '@keyframes paw-helper-attention{ 0%,100%{ transform: translateY(0); box-shadow: var(--paw-shadow-md); } 50%{ transform: translateY(-3px); box-shadow: 0 10px 28px rgba(15,23,42,0.28); } }',
    '@media (prefers-reduced-motion: reduce){ .paw-helper__launch{ transition: none; animation: none; } .paw-helper__spinner{ animation-duration: 2s; } }',
    '@media (max-width: 600px){',
    '  .paw-helper__launch{ width: 56px; height: 56px; min-height: 0; padding: 0; border-radius: 50%; }',
    '  .paw-helper__launch-label{ display: none; }',
    '  .paw-helper__launch svg{ width: 26px; height: 26px; }',
    '  .paw-helper__dialog{ top: 0; left: 0; transform: none; width: 100vw; height: 100%; border-radius: 0; }',
    '  .paw-helper__results{ max-height: calc(100vh - 7rem); }',
    '}'
  ].join('\n');

  // --- Markup (ported from _includes/helper.html, Liquid removed). ---
  var HTML = [
    '<button type="button" class="paw-helper__launch" aria-label="Ask" aria-haspopup="dialog" aria-expanded="false">',
    '  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
    '    <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 17 0z"></path>',
    '  </svg>',
    '  <span class="paw-helper__launch-label">Ask</span>',
    '</button>',
    '<div class="paw-helper__overlay" hidden></div>',
    '<div class="paw-helper__dialog" role="dialog" aria-modal="true" aria-label="Ask" hidden>',
    '  <form class="paw-helper__bar" autocomplete="off">',
    '    <svg class="paw-helper__search" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
    '      <circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path>',
    '    </svg>',
    '    <input type="text" class="paw-helper__input" placeholder="Ask a question\u2026" aria-label="Ask">',
    '    <span class="paw-helper__spinner" hidden aria-hidden="true"></span>',
    '    <button type="button" class="paw-helper__close" aria-label="Close">',
    '      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"></path></svg>',
    '    </button>',
    '  </form>',
    '  <div class="paw-helper__results" aria-live="polite"></div>',
    '  <div class="paw-helper__footer">',
    '    <span>Powered by <span class="paw-helper__count">multiple</span> <a href="https://programasweights.com" target="_blank" rel="noopener" title="A pipeline of small ProgramAsWeights programs: a domain router, page classifiers, a topic router, specialized answerers, and a validator">ProgramAsWeights</a> programs</span>',
    '    <span class="paw-helper__kbd">esc</span>',
    '  </div>',
    '</div>'
  ].join('\n');

  function mount() {
    var host = document.createElement('div');
    host.id = 'paw-helper-host';
    var shadow = host.attachShadow({ mode: 'open' });
    var style = document.createElement('style');
    style.textContent = CSS;
    var root = document.createElement('div');
    root.className = 'paw-helper';
    root.innerHTML = HTML;
    shadow.appendChild(style);
    shadow.appendChild(root);
    document.body.appendChild(host);
    init(root);
  }

  // --- Behaviour (ported verbatim from js/helper.js; `root` is the shadow subtree). ---
  function init(root) {
    var launch = root.querySelector('.paw-helper__launch');
    var overlay = root.querySelector('.paw-helper__overlay');
    var dialog = root.querySelector('.paw-helper__dialog');
    var form = root.querySelector('.paw-helper__bar');
    var input = root.querySelector('.paw-helper__input');
    var spinner = root.querySelector('.paw-helper__spinner');
    var closeBtn = root.querySelector('.paw-helper__close');
    var results = root.querySelector('.paw-helper__results');

    var debounceTimer = null;
    var reqSeq = 0;

    function el(tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    }

    function setLoading(on) { if (spinner) spinner.hidden = !on; }

    var countEl = root.querySelector('.paw-helper__count');
    var countDone = false;
    function updateCount() {
      if (countDone || !countEl) return;
      countDone = true;
      fetch(ENDPOINT + '/health')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.n_serving) countEl.textContent = d.n_serving; })
        .catch(function () { countDone = false; });
    }

    function openDialog() {
      overlay.hidden = false;
      dialog.hidden = false;
      launch.setAttribute('aria-expanded', 'true');
      renderQuickLinks();
      updateCount();
      setTimeout(function () { input.focus(); }, 30);
    }

    function closeDialog() {
      overlay.hidden = true;
      dialog.hidden = true;
      launch.setAttribute('aria-expanded', 'false');
      input.value = '';
      results.innerHTML = '';
      if (debounceTimer) clearTimeout(debounceTimer);
      clearAskFromUrl();
      launch.focus();
    }

    function clearAskFromUrl() {
      var isAskHash = location.hash.replace(/^#/, '').toLowerCase() === 'ask';
      var params = new URLSearchParams(location.search);
      var hasAskParam = params.has('ask');
      if (!isAskHash && !hasAskParam) return;
      if (hasAskParam) params.delete('ask');
      var search = params.toString();
      history.replaceState(null, '',
        location.pathname + (search ? '?' + search : '') + (isAskHash ? '' : location.hash));
    }

    function renderQuickLinks() {
      results.innerHTML = '';
      var tip = NAME ? ('Ask anything about ' + NAME + '.') : 'Ask a question, or search for what you need.';
      results.appendChild(el('p', 'paw-helper__placeholder', tip));
    }

    function clearResults() { results.innerHTML = ''; }

    function renderLink(r) {
      clearResults();
      var a = el('a', 'paw-helper__result paw-helper__result--link');
      a.href = r.url;
      if (r.url.indexOf('mailto:') !== 0) { a.target = '_blank'; a.rel = 'noopener'; }
      a.appendChild(el('span', 'paw-helper__result-title', r.label));
      if (r.description) a.appendChild(el('span', 'paw-helper__result-desc', r.description));
      results.appendChild(a);
    }

    function renderLinks(r) {
      clearResults();
      var items = (r && r.items) || [];
      if (!items.length) return renderNone();
      if (r.label) results.appendChild(el('p', 'paw-helper__placeholder', r.label + ':'));
      items.forEach(function (it) {
        var a = el('a', 'paw-helper__result paw-helper__result--link');
        a.href = it.url; a.target = '_blank'; a.rel = 'noopener';
        a.appendChild(el('span', 'paw-helper__result-title', it.label));
        if (it.description) a.appendChild(el('span', 'paw-helper__result-desc', it.description));
        results.appendChild(a);
      });
    }

    function appendMarkdown(parent, text) {
      var re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g;
      var last = 0;
      var m;
      while ((m = re.exec(text)) !== null) {
        if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
        var a = document.createElement('a');
        a.href = m[2];
        a.textContent = m[1];
        if (m[2].indexOf('mailto:') !== 0) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
        parent.appendChild(a);
        last = re.lastIndex;
      }
      if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
    }

    function renderAnswer(r) {
      clearResults();
      var d = el('div', 'paw-helper__result paw-helper__result--answer');
      var p = el('p', 'paw-helper__answer-text');
      appendMarkdown(p, r.text || '');
      d.appendChild(p);
      results.appendChild(d);
    }

    function renderNone() {
      clearResults();
      var d = el('div', 'paw-helper__result paw-helper__result--none');
      d.appendChild(el('span', null, "I'm not sure about that. You can "));
      if (EMAIL) {
        var mail = el('a', null, 'email' + (NAME ? ' ' + NAME : ''));
        mail.href = 'mailto:' + EMAIL;
        d.appendChild(mail);
        d.appendChild(el('span', null, ' or '));
      }
      var fb = el('button', 'paw-helper__inline-btn', 'leave feedback');
      fb.type = 'button';
      fb.addEventListener('click', renderFeedbackForm);
      d.appendChild(fb);
      d.appendChild(el('span', null, '.'));
      results.appendChild(d);
    }

    function renderFeedbackForm() {
      clearResults();
      var wrap = el('div', 'paw-helper__feedback');
      var ta = el('textarea', 'paw-helper__textarea');
      ta.placeholder = 'Your message (anonymous). Bug reports, suggestions, and praise all welcome.';
      ta.maxLength = 2000;
      var email = el('input', 'paw-helper__email');
      email.type = 'email';
      email.placeholder = 'Email (optional, for a reply)';
      var send = el('button', 'paw-helper__send', 'Send feedback');
      send.type = 'button';
      var status = el('p', 'paw-helper__fb-status');
      send.addEventListener('click', function () {
        var text = ta.value.trim();
        if (!text) { ta.focus(); return; }
        send.disabled = true;
        status.textContent = 'Sending\u2026';
        fetch(ENDPOINT + '/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text, email: email.value.trim() || undefined, page_url: location.href })
        }).then(function (resp) {
          if (!resp.ok) throw new Error();
          status.textContent = 'Thank you for your feedback!';
          ta.value = ''; email.value = '';
        }).catch(function () {
          status.textContent = 'Could not send. Please try again later.';
          send.disabled = false;
        });
      });
      wrap.appendChild(ta);
      wrap.appendChild(email);
      wrap.appendChild(send);
      wrap.appendChild(status);
      results.appendChild(wrap);
      setTimeout(function () { ta.focus(); }, 30);
    }

    function render(r) {
      if (!r || r.type === 'none') return renderNone();
      if (r.type === 'link') return renderLink(r);
      if (r.type === 'links') return renderLinks(r);
      if (r.type === 'answer') return renderAnswer(r);
      if (r.type === 'feedback') return renderFeedbackForm();
      return renderNone();
    }

    function runQuery(q) {
      q = q.trim();
      if (q.length < 3) { renderQuickLinks(); return; }
      var seq = ++reqSeq;
      setLoading(true);
      fetch(ENDPOINT + '/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, page: PAGE })
      }).then(function (resp) {
        return resp.ok ? resp.json() : null;
      }).then(function (data) {
        if (seq !== reqSeq) return;
        setLoading(false);
        render(data);
      }).catch(function () {
        if (seq !== reqSeq) return;
        setLoading(false);
        renderNone();
      });
    }

    if (NAME) {
      input.placeholder = 'Ask about ' + NAME + '\u2026';
      input.setAttribute('aria-label', ASK_LABEL);
      launch.setAttribute('aria-label', ASK_LABEL);
      dialog.setAttribute('aria-label', ASK_LABEL);
    }

    launch.addEventListener('click', openDialog);
    closeBtn.addEventListener('click', closeDialog);
    overlay.addEventListener('click', closeDialog);

    input.addEventListener('input', function () {
      if (debounceTimer) clearTimeout(debounceTimer);
      var v = input.value;
      debounceTimer = setTimeout(function () { runQuery(v); }, 400);
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (debounceTimer) clearTimeout(debounceTimer);
      runQuery(input.value);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !dialog.hidden) closeDialog();
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (dialog.hidden) openDialog(); else closeDialog();
      }
    });

    function openFromUrl() {
      var raw = null;
      try { raw = new URLSearchParams(location.search).get('ask'); } catch (e) {}
      var hashAsk = location.hash.replace(/^#/, '').toLowerCase() === 'ask';
      if (raw === null && !hashAsk) return;
      if (dialog.hidden) openDialog();
      var q = (raw && raw !== '1' && raw.toLowerCase() !== 'true') ? raw : '';
      if (q) {
        input.value = q;
        runQuery(q);
      }
    }

    openFromUrl();
    window.addEventListener('hashchange', openFromUrl);
  }

  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();
