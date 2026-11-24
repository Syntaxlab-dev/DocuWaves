/*
 * DocuWaves search widget: the documentation's search on any other site.
 *
 *   <script src="https://docs.example.com/widget.js" data-project="handbook" async></script>
 *
 * The tag turns into a "Search the docs" button where it stands; the button,
 * or Ctrl/Cmd+K, opens a search box whose results link to the pages on this
 * instance. Optional attributes on the tag:
 *   data-project    a project slug: search only that project
 *   data-lang       a language code (e.g. "de"): search and link that language
 *   data-version    a documentation version of that project
 *   data-label      the button text           data-placeholder  the box hint
 *   data-accent     a CSS colour for highlights
 *   data-trigger    a CSS selector: those elements open the box instead of
 *                   a button of its own
 *   data-shortcut   "off" leaves Ctrl/Cmd+K to the host page
 *   data-new-tab    "off" opens results in the same tab
 *
 * Plain JavaScript in public/, not part of the bundle, so the address stays
 * the same from release to release. Everything is drawn inside a shadow root:
 * the host site's CSS can't reach in and this CSS can't leak out. Searches go
 * without cookies (credentials: "omit") and the server answers other sites
 * only as SEARCH_WIDGET_ORIGINS allows, so only what an anonymous reader may
 * see is ever shown. Results are written with textContent, never as HTML.
 */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || !script.src) return;
  var base = new URL(script.src).origin;
  var opt = function (name, fallback) {
    var v = script.getAttribute("data-" + name);
    return v === null || v === "" ? fallback : v;
  };
  var project = opt("project", "");
  var lang = opt("lang", "");
  var version = opt("version", "");
  var german = (lang || document.documentElement.lang || navigator.language || "").toLowerCase().indexOf("de") === 0;
  var text = german
    ? { label: "Doku durchsuchen", placeholder: "Suchbegriff …", none: "Nichts gefunden.", failed: "Die Suche ist gerade nicht erreichbar.", close: "Schließen", corrected: "Ergebnisse für" }
    : { label: "Search the docs", placeholder: "Search …", none: "Nothing found.", failed: "Search is not reachable right now.", close: "Close", corrected: "Showing results for" };
  var label = opt("label", text.label);
  var accent = opt("accent", "#2563eb");
  var newTab = opt("new-tab", "on") !== "off";

  var css =
    ":host{all:initial}" +
    "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}" +
    ".btn{display:inline-flex;align-items:center;gap:.5em;padding:.45em .8em;border:1px solid #d0d5dd;border-radius:8px;background:#fff;color:#344054;font-size:14px;cursor:pointer}" +
    ".btn:hover{border-color:var(--a)}.btn:focus-visible{outline:2px solid var(--a);outline-offset:2px}" +
    ".btn kbd{font:11px ui-monospace,monospace;padding:1px 5px;border:1px solid #d0d5dd;border-radius:4px;color:#667085}" +
    ".back{position:fixed;inset:0;z-index:2147483646;background:rgba(15,23,42,.45);display:flex;justify-content:center;align-items:flex-start;padding:10vh 16px 16px}" +
    ".box{width:100%;max-width:640px;max-height:75vh;display:flex;flex-direction:column;background:#fff;color:#101828;border-radius:12px;box-shadow:0 20px 50px rgba(0,0,0,.3);overflow:hidden}" +
    ".head{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid #eaecf0}" +
    "input{flex:1;border:0;outline:0;font-size:17px;background:transparent;color:inherit;min-width:0}" +
    ".x{border:0;background:none;font-size:13px;color:#667085;cursor:pointer;padding:4px 6px;border-radius:6px}.x:hover{background:#f2f4f7}" +
    "ul{list-style:none;margin:0;padding:6px;overflow-y:auto}" +
    "a{display:block;padding:10px 12px;border-radius:8px;color:inherit;text-decoration:none}" +
    "a[aria-selected=true],a:hover{background:color-mix(in srgb,var(--a) 10%,transparent)}" +
    ".t{font-weight:600;font-size:15px}.p{font-size:12px;color:#667085;margin-top:2px}.s{font-size:13px;color:#475467;margin-top:4px;line-height:1.45}" +
    ".msg{padding:16px;font-size:14px;color:#667085}" +
    ".foot{padding:8px 14px;border-top:1px solid #eaecf0;font-size:11px;color:#98a2b3;text-align:right}.foot a{display:inline;padding:0;color:#667085}" +
    "@media (prefers-color-scheme:dark){.btn{background:#1d2939;color:#e4e7ec;border-color:#475467}.box{background:#101828;color:#f2f4f7}.head,.foot{border-color:#344054}.p,.msg{color:#98a2b3}.s{color:#d0d5dd}.x:hover{background:#1d2939}}";

  var host = document.createElement("span");
  host.className = "docuwaves-search";
  var root = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = css;
  root.appendChild(style);
  host.style.setProperty("--a", accent);

  var el = function (tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt) n.textContent = txt;
    return n;
  };

  var trigger = opt("trigger", "");
  if (!trigger) {
    var btn = el("button", "btn");
    btn.type = "button";
    btn.style.setProperty("--a", accent);
    btn.appendChild(document.createTextNode(label + " "));
    if (opt("shortcut", "on") !== "off") btn.appendChild(el("kbd", "", /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘K" : "Ctrl K"));
    btn.addEventListener("click", function () { open(); });
    root.appendChild(btn);
  }
  script.parentNode.insertBefore(host, script);
  if (trigger) {
    document.addEventListener("click", function (e) {
      var t = e.target && e.target.closest ? e.target.closest(trigger) : null;
      if (t) { e.preventDefault(); open(); }
    });
  }

  var back, input, list, status, results = [], active = -1, timer = 0, seq = 0, lastFocus = null;

  function pageUrl(r) {
    var v = project && version && r.project_slug === project ? "/" + encodeURIComponent(r.version || version) : "";
    return base + (lang ? "/" + encodeURIComponent(lang) : "") + "/p/" + encodeURIComponent(r.project_slug) + v + "/pages/" + encodeURIComponent(r.page_slug);
  }

  function build() {
    back = el("div", "back");
    back.style.setProperty("--a", accent);
    back.addEventListener("mousedown", function (e) { if (e.target === back) close(); });
    var box = el("div", "box");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", label);
    var head = el("div", "head");
    input = el("input");
    input.type = "search";
    input.placeholder = opt("placeholder", text.placeholder);
    input.setAttribute("aria-label", label);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-controls", "dw-results");
    input.setAttribute("aria-expanded", "true");
    input.setAttribute("autocomplete", "off");
    var x = el("button", "x", "Esc");
    x.type = "button";
    x.setAttribute("aria-label", text.close);
    x.addEventListener("click", close);
    head.appendChild(input);
    head.appendChild(x);
    list = el("ul");
    list.id = "dw-results";
    list.setAttribute("role", "listbox");
    status = el("div", "msg");
    status.setAttribute("aria-live", "polite");
    var foot = el("div", "foot");
    var by = el("a", "", "DocuWaves");
    by.href = base + "/";
    by.target = "_blank";
    by.rel = "noopener";
    foot.appendChild(by);
    box.appendChild(head);
    box.appendChild(status);
    box.appendChild(list);
    box.appendChild(foot);
    back.appendChild(box);
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(search, 180);
    });
    input.addEventListener("keydown", keys);
    back.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
    });
  }

  function keys(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!results.length) return;
      select((active + (e.key === "ArrowDown" ? 1 : results.length - 1)) % results.length);
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      list.children[active].firstChild.click();
    }
  }

  function select(i) {
    active = i;
    for (var n = 0; n < list.children.length; n++) {
      var a = list.children[n].firstChild;
      a.setAttribute("aria-selected", n === i ? "true" : "false");
      if (n === i) { a.scrollIntoView({ block: "nearest" }); input.setAttribute("aria-activedescendant", a.id); }
    }
  }

  function render(data) {
    results = data.results || [];
    list.textContent = "";
    active = -1;
    status.textContent = data.corrected ? text.corrected + " „" + data.corrected + "“" : results.length ? "" : text.none;
    status.style.display = status.textContent ? "" : "none";
    results.slice(0, 20).forEach(function (r, i) {
      var li = el("li");
      li.setAttribute("role", "presentation");
      var a = el("a");
      a.id = "dw-r" + i;
      a.setAttribute("role", "option");
      a.href = pageUrl(r);
      if (newTab) { a.target = "_blank"; a.rel = "noopener"; }
      a.appendChild(el("div", "t", r.title));
      a.appendChild(el("div", "p", [r.project_name, r.category_name].filter(Boolean).join(" › ")));
      if (r.snippet) a.appendChild(el("div", "s", r.snippet));
      li.appendChild(a);
      list.appendChild(li);
    });
  }

  function search() {
    var q = input.value.trim();
    var mine = ++seq;
    if (!q) { list.textContent = ""; results = []; status.style.display = "none"; return; }
    var params = new URLSearchParams({ q: q.slice(0, 200) });
    if (project) params.set("project", project);
    if (lang) params.set("lang", lang);
    if (version) params.set("version", version);
    fetch(base + "/api/public/search?" + params.toString(), { credentials: "omit" })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (data) { if (mine === seq) render(data); })
      .catch(function () {
        if (mine !== seq) return;
        list.textContent = "";
        results = [];
        status.textContent = text.failed;
        status.style.display = "";
      });
  }

  function open() {
    if (!back) build();
    if (back.isConnected) return;
    lastFocus = document.activeElement;
    status.style.display = "none";
    root.appendChild(back);
    input.focus();
    input.select();
  }

  function close() {
    if (back && back.isConnected) root.removeChild(back);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  if (opt("shortcut", "on") !== "off") {
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        open();
      }
    });
  }

  window.DocuWavesSearch = { open: open, close: close };
})();
