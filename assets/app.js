(function () {
  'use strict';

  var DATA = window.KDQ || { subjects: [], blocks: [], questions: [] };
  var SUBJECTS = DATA.subjects;
  var ALL = DATA.questions;
  var SUBJECT_BY_ID = {};
  SUBJECTS.forEach(function (s) { SUBJECT_BY_ID[s.id] = s; });
  var BY_ID = {};
  ALL.forEach(function (q) { BY_ID[q.id] = q; });

  var LS_KEY = 'kdq.filter.v2';

  // --- セッションごとの成績。ページを開くたびにゼロから ---
  var score = { correct: 0, total: 0, streak: 0, best: 0 };
  var wrongPool = [];   // この回に間違えた問題。再出題に使う
  var recent = [];      // 直近に出した問題。すぐ同じものが出ないように
  var enabled = {};
  var opts = { wrongFirst: true, shuffleChoices: true, src: 'all', minStars: 1 };
  var current = null;   // { q, order, picks }
  var answered = false;

  function $(id) { return document.getElementById(id); }
  function isExam(q) { return /^令和/.test(q.tag || ''); }
  function isBlanks(q) { return !!(q.blanks && q.blanks.length); }
  function byId(id) { return BY_ID[id]; }

  // ---------- 出題範囲 ----------
  function loadFilter() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { saved = null; }
    SUBJECTS.forEach(function (s) {
      enabled[s.id] = saved && saved.enabled ? saved.enabled.indexOf(s.id) >= 0 : true;
    });
    if (saved && saved.opts) {
      ['wrongFirst', 'shuffleChoices'].forEach(function (k) {
        if (typeof saved.opts[k] === 'boolean') opts[k] = saved.opts[k];
      });
      if (typeof saved.opts.src === 'string') opts.src = saved.opts.src;
      if (typeof saved.opts.minStars === 'number') opts.minStars = saved.opts.minStars;
    }
  }
  function saveFilter() {
    var on = SUBJECTS.filter(function (s) { return enabled[s.id]; }).map(function (s) { return s.id; });
    try { localStorage.setItem(LS_KEY, JSON.stringify({ enabled: on, opts: opts })); } catch (e) { /* 使えなくても動く */ }
  }

  function pool() {
    return ALL.filter(function (q) {
      if (!enabled[q.subject]) return false;
      if ((q.stars || 1) < opts.minStars) return false;
      if (opts.src === 'exam') return isExam(q);
      if (opts.src === 'base') return !isExam(q);
      return true;
    });
  }

  function pick() {
    var p = pool();
    if (!p.length) return null;
    if (opts.wrongFirst && wrongPool.length && Math.random() < 0.34) {
      var wp = wrongPool.filter(function (id) {
        var q = byId(id);
        return q && enabled[q.subject] && (q.stars || 1) >= opts.minStars;
      });
      if (wp.length) return byId(wp[(Math.random() * wp.length) | 0]);
    }
    var avoid = Math.min(recent.length, Math.max(0, Math.floor(p.length * 0.5)));
    var skip = recent.slice(recent.length - avoid);
    var fresh = p.filter(function (q) { return skip.indexOf(q.id) < 0; });
    var src = fresh.length ? fresh : p;
    return src[(Math.random() * src.length) | 0];
  }

  function shuffled(n) {
    var a = [];
    for (var i = 0; i < n; i++) a.push(i);
    for (var j = a.length - 1; j > 0; j--) {
      var k = (Math.random() * (j + 1)) | 0;
      var t = a[j]; a[j] = a[k]; a[k] = t;
    }
    return a;
  }
  function order(n) {
    if (opts.shuffleChoices) return shuffled(n);
    var a = [];
    for (var i = 0; i < n; i++) a.push(i);
    return a;
  }

  // ---------- 表示 ----------
  function renderHud() {
    $('hudCorrect').textContent = score.correct;
    $('hudTotal').textContent = score.total;
    $('hudRate').textContent = score.total ? Math.round(score.correct / score.total * 100) + '%' : '—';
    $('hudStreak').textContent = score.streak >= 2 ? '連続' + score.streak : '';
    $('footStats').textContent = score.total
      ? '誤答 ' + (score.total - score.correct) + ' / 最長連続 ' + score.best + ' / 要復習 ' + wrongPool.length + ' 問'
      : '';
  }

  function choiceButton(text, num, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    var n = document.createElement('span');
    n.className = 'num';
    n.textContent = num;
    var t = document.createElement('span');
    t.textContent = text;
    b.appendChild(n);
    b.appendChild(t);
    b.addEventListener('click', onClick);
    return b;
  }

  /** 本文の 【ア】 を空欄の見た目に差し替えて描画する */
  function renderPassage(el, text, labels) {
    el.innerHTML = '';
    var re = /【([^】]*)】/g, last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) el.appendChild(document.createTextNode(text.slice(last, m.index)));
      var span = document.createElement('span');
      var known = labels.indexOf(m[1]) >= 0;
      span.className = known ? 'blank-mark' : 'blank-mark blank-other';
      span.textContent = known ? m[1] : '…';
      span.dataset.label = m[1];
      el.appendChild(span);
      last = re.lastIndex;
    }
    if (last < text.length) el.appendChild(document.createTextNode(text.slice(last)));
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
    answered = false;

    recent.push(q.id);
    if (recent.length > 400) recent.shift();

    var s = SUBJECT_BY_ID[q.subject];
    $('qsubject').textContent = (s ? s.name : q.subject) + (s && s.points === 20 ? '（20点科目）' : '');
    var stars = q.stars || 1;
    $('qstars').textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
    $('qstars').title = (q.years && q.years.length)
      ? '過去5年の出題: ' + q.years.join('・')
      : '過去5年では同じ論点の出題を確認できず';
    $('qsrc').textContent = isExam(q) ? q.tag + ' 本試験' : '条文ベース';

    $('verdict').hidden = true;
    $('verdictLine').className = '';
    $('choices').innerHTML = '';
    $('blanks').innerHTML = '';
    $('btnGrade').hidden = true;

    if (isBlanks(q)) {
      renderBlanks(q);
    } else {
      renderSingle(q);
    }
    window.scrollTo(0, 0);
  }

  function renderSingle(q) {
    $('qtext').textContent = q.q;
    var ord = order(q.choices.length);
    current = { q: q, order: ord };
    var wide = q.choices.every(function (c) { return c.length <= 2; });
    var ol = $('choices');
    ol.className = wide ? 'compact' : '';
    ord.forEach(function (origIdx, pos) {
      var li = document.createElement('li');
      li.appendChild(choiceButton(q.choices[origIdx], wide ? '' : (pos + 1) + '.',
        function () { answerSingle(pos); }));
      ol.appendChild(li);
    });
  }

  function renderBlanks(q) {
    var picks = q.blanks.map(function () { return -1; });
    var orders = q.blanks.map(function (bl) { return order(bl.choices.length); });
    current = { q: q, orders: orders, picks: picks };

    renderPassage($('qtext'), q.q.split('\n\n').slice(1).join('\n\n'),
      q.blanks.map(function (bl) { return bl.label; }));

    var wrap = $('blanks');
    q.blanks.forEach(function (bl, i) {
      var row = document.createElement('div');
      row.className = 'blank-row';
      row.dataset.i = String(i);
      var lab = document.createElement('span');
      lab.className = 'blank-mark';
      lab.textContent = bl.label;
      row.appendChild(lab);
      var box = document.createElement('div');
      box.className = 'blank-choices';
      orders[i].forEach(function (origIdx, pos) {
        var b = choiceButton(bl.choices[origIdx], '', function () { pickBlank(i, pos); });
        b.dataset.pos = String(pos);
        box.appendChild(b);
      });
      row.appendChild(box);
      var res = document.createElement('div');
      res.className = 'blank-result';
      res.hidden = true;
      row.appendChild(res);
      wrap.appendChild(row);
    });
    $('btnGrade').hidden = false;
    $('btnGrade').disabled = true;
    $('btnGrade').textContent = '採点する（残り ' + q.blanks.length + '）';
  }

  function pickBlank(i, pos) {
    if (answered) return;
    current.picks[i] = pos;
    var row = $('blanks').querySelector('.blank-row[data-i="' + i + '"]');
    row.querySelectorAll('.blank-choices button').forEach(function (b) {
      b.classList.toggle('is-picked', Number(b.dataset.pos) === pos);
    });
    var left = current.picks.filter(function (p) { return p < 0; }).length;
    $('btnGrade').disabled = left > 0;
    $('btnGrade').textContent = left ? '採点する（残り ' + left + '）' : '採点する (Enter)';
  }

  function markScore(ok) {
    score.total++;
    if (ok) {
      score.correct++;
      score.streak++;
      if (score.streak > score.best) score.best = score.streak;
    } else {
      score.streak = 0;
    }
  }

  function answerSingle(pos) {
    if (answered || !current) return;
    answered = true;
    var q = current.q;
    var chosen = current.order[pos];
    var ok = chosen === q.answer;
    var correctPos = current.order.indexOf(q.answer);

    markScore(ok);
    if (ok) {
      var wi = wrongPool.indexOf(q.id);
      if (wi >= 0) wrongPool.splice(wi, 1);
    } else if (wrongPool.indexOf(q.id) < 0) {
      wrongPool.push(q.id);
    }

    var btns = $('choices').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    if (btns[correctPos]) btns[correctPos].classList.add('is-correct');
    if (!ok && btns[pos]) btns[pos].classList.add('is-wrong');

    showVerdict(ok, ok ? '正解' : '不正解 — 正答は「' + q.choices[q.answer] + '」', q.explain, q.ref);
  }

  function grade() {
    if (answered || !current || !isBlanks(current.q)) return;
    answered = true;
    var q = current.q;
    var hit = 0;

    q.blanks.forEach(function (bl, i) {
      var pos = current.picks[i];
      var chosen = current.orders[i][pos];
      var ok = chosen === bl.answer;
      if (ok) hit++;
      markScore(ok);

      var row = $('blanks').querySelector('.blank-row[data-i="' + i + '"]');
      var correctPos = current.orders[i].indexOf(bl.answer);
      row.querySelectorAll('.blank-choices button').forEach(function (b) {
        b.disabled = true;
        var p = Number(b.dataset.pos);
        if (p === correctPos) b.classList.add('is-correct');
        if (!ok && p === pos) b.classList.add('is-wrong');
      });
      row.classList.add(ok ? 'row-ok' : 'row-ng');
      var res = row.querySelector('.blank-result');
      res.hidden = false;
      res.textContent = (ok ? '○ ' : '× 正答「' + bl.choices[bl.answer] + '」 ') + (bl.explain || '');

      var markId = q.id + '#' + bl.label;
      var wi = wrongPool.indexOf(markId);
      if (ok) { if (wi >= 0) wrongPool.splice(wi, 1); }
      else if (wi < 0) wrongPool.push(q.id);
    });

    $('qtext').querySelectorAll('.blank-mark').forEach(function (el) {
      var bl = q.blanks.filter(function (b) { return b.label === el.dataset.label; })[0];
      if (bl) { el.textContent = bl.choices[bl.answer]; el.classList.add('blank-filled'); }
    });

    $('btnGrade').hidden = true;
    var all = q.blanks.length;
    showVerdict(hit === all, hit + ' / ' + all + ' 正解', '', q.ref);
  }

  function showVerdict(ok, line, explain, ref) {
    var vl = $('verdictLine');
    vl.textContent = line;
    vl.className = ok ? 'ok' : 'ng';
    $('explain').textContent = explain || '';
    $('ref').textContent = ref ? '出典: ' + ref : '';
    $('verdict').hidden = false;
    renderHud();
    $('btnNext').focus();
  }

  function next() { if (answered) renderQuestion(); }

  function resetScore() {
    score = { correct: 0, total: 0, streak: 0, best: 0 };
    wrongPool = [];
    recent = [];
    renderHud();
    renderQuestion();
  }

  // ---------- 範囲パネル ----------
  function countBySubject(id) {
    var n = 0;
    for (var i = 0; i < ALL.length; i++) if (ALL[i].subject === id) n++;
    return n;
  }

  function renderFilter() {
    var list = $('subjectList');
    list.innerHTML = '';
    SUBJECTS.forEach(function (s) {
      var label = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = 'subj-' + s.id;
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
    document.querySelectorAll('#starFilter button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(Number(b.dataset.star) === opts.minStars));
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
    $('empty').hidden = show || pool().length > 0;
    if (!show) {
      var live = current && current.q;
      var stillOk = live && enabled[live.subject] && (live.stars || 1) >= opts.minStars
        && (opts.src === 'all' || (opts.src === 'exam') === isExam(live));
      if (!stillOk || !pool().length) renderQuestion();
      else $('quiz').hidden = false;
    }
  }

  // ---------- 起動 ----------
  function init() {
    loadFilter();
    renderFilter();
    renderHud();
    renderQuestion();

    $('btnReset').addEventListener('click', resetScore);
    $('btnFilter').addEventListener('click', function () { toggleFilter(); });
    $('btnFilterClose').addEventListener('click', function () { toggleFilter(false); });
    $('btnNext').addEventListener('click', next);
    $('btnGrade').addEventListener('click', grade);

    document.querySelectorAll('.filter-bulk button[data-bulk]').forEach(function (b) {
      b.addEventListener('click', function () { bulk(b.dataset.bulk); });
    });
    document.querySelectorAll('#srcFilter button').forEach(function (b) {
      b.addEventListener('click', function () { opts.src = b.dataset.src; saveFilter(); renderFilter(); });
    });
    document.querySelectorAll('#starFilter button').forEach(function (b) {
      b.addEventListener('click', function () {
        opts.minStars = Number(b.dataset.star); saveFilter(); renderFilter();
      });
    });
    $('optWrongFirst').addEventListener('change', function (e) { opts.wrongFirst = e.target.checked; saveFilter(); });
    $('optShuffleChoices').addEventListener('change', function (e) { opts.shuffleChoices = e.target.checked; saveFilter(); });

    document.addEventListener('keydown', function (e) {
      if (!$('filterPanel').hidden) return;
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      if (answered && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); next(); return; }
      if (!answered && current && !isBlanks(current.q) && /^[1-9]$/.test(e.key)) {
        var pos = parseInt(e.key, 10) - 1;
        if (pos < current.order.length) { e.preventDefault(); answerSingle(pos); }
        return;
      }
      if (!answered && current && isBlanks(current.q) && e.key === 'Enter' && !$('btnGrade').disabled) {
        e.preventDefault();
        grade();
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
