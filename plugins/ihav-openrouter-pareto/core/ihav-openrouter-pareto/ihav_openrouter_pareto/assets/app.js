(function () {
  'use strict';
  // Python precomputed every view and frontier; this script only selects a view and draws it.
  var DATA = JSON.parse(document.getElementById('report-data').textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var ORIGIN = 'https://openrouter.ai/';
  var W = 960, H = 540, M = { l: 72, r: 24, t: 16, b: 56 }, ZERO_BAND = 48;
  var state = { mod: null, metric: null, basis: null, scope: null };

  function $(id) { return document.getElementById(id); }
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function sv(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = text;
    return e;
  }
  function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); }
  function byId(list, id) { return list.filter(function (x) { return x.id === id; })[0]; }
  function clip(s, n) { var a = Array.from(s); return a.length > n ? a.slice(0, n - 1).join('') + '…' : s; }
  function modelHref(id) { return ORIGIN + id.split('/').map(encodeURIComponent).join('/'); }
  function compact(v) {
    var units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
    for (var i = 0; i < units.length; i++) if (Math.abs(v) >= units[i][0]) return +(v / units[i][0]).toPrecision(3) + units[i][1];
    return String(+v.toPrecision(4));
  }

  function scale(values, from, to, log) {
    var f = log ? Math.log10 : function (v) { return v; };
    var used = values.filter(function (v) { return !log || v > 0; }).map(f);
    var lo = used.length ? Math.min.apply(null, used) : 0, hi = used.length ? Math.max.apply(null, used) : 1;
    var pad = hi > lo ? (hi - lo) * 0.06 : (log ? 0.5 : Math.abs(lo) * 0.05 || 1);
    lo -= pad; hi += pad;
    var ticks = [];
    if (log) {
      for (var p = Math.ceil(lo); p <= Math.floor(hi); p++) ticks.push(Math.pow(10, p));
      if (ticks.length < 3) [2, 5].forEach(function (m) {
        for (var q = Math.floor(lo); q <= Math.ceil(hi); q++) { var t = m * Math.pow(10, q); if (Math.log10(t) >= lo && Math.log10(t) <= hi) ticks.push(t); }
      });
    } else {
      var raw = (hi - lo) / 6, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map(function (k) { return k * mag; }).filter(function (s) { return s >= raw; })[0];
      for (var v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(+v.toPrecision(12));
    }
    return { ticks: ticks, map: function (v) { var t = log && v <= 0 ? lo : f(v); return from + (t - lo) / (hi - lo) * (to - from); } };
  }

  function header() {
    $('meta').textContent = 'Capture ' + DATA.capture_id + ' (captured ' + DATA.captured_at + ', built ' + DATA.generated_at + ', plugin ' + DATA.version + '). Tables: ' +
      (Object.keys(DATA.tables).map(function (m) { var t = DATA.tables[m]; return m + ' ' + t.rows_read + '/' + t.expected_rows + ' rows at ' + t.captured_at; }).join('; ') || 'none (API-only)') +
      '. Typed endpoint prices: ' + DATA.endpoints.ok + ' ok, ' + DATA.endpoints.failed + ' failed.';
    DATA.blocking.concat(DATA.warnings).forEach(function (w) { $('alerts').appendChild(el('li', w)); });
    DATA.notes.forEach(function (n) { $('global-notes').appendChild(el('li', n)); });
    DATA.modalities.forEach(function (mod, i) {
      var b = el('button', mod.label);
      b.setAttribute('role', 'tab');
      b.addEventListener('click', function () { selectModality(i); });
      $('tabs').appendChild(b);
    });
  }

  function fill(select, items, current, label, disabledReason) {
    clear(select);
    items.forEach(function (it) {
      var o = el('option', label(it));
      o.value = it.id || it;
      var reason = disabledReason(it);
      if (reason) { o.disabled = true; o.title = reason; o.textContent += ' (' + reason + ')'; }
      select.appendChild(o);
    });
    select.value = current;
  }

  function selectModality(i) {
    state.mod = DATA.modalities[i];
    Array.prototype.forEach.call($('tabs').children, function (b, k) { b.setAttribute('aria-selected', String(k === i)); });
    var d = state.mod.default || {};
    state.metric = d.metric; state.basis = d.basis; state.scope = d.scope || 'all';
    fill($('metric'), state.mod.metrics, state.metric, function (m) { return m.label; },
      function (m) { return m.status !== 'ok' ? m.reason : (!m.axis ? m.reason : null); });
    fill($('basis'), state.mod.bases, state.basis, function (b) { return b.label; }, function () { return null; });
    fill($('scope'), state.mod.scopes, state.scope, function (s) { return s; }, function () { return null; });
    var list = $('excluded').querySelector('ul');
    clear(list);
    state.mod.offers.forEach(function (o) { if (o.excluded) list.appendChild(el('li', o.id + ': ' + o.excluded + ', ' + o.detail)); });
    draw();
  }

  function draw() {
    var mod = state.mod, view = mod.views[state.metric + '|' + state.basis + '|' + state.scope];
    clear($('notes')); clear($('chart')); clear($('points').tBodies[0]); $('tip').hidden = true;
    if (!view) {
      $('title').textContent = mod.label + ': no chart';
      $('counts').textContent = mod.bases.length ? 'No chartable metric has values in this tab.' : 'No price with a known unit in this tab.';
      return;
    }
    var metric = byId(mod.metrics, state.metric), basis = byId(mod.bases, state.basis);
    $('title').textContent = metric.title + ' (' + basis.label + '; offers: ' + state.scope + ')';
    $('counts').textContent = view.valid.length + ' valid / ' + view.total + ' total. Excluded: ' +
      (Object.keys(view.excluded).map(function (r) { return r.replace(/_/g, ' ') + ' ' + view.excluded[r]; }).join(', ') || 'none') + '.';
    view.notes.forEach(function (n) { $('notes').appendChild(el('li', n)); });
    var pts = view.valid.map(function (i) { var o = mod.offers[i]; return { i: i, o: o, p: o.p[basis.id], m: o.m[metric.id] }; });
    chart(view, pts, metric, basis);
    table(view, pts, metric);
  }

  function chart(view, pts, metric, basis) {
    var svg = $('chart');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    if (!pts.length) { svg.appendChild(sv('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', 'class': 'empty' }, 'No offer has this metric and this price in this scope.')); return; }
    var zero = pts.some(function (p) { return p.p.x === 0; });
    var left = M.l + (zero ? ZERO_BAND : 0), right = W - M.r, bottom = H - M.b;
    var X = scale(pts.map(function (p) { return p.p.x; }), left, right, true);
    var Y = scale(pts.map(function (p) { return p.m.y; }), bottom, M.t, metric.scale === 'log');
    var px = function (x) { return x > 0 ? X.map(x) : M.l + ZERO_BAND / 2 - 4; };
    if (zero) {
      svg.appendChild(sv('rect', { x: M.l, y: M.t, width: ZERO_BAND - 8, height: bottom - M.t, 'class': 'band' }));
      svg.appendChild(sv('text', { x: M.l + ZERO_BAND / 2 - 4, y: bottom + 16, 'text-anchor': 'middle' }, '$0'));
    }
    X.ticks.forEach(function (t) {
      var x = X.map(t);
      svg.appendChild(sv('line', { x1: x, x2: x, y1: M.t, y2: bottom, 'class': 'grid' }));
      svg.appendChild(sv('text', { x: x, y: bottom + 16, 'text-anchor': 'middle' }, '$' + compact(t)));
    });
    Y.ticks.forEach(function (t) {
      var y = Y.map(t);
      svg.appendChild(sv('line', { x1: M.l, x2: right, y1: y, y2: y, 'class': 'grid' }));
      svg.appendChild(sv('text', { x: M.l - 6, y: y + 4, 'text-anchor': 'end' }, compact(t)));
    });
    svg.appendChild(sv('line', { x1: M.l, x2: right, y1: bottom, y2: bottom, 'class': 'axis' }));
    svg.appendChild(sv('line', { x1: M.l, x2: M.l, y1: M.t, y2: bottom, 'class': 'axis' }));
    svg.appendChild(sv('text', { x: (left + right) / 2, y: H - 12, 'text-anchor': 'middle' }, basis.label + ', log scale'));
    svg.appendChild(sv('text', { x: 14, y: (M.t + bottom) / 2, 'text-anchor': 'middle', transform: 'rotate(-90 14 ' + (M.t + bottom) / 2 + ')' },
      metric.label + (metric.scale === 'log' ? ', log scale' : '')));

    var front = {}, groups = {}, order = [];
    view.frontier.forEach(function (i) { front[i] = true; });
    pts.forEach(function (p) {
      var key = p.p.v + '|' + p.m.v;
      if (!groups[key]) { groups[key] = []; order.push(key); }
      groups[key].push(p);
    });
    var vertices = [];
    view.frontier.forEach(function (i) {
      var p = pts.filter(function (q) { return q.i === i; })[0], last = vertices[vertices.length - 1];
      if (!last || last.p.v !== p.p.v || last.m.v !== p.m.v) vertices.push(p);
    });
    if (vertices.length) {
      var d = 'M' + px(vertices[0].p.x) + ' ' + Y.map(vertices[0].m.y);
      vertices.slice(1).forEach(function (v) { d += ' H' + px(v.p.x) + ' V' + Y.map(v.m.y); });
      svg.appendChild(sv('path', { d: d + ' H' + right, 'class': 'frontier' }));
    }
    order.forEach(function (key) {
      var g = groups[key], first = g[0], cx = px(first.p.x), cy = Y.map(first.m.y);
      var onFront = g.some(function (p) { return front[p.i]; });
      var cls = 'pt v-' + first.o.variant + (onFront ? ' front' : '') + (first.p.fc ? ' hollow' : '');
      var r = onFront ? 6 : 4.5, mark;
      if (first.p.lb) mark = sv('polygon', { points: [cx, cy - r - 1, cx + r + 1, cy, cx, cy + r + 1, cx - r - 1, cy].join(' '), 'class': cls });
      else if (first.p.x === 0) mark = sv('rect', { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, 'class': cls });
      else mark = sv('circle', { cx: cx, cy: cy, r: r, 'class': cls });
      mark.setAttribute('tabindex', '0');
      mark.setAttribute('aria-label', g.map(function (p) { return p.o.name; }).join(', ') + ': ' + first.p.d + ', ' + first.m.d);
      mark.addEventListener('mouseenter', function () { tip(g, cx, cy, front, metric, basis); });
      mark.addEventListener('focus', function () { tip(g, cx, cy, front, metric, basis); });
      mark.addEventListener('mouseleave', function () { $('tip').hidden = true; });
      mark.addEventListener('blur', function () { $('tip').hidden = true; });
      svg.appendChild(mark);
      if (onFront) svg.appendChild(sv('text', { x: cx + 8, y: cy - 8, 'class': 'label' }, clip(first.o.name, 28) + (g.length > 1 ? ' +' + (g.length - 1) : '')));
    });
  }

  function tip(group, cx, cy, front, metric, basis) {
    var box = $('tip'), ratio = $('chart').getBoundingClientRect().width / W;
    clear(box);
    group.forEach(function (p) {
      var div = el('div', null, 'offer');
      div.appendChild(el('b', p.o.name));
      div.appendChild(el('div', p.o.id + ' · ' + p.o.variant + (front[p.i] ? ' · on the frontier' : '')));
      div.appendChild(el('div', 'Price: ' + p.p.d + ' (' + basis.label + ', ' + p.p.q + (p.p.lb ? ', lower bound' : '') + ', source ' + p.p.s + ')'));
      if (p.p.dp) div.appendChild(el('div', 'Displayed with ' + p.p.dp + '% off; not applied again'));
      if (p.o.free) div.appendChild(el('div', 'Free offer: every price is 0'));
      else if (p.p.fc) div.appendChild(el('div', 'This price is 0; other prices of the offer are not'));
      div.appendChild(el('div', metric.label + ': ' + p.m.d));
      box.appendChild(div);
    });
    box.hidden = false;
    box.style.left = Math.min(cx * ratio + 12, Math.max(0, $('chart-wrap').clientWidth - box.offsetWidth)) + 'px';
    box.style.top = Math.max(0, cy * ratio - 10) + 'px';
  }

  function table(view, pts, metric) {
    var body = $('points').tBodies[0], front = {};
    view.frontier.forEach(function (i) { front[i] = true; });
    pts.forEach(function (p, k) {
      var tr = el('tr', null, front[p.i] ? 'front' : null), name = el('td');
      if (p.o.match !== 'unmatched') {
        var a = el('a', p.o.name);
        a.href = modelHref(p.o.id); a.rel = 'noopener noreferrer'; a.target = '_blank';
        name.appendChild(a);
      } else name.appendChild(document.createTextNode(p.o.name));
      name.appendChild(el('small', p.o.id));
      tr.appendChild(el('td', String(k + 1), 'num'));
      tr.appendChild(name);
      tr.appendChild(el('td', p.o.variant + (p.o.free ? ', free' : '')));
      tr.appendChild(el('td', p.p.d + (p.p.lb ? ' (lower bound)' : '') + (p.p.fc ? ' (0 in a paid offer)' : ''), 'num'));
      tr.appendChild(el('td', p.m.d, 'num'));
      tr.appendChild(el('td', front[p.i] ? 'frontier' : ''));
      tr.appendChild(el('td', p.p.s + ' · ' + p.p.col));
      body.appendChild(tr);
    });
  }

  ['metric', 'basis', 'scope'].forEach(function (k) {
    $(k).addEventListener('change', function (e) { state[k] = e.target.value; draw(); });
  });
  header();
  if (DATA.modalities.length) selectModality(0);
})();
