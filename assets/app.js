(function () {
  'use strict';

  var DATA = window.KDQ || { subjects: [], blocks: [], questions: [] };
  var SUBJECTS = DATA.subjects;
  var ALL = DATA.questions;
  var SUBJECT_BY_ID = {};
  SUBJECTS.forEach(function (s) { SUBJECT_BY_ID[s.id] = s; });

  var LS_KEY = 'kdq.filter.v1';

  // --- session state (resets on every load; that is the point) ---
  var score = { correct: 0, total: 0, streak: 0, best: 0 };
  var wrongPool = [];   // ids answered wrong this session, re-queued
  var recent = [];      // ids shown recently, to avoid immediate repeats
  var enabled = {};     // subjectId -> bool
  var opts = { wrongFirst: true, shuffleChoices: true, src: 'all' };
  var current = null;   // { q, order }
  var answered = false;

  var $ = function (id) { return document.getElementById(id); };

  // ---------- filter persistence ----------
  function loadFilter() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { saved = null; }
    SUBJECTS.forEach(function (s) {
      enabled[s.id] = saved && saved.enabled ? saved.enabled.indexOf(s.id) >= 0 : true;
    });
    if (saved && saved.opts) {
      if (typeof saved.opts.wrongFirst === 'boolean') opts.wrongFirst = saved.opts.wrongFirst;
      if (typeof saved.opts.shuffleChoices === 'boolean') opts.shuffleChoices = saved.opts.shuffleChoices;
      if (typeof saved.opts.src === 'string') opts.src = saved.opts.src;
    }
  }
  function saveFilter() {
    var on = SUBJECTS.filter(function (s) { return enabled[s.id]; }).map(function (s) { return s.id; });
    try { localStorage.setItem(LS_KEY, JSON.stringify({ enabled: on, opts: opts })); } catch (e) { /* ignore */ }
  }

  // ---------- pool ----------
  function isExam(q) { return /^令和/.test(q.tag || ''); }

  function pool() {
    return ALL.filter(function (q) {
      if (!enabled[q.subject]) return false;
      if (opts.src === 'exam') return isExam(q);
      if (opts.src === 'base') return !isExam(q);
      return true;
    });
  }
  function countBySubject(id) {
    var n = 0;
    for (var i = 0; i < ALL.length; i++) if (ALL[i].subject === id) n++;
    return n;
  }

  function pick() {
    var p = pool();
    if (!p.length) return null;

    // 1/3 of the time, replay something missed earlier this session
    if (opts.wrongFirst && wrongPool.length && Math.random() < 0.34) {
      var wp = wrongPool.filter(function (id) { return enabled[byId(id).subject]; });
      if (wp.length) {
        var wid = wp[(Math.random() * wp.length) | 0];
        return byId(wid);
      }
    }
    var avoid = Math.min(recent.length, Math.max(0, Math.floor(p.length * 0.5)));
    var skip = recent.slice(recent.length - avoid);
    var fresh = p.filter(function (q) { return skip.indexOf(q.id) < 0; });
    var src = fresh.length ? fresh : p;
    return src[(Math.random() * src.length) | 0];
  }

  var BY_ID = {};
  ALL.forEach(function (q) { BY_ID[q.id] = q; });
  function byId(id) { return BY_ID[id]; }

  function shuffled(n) {
    var a = [];
    for (var i = 0; i < n; i++) a.push(i);
    for (var j = a.length - 1; j > 0; j--) {
      var k = (Math.random() * (j + 1)) | 0;
      var t = a[j]; a[j] = a[k]; a[k] = t;
    }
    return a;
  }

  // ---------- render ----------
  function renderHud() {
    $('hudCorrect').textContent = score.correct;
    $('hudTotal').textContent = score.total;
    $('hudRate').textContent = score.total ? Math.round(score.correct / score.total * 100) + '%' : '—';
    $('hudStreak').textContent = score.streak >= 2 ? '連続' + score.streak : '';
    var missed = score.total - score.correct;
    $('footStats').textContent = score.total
      ? '誤答 ' + missed + ' 問 / 最長連続 ' + score.best + ' / 要復習 ' + wrongPool.length + ' 問'
      : '';
  }

  function renderQuestion() {
    var q = pick();
    if (!q) {
      $('quiz').hidden = true;
      $('empty').hidden = false;
      return;
    }
    $('quiz').hidden = false;
    $('empty').hidden = true;

    var order = opts.shuffleChoices
      ? shuffled(q.choices.length)
      : q.choices.map(function (_, i) { return i; });
    current = { q: q, order: order };
    answered = false;

    recent.push(q.id);
    if (recent.length > 400) recent.shift();

    var s = SUBJECT_BY_ID[q.subject];
    $('qsubject').textContent = (s ? s.name : q.subject) + (s && s.points === 20 ? '（20点科目）' : '');
    $('qsrc').textContent = isExam(q) ? q.tag + ' 本試験' : '条文ベース';
    $('qtext').textContent = q.q;

    var ol = $('choices');
    ol.innerHTML = '';
    order.forEach(function (origIdx, pos) {
      var li = document.createElement('li');
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.pos = String(pos);
      var num = document.createElement('span');
      num.className = 'num';
      num.textContent = (pos + 1) + '.';
      var txt = document.createElement('span');
      txt.textContent = q.choices[origIdx];
      b.appendChild(num);
      b.appendChild(txt);
      b.addEventListener('click', function () { answer(pos); });
      li.appendChild(b);
      ol.appendChild(li);
    });

    $('verdict').hidden = true;
    $('verdictLine').className = '';
    window.scrollTo(0, 0);
  }

  function answer(pos) {
    if (answered || !current) return;
    answered = true;
    var q = current.q;
    var chosenOrig = current.order[pos];
    var ok = chosenOrig === q.answer;
    var correctPos = current.order.indexOf(q.answer);

    score.total++;
    if (ok) {
      score.correct++;
      score.streak++;
      if (score.streak > score.best) score.best = score.streak;
      var wi = wrongPool.indexOf(q.id);
      if (wi >= 0) wrongPool.splice(wi, 1); // cleared on a later correct answer
    } else {
      score.streak = 0;
      if (wrongPool.indexOf(q.id) < 0) wrongPool.push(q.id);
    }

    var btns = $('choices').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    if (btns[correctPos]) btns[correctPos].classList.add('is-correct');
    if (!ok && btns[pos]) btns[pos].classList.add('is-wrong');

    var vl = $('verdictLine');
    vl.textContent = ok ? '正解' : '不正解 — 正答は ' + (correctPos + 1);
    vl.className = ok ? 'ok' : 'ng';
    $('explain').textContent = q.explain || '';
    $('ref').textContent = q.ref ? '根拠: ' + q.ref : '';
    $('verdict').hidden = false;

    renderHud();
    $('btnNext').focus();
  }

  function next() {
    if (!answered) return;
    renderQuestion();
  }

  function resetScore() {
    score = { correct: 0, total: 0, streak: 0, best: 0 };
    wrongPool = [];
    recent = [];
    renderHud();
    renderQuestion();
  }

  // ---------- filter UI ----------
  function renderFilter() {
    var list = $('subjectList');
    list.innerHTML = '';
    SUBJECTS.forEach(function (s) {
      var label = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!enabled[s.id];
      cb.addEventListener('change', function () {
        enabled[s.id] = cb.checked;
        saveFilter();
        updatePoolCount();
      });
      var name = document.createElement('span');
      name.className = 'sname';
      name.textContent = s.short;
      name.title = s.name;
      label.appendChild(cb);
      label.appendChild(name);
      if (s.points === 20) {
        var pt = document.createElement('span');
        pt.className = 'pt20';
        pt.textContent = '20';
        label.appendChild(pt);
      }
      var cnt = document.createElement('span');
      cnt.className = 'scount';
      cnt.textContent = countBySubject(s.id);
      label.appendChild(cnt);
      list.appendChild(label);
    });
    $('optWrongFirst').checked = opts.wrongFirst;
    $('optShuffleChoices').checked = opts.shuffleChoices;
    document.querySelectorAll('#srcFilter button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.src === opts.src));
    });
    updatePoolCount();
  }
  function updatePoolCount() { $('poolCount').textContent = pool().length; }

  function bulk(kind) {
    SUBJECTS.forEach(function (s) {
      if (kind === 'all') enabled[s.id] = true;
      else if (kind === 'none') enabled[s.id] = false;
      else if (kind === 'heavy') enabled[s.id] = s.points === 20;
      else enabled[s.id] = s.block === kind;
    });
    saveFilter();
    renderFilter();
  }

  function toggleFilter(force) {
    var p = $('filterPanel');
    var show = typeof force === 'boolean' ? force : p.hidden;
    p.hidden = !show;
    $('quiz').hidden = show || !pool().length;
    if (!show) {
      // range may have changed under us; make sure the live question is in range
      if (!current || !enabled[current.q.subject] || !pool().length) renderQuestion();
      else $('quiz').hidden = false;
    }
    $('empty').hidden = show || pool().length > 0;
  }

  // ---------- wiring ----------
  function init() {
    loadFilter();
    renderFilter();
    renderHud();
    renderQuestion();

    $('btnReset').addEventListener('click', resetScore);
    $('btnFilter').addEventListener('click', function () { toggleFilter(); });
    $('btnFilterClose').addEventListener('click', function () { toggleFilter(false); });
    $('btnNext').addEventListener('click', next);

    document.querySelectorAll('.filter-bulk button[data-bulk]').forEach(function (b) {
      b.addEventListener('click', function () { bulk(b.dataset.bulk); });
    });
    document.querySelectorAll('#srcFilter button').forEach(function (b) {
      b.addEventListener('click', function () {
        opts.src = b.dataset.src;
        saveFilter();
        renderFilter();
      });
    });
    $('optWrongFirst').addEventListener('change', function (e) {
      opts.wrongFirst = e.target.checked; saveFilter();
    });
    $('optShuffleChoices').addEventListener('change', function (e) {
      opts.shuffleChoices = e.target.checked; saveFilter();
    });

    document.addEventListener('keydown', function (e) {
      if (!$('filterPanel').hidden) return;
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      if (!answered && /^[1-9]$/.test(e.key)) {
        var pos = parseInt(e.key, 10) - 1;
        if (current && pos < current.order.length) { e.preventDefault(); answer(pos); }
        return;
      }
      if (answered && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); next(); }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
