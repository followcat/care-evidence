(function () {
  "use strict";

  var BOARD_LABEL = { daily: "日常", rx: "治疗／创面" };
  var P_ORDER = {
    "基础用途优选": 0,
    "条件适用": 1,
    "对照·选购成立": 2,
    "对照·条件适用": 3,
    "待核": 4
  };
  var CAT_ORDER = [
    "sunscreen", "serum", "basics", "barrier", "cream", "bodylotion",
    "bodywash", "shampoo", "conditioner", "toothpaste"
  ];

  var state = {
    board: null,
    cat: null,
    q: "",
    verdict: "",
    pband: "",
    sort: "default"
  };
  var products = [];
  var app = document.getElementById("app");
  var lede = document.getElementById("lede");

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function pStatus(rec) {
    return (rec.v5 && rec.v5.p_status) || "未完成实用评估";
  }

  function pBand(rec) {
    return (rec.v5 && rec.v5.p_band) || null;
  }

  function dTier(rec) {
    return (rec.v5 && rec.v5.d_tier) || "尚无差异证据或待评";
  }

  function num(v) {
    return typeof v === "number" ? v : null;
  }

  function buyLinks(rec) {
    var out = [];
    var seen = {};
    var buy = rec.buy || {};
    (buy.channels || []).forEach(function (ch) {
      var href = ch && ch.href;
      if (typeof href === "string" && /^https?:\/\//.test(href) && !seen[href]) {
        seen[href] = true;
        out.push({ label: ch.label || "渠道", href: href });
      }
    });
    if (typeof buy.buyHref === "string" && /^https?:\/\//.test(buy.buyHref) && !seen[buy.buyHref]) {
      seen[buy.buyHref] = true;
      out.push({ label: buy.buyLabel || "购买页", href: buy.buyHref });
    }
    return out;
  }

  function haystack(rec) {
    return [
      rec.product, rec.id, rec.cat_label, rec.role, rec.actives,
      rec.official, rec.channel, rec.cites
    ].join(" ").toLowerCase();
  }

  function matches(rec) {
    if (state.board && rec.board !== state.board) return false;
    if (state.cat && state.cat !== "__all__" && rec.cat !== state.cat) return false;
    if (state.verdict && rec.legacy && rec.legacy.verdict !== state.verdict) return false;
    if (state.pband === "__none__") {
      if (rec.v5 && rec.v5.p_evaluated) return false;
    } else if (state.pband && pBand(rec) !== state.pband) {
      return false;
    }
    if (state.q) {
      var q = state.q.toLowerCase();
      if (haystack(rec).indexOf(q) === -1) return false;
    }
    return true;
  }

  function compare(a, b) {
    if (state.sort === "e") {
      var ea = num(a.legacy && a.legacy.E), eb = num(b.legacy && b.legacy.E);
      if (ea !== eb) return (eb || 0) - (ea || 0);
    } else if (state.sort === "s") {
      var sa = num(a.legacy && a.legacy.score), sb = num(b.legacy && b.legacy.score);
      if (sa !== sb) return (sb || 0) - (sa || 0);
    } else if (state.sort === "name") {
      var c = String(a.product).localeCompare(String(b.product), "zh-Hans-CN");
      if (c !== 0) return c;
    } else {
      var pa = P_ORDER[pBand(a)] != null ? P_ORDER[pBand(a)] : 5;
      var pb = P_ORDER[pBand(b)] != null ? P_ORDER[pBand(b)] : 5;
      if (pa !== pb) return pa - pb;
      var e2a = num(a.legacy && a.legacy.E) || 0;
      var e2b = num(b.legacy && b.legacy.E) || 0;
      if (e2a !== e2b) return e2b - e2a;
    }
    var s2a = num(a.legacy && a.legacy.score) || 0;
    var s2b = num(b.legacy && b.legacy.score) || 0;
    if (s2a !== s2b) return s2b - s2a;
    return String(a.id).localeCompare(String(b.id));
  }

  function cardHtml(rec) {
    var e = rec.legacy && rec.legacy.E;
    var s = rec.legacy && rec.legacy.score;
    var p = pStatus(rec);
    var d = dTier(rec);
    var links = buyLinks(rec);
    var buyHtml = links.length
      ? '<div class="buys"><span class="tag">仅供核验</span>' + links.map(function (l) {
          return '<a class="buy-link" href="' + esc(l.href) +
            '" target="_blank" rel="noopener noreferrer nofollow">' + esc(l.label) + "</a>";
        }).join("") + "</div>"
      : '<div class="buys"><span class="unknown">购买线索：未知／待核</span></div>';

    return '<li class="card">' +
      '<div class="card-head">' +
        '<a class="pname" href="p/' + esc(rec.id) + '/index.html">' + esc(rec.product) + "</a>" +
        '<span class="meta">' + esc(rec.cat_label) + " · " + esc(rec.board_label) + "</span>" +
      "</div>" +
      '<div class="badges">' +
        '<span class="chip chip-e">E' + esc(e == null ? "?" : e) + "</span>" +
        '<span class="chip chip-s">S' + esc(s == null ? "?" : s) + "</span>" +
        '<span class="chip chip-p">' + esc(p) + "</span>" +
        '<span class="chip chip-d">D · ' + esc(d) + "</span>" +
      "</div>" +
      '<p class="role">' + esc(rec.role || "主打作用：未知／待核") + "</p>" +
      '<p class="drawback">缺点：' + esc(rec.drawback || "未知／待核") + "</p>" +
      '<p class="cites">证据出处：' + esc(rec.cites || "未知／待核") + "</p>" +
      buyHtml +
    "</li>";
  }

  function renderChoices() {
    var counts = {};
    products.forEach(function (r) { counts[r.board] = (counts[r.board] || 0) + 1; });
    var boardHtml = ["daily", "rx"].map(function (b) {
      return '<button class="choice" type="button" data-board="' + b + '" aria-pressed="' +
        (state.board === b) + '">' + esc(BOARD_LABEL[b]) +
        "<small>" + (counts[b] || 0) + " 条</small></button>";
    }).join("");

    var catCounts = {};
    products.forEach(function (r) {
      if (state.board && r.board !== state.board) return;
      catCounts[r.cat] = (catCounts[r.cat] || 0) + 1;
    });
    var labels = {};
    products.forEach(function (r) { labels[r.cat] = r.cat_label; });
    var catHtml = CAT_ORDER.filter(function (c) { return catCounts[c]; }).map(function (c) {
      return '<button class="choice" type="button" data-cat="' + c + '" aria-pressed="' +
        (state.cat === c) + '">' + esc(labels[c] || c) +
        "<small>" + catCounts[c] + " 条</small></button>";
    }).join("");
    var catAll = state.board
      ? '<button class="choice" type="button" data-cat="__all__" aria-pressed="' +
        (state.cat === "__all__") + '">全部品类<small>' + (counts[state.board] || 0) + " 条</small></button>"
      : "";

    return '<section class="step"><h2>1 · 先选用途</h2><div class="choices">' +
      boardHtml + '</div></section>' +
      (state.board
        ? '<section class="step"><h2>2 · 再选品类</h2><div class="choices">' +
          catHtml + catAll + "</div></section>"
        : '<p class="note">选好用途后出现品类。</p>');
  }

  function renderToolbar() {
    var verdictOpts = [
      ["", "全部证据档"],
      ["rec", "证据充分（旧门）"],
      ["consider", "证据中等（旧门）"],
      ["weak", "证据有限（旧门）"],
      ["skip", "证据不足（旧门）"]
    ];
    var pOpts = [
      ["", "全部 P 档"],
      ["基础用途优选", "基础用途优选"],
      ["条件适用", "条件适用"],
      ["对照·选购成立", "对照·选购成立"],
      ["对照·条件适用", "对照·条件适用"],
      ["待核", "待核"],
      ["__none__", "未完成实用评估"]
    ];
    var sortOpts = [
      ["default", "默认：P 档 → E 档"],
      ["e", "E 证据档"],
      ["s", "S 旧评分"],
      ["name", "品名"]
    ];
    function opts(list, val) {
      return list.map(function (o) {
        return '<option value="' + esc(o[0]) + '"' + (val === o[0] ? " selected" : "") +
          ">" + esc(o[1]) + "</option>";
      }).join("");
    }
    return '<div class="toolbar">' +
      '<label class="grow">搜索<input id="q" type="search" placeholder="品名 / id / 品牌关键词" value="' +
        esc(state.q) + '"></label>' +
      '<label>证据档<select id="verdict">' + opts(verdictOpts, state.verdict) + "</select></label>" +
      '<label>P 档<select id="pband">' + opts(pOpts, state.pband) + "</select></label>" +
      '<label>排序<select id="sort">' + opts(sortOpts, state.sort) + "</select></label>" +
      '<button class="reset" type="button" id="reset">清空筛选</button>' +
    "</div>";
  }

  function renderList() {
    var filtered = products.filter(matches).sort(compare);
    var head = '<p class="result-count">共 ' + filtered.length + " 条";

    if (!state.cat || state.cat === "__all__") {
      var groups = {};
      filtered.forEach(function (r) { (groups[r.cat] = groups[r.cat] || []).push(r); });
      if (!filtered.length) return head + '</p><p class="empty">没有符合条件的条目，试试清空筛选。</p>';
      var html = head + "（按品类分组，品类之间不排名）</p>";
      CAT_ORDER.forEach(function (c) {
        var list = groups[c];
        if (!list || !list.length) return;
        html += '<h3 class="group-title">' + esc(list[0].cat_label) +
          " <span>" + list.length + " 条</span></h3>" +
          '<ul class="list">' + list.map(cardHtml).join("") + "</ul>";
      });
      return html;
    }
    if (!filtered.length) return head + '</p><p class="empty">没有符合条件的条目，试试清空筛选。</p>';
    return head + "</p><ul class=\"list\">" + filtered.map(cardHtml).join("") + "</ul>";
  }

  function render() {
    if (!state.board) {
      lede.textContent = "先选用途，再选品类，然后看单个条目。不做跨品类总分排名。";
      app.innerHTML = renderChoices();
      return;
    }
    lede.textContent = "当前：" + BOARD_LABEL[state.board] +
      (state.cat && state.cat !== "__all__" ? " · " + (products.find(function (r) { return r.cat === state.cat; }) || {}).cat_label : " · 全部品类");
    app.innerHTML = renderChoices() +
      (state.cat ? renderToolbar() + '<div id="list">' + renderList() + "</div>" : "");
  }

  function bind() {
    app.addEventListener("click", function (ev) {
      var board = ev.target.closest("[data-board]");
      if (board) {
        state.board = board.getAttribute("data-board");
        state.cat = "__all__";
        state.q = ""; state.verdict = ""; state.pband = ""; state.sort = "default";
        render();
        return;
      }
      var cat = ev.target.closest("[data-cat]");
      if (cat) {
        var v = cat.getAttribute("data-cat");
        state.cat = v === "__all__" ? "__all__" : v;
        render();
        return;
      }
      if (ev.target.closest("#reset")) {
        state.q = ""; state.verdict = ""; state.pband = ""; state.sort = "default";
        render();
      }
    });

    app.addEventListener("input", function (ev) {
      if (ev.target.id === "q") {
        state.q = ev.target.value.trim();
        renderListInPlace();
      }
    });

    app.addEventListener("change", function (ev) {
      var id = ev.target.id;
      if (id === "verdict") state.verdict = ev.target.value;
      else if (id === "pband") state.pband = ev.target.value;
      else if (id === "sort") state.sort = ev.target.value;
      else return;
      renderListInPlace();
    });
  }

  function renderListInPlace() {
    var list = document.getElementById("list");
    if (!list) return;
    list.innerHTML = renderList();
  }

  fetch("data/products.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      if (!Array.isArray(data) || !data.length) throw new Error("数据为空");
      products = data;
      render();
      bind();
    })
    .catch(function (err) {
      app.innerHTML = '<p class="empty">数据载入失败（' + esc(err.message) +
        "）。请通过本地服务器打开：python3 -m http.server -d site/dist 8000</p>";
    });
})();
