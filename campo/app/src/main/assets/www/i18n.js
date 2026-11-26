/*
 * MonitorEO Campo: the language of the interface, Spanish (es, the text of the code) or English (en).
 *
 * The texts are written in Spanish in the code; en.js (window.CAMPO_EN) gives the English of each one, with the Spanish
 * text as key. t('¿Borrar "{0}"?', name) gives the text in the language chosen, with {0}, {1}… replaced by the values
 * after it; tr(message) translates a free message (an error of the phone or of a library) by its whole text or by the
 * patterns of window.CAMPO_EN_PATTERNS; translateDom() translates the texts and the attributes placeholder, title,
 * aria-label and alt of the static page (index.html). Changing the language reloads the page (setLang): the points,
 * the results and the settings are kept in the phone.
 *
 * The language is the one chosen last (localStorage 'campo.lang'), else Spanish if the phone is in Spanish, else
 * English.
 */
(function () {
  'use strict';

  var KEY = 'campo.lang';
  var lang = (function () {
    try {
      var v = localStorage.getItem(KEY);
      if (v === 'es' || v === 'en') return v;
    } catch (e) { /* no storage: the language of the phone */ }
    return String(navigator.language || 'es').toLowerCase().indexOf('es') === 0 ? 'es' : 'en';
  })();
  var missing = {};  // texts without English seen (for the tests: i18n.missing())

  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function dict() { return window.CAMPO_EN || {}; }

  function fill(s, args) {
    return args.length ? String(s).replace(/\{(\d+)\}/g, function (m, k) {
      return args[+k] !== undefined && args[+k] !== null ? String(args[+k]) : m;
    }) : s;
  }

  /** The text S (Spanish) in the language chosen, with {0}, {1}… replaced by the other arguments. */
  function t(s) {
    var args = Array.prototype.slice.call(arguments, 1);
    if (lang !== 'en') return fill(s, args);
    var d = dict();
    if (has(d, s)) return fill(d[s], args);
    missing[s] = true;
    return fill(s, args);
  }

  /** A free message (an error) in the language chosen: by its whole text, else by the first pattern that matches. */
  function tr(message) {
    var m = message === undefined || message === null ? '' : String(message);
    if (lang !== 'en' || !m) return m;
    var d = dict();
    if (has(d, m)) return d[m];
    var ps = window.CAMPO_EN_PATTERNS || [];
    for (var i = 0; i < ps.length; i++) if (ps[i][0].test(m)) return m.replace(ps[i][0], ps[i][1]);
    return m;
  }

  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];

  /** The texts of ROOT (the document by default) in the language chosen: whole texts of the dictionary only. */
  function translateDom(root) {
    if (lang !== 'en') return;
    root = root || document.body;
    var d = dict();
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = walker.nextNode())) {
      var p = n.parentNode;
      if (p && (p.nodeName === 'SCRIPT' || p.nodeName === 'STYLE' || p.closest && p.closest('[data-no-i18n]'))) continue;
      var raw = n.nodeValue, key = raw.trim().replace(/\s+/g, ' ');
      if (!key || !/[A-Za-zÁÉÍÓÚáéíóúñÑ]/.test(key)) continue;
      if (has(d, key)) n.nodeValue = raw.replace(/^(\s*)[\s\S]*?(\s*)$/, '$1' + d[key] + '$2');
      else missing[key] = true;
    }
    root.querySelectorAll('[' + ATTRS.join('],[') + ']').forEach(function (el) {
      ATTRS.forEach(function (a) {
        var v = el.getAttribute(a);
        if (!v || !/[A-Za-z]/.test(v)) return;
        if (has(d, v)) el.setAttribute(a, d[v]);
        else missing[v] = true;
      });
    });
    var title = document.title;
    if (has(d, title)) document.title = d[title];
  }

  function setLang(l) {
    if (l !== 'es' && l !== 'en') return;
    try { localStorage.setItem(KEY, l); } catch (e) { /* only this session */ }
    location.reload();
  }

  var locale = lang === 'en' ? 'en-GB' : 'es-ES';
  document.documentElement.lang = lang;

  window.i18n = {
    lang: lang,
    locale: locale,
    t: t,
    tr: tr,
    translateDom: translateDom,
    setLang: setLang,
    /** A number with the separators of the language (n.toLocaleString). */
    int: function (n) { return Number(n).toLocaleString(locale); },
    date: function (d) { return new Date(d).toLocaleDateString(locale); },
    dateTime: function (d) { return new Date(d).toLocaleString(locale); },
    missing: function () { return Object.keys(missing); }
  };
  window.t = t;

  // The page: its static texts, and the button that changes the language (it shows the other one).
  translateDom();
  var b = document.getElementById('btn-lang');
  if (b) {
    b.textContent = lang === 'en' ? 'ES' : 'EN';
    b.title = lang === 'en' ? 'Cambiar a español' : 'Switch to English';
    b.setAttribute('aria-label', b.title);
    b.onclick = function () { setLang(lang === 'en' ? 'es' : 'en'); };
  }
  // the native part (the buttons of its dialogs)
  if (window.Android) try { window.Android.call('lang', 'setLang', lang); } catch (e) { /* an older app */ }
})();
