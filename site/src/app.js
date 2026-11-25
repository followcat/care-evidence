(function () {
  "use strict";

  var BOARD_LABEL = { daily: "日常护理", rx: "皮肤出问题（医用）" };
  var P_ORDER = {
    "基础用途优选": 0,
    "条件适用": 1,
    "对照·选购成立": 2,
    "对照·条件适用": 3,
    "待核": 4
  };
  var BAND_ORDER = { le100: 0, b300: 1, b500: 2, b1000: 3, b2000: 4, b3000: 5 };
  var CAT_ORDER = [
    "sunscreen", "serum", "basics", "barrier", "cream", "bodylotion",
    "bodywash", "shampoo", "conditioner", "toothpaste", "mask", "oral"
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
    var v = rec.v5 && rec.v5.p_status;
    if (!v || v === "未完成实用评估") return "还没评";
    return v;
  }

  function pBand(rec) {
    return (rec.v5 && rec.v5.p_band) || null;
  }

  function dTier(rec) {
    return (rec.v5 && rec.v5.d_tier) || "暂无看点";
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
    } else if (state.sort === "price") {
      var ba = BAND_ORDER[a.band] != null ? BAND_ORDER[a.band] : 9;
      var bb = BAND_ORDER[b.band] != null ? BAND_ORDER[b.band] : 9;
      if (ba !== bb) return ba - bb;
    } else if (state.sort === "pricedesc") {
      var ba2 = BAND_ORDER[a.band] != null ? BAND_ORDER[a.band] : -1;
      var bb2 = BAND_ORDER[b.band] != null ? BAND_ORDER[b.band] : -1;
      if (ba2 !== bb2) return bb2 - ba2;
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

  function hasText(v) {
    return typeof v === "string" && v.trim().length > 0;
  }

  function shortPrice(v) {
    if (!hasText(v)) return "";
    var s = v.replace(/\s*[·;；]\s*20\d\d-\d\d-\d\d.*$/, "").trim();
    var cut = s.indexOf("；");
    if (cut > 0) s = s.slice(0, cut);
    cut = s.indexOf("; ");
    if (cut > 0) s = s.slice(0, cut);
    if (s.length > 42) s = s.slice(0, 42) + "…";
    return s;
  }

  function cardHtml(rec) {
    var e = rec.legacy && rec.legacy.E;
    var s = rec.legacy && rec.legacy.score;
    var p = pStatus(rec);
    var d = dTier(rec);
    var links = buyLinks(rec);
    var buyHtml = links.length
      ? '<div class="buys">' + links.map(function (l) {
          return '<a class="buy-link" href="' + esc(l.href) +
            '" target="_blank" rel="noopener noreferrer nofollow">' + esc(l.label) + "</a>";
        }).join("") + '<span class="tag">指路非推荐</span></div>'
      : '<div class="buys"><span class="unknown">还没查到靠谱链接</span></div>';

    var lines = "";
    var sp = shortPrice(rec.price);
    if (sp) lines += '<p class="price">' + esc(sp) + "</p>";
    if (hasText(rec.role)) lines += '<p class="role">' + esc(rec.role) + "</p>";
    if (hasText(rec.drawback)) lines += '<p class="drawback">缺点：' + esc(rec.drawback) + "</p>";

    return '<li class="card">' +
      '<div class="card-head">' +
        '<a class="pname" href="p/' + esc(rec.id) + '/index.html">' + esc(rec.product) + "</a>" +
        '<span class="meta">' + esc(rec.cat_label) + " · " + esc(rec.band_label || "") + "</span>" +
      "</div>" +
      '<div class="badges">' +
        '<span class="chip chip-e" title="证据硬不硬">E' + esc(e == null ? "?" : e) + "</span>" +
        '<span class="chip chip-s" title="老算法总分">S' + esc(s == null ? "?" : s) + "</span>" +
        '<span class="chip chip-p" title="值不值得买">' + esc(p) + "</span>" +
        '<span class="chip chip-d" title="有没有新东西">D · ' + esc(d) + "</span>" +
      "</div>" +
      lines +
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

    return '<section class="step"><h2>先看用途</h2><div class="choices">' +
      boardHtml + '</div></section>' +
      (state.board
        ? '<section class="step"><h2>再看品类</h2><div class="choices">' +
          catHtml + catAll + "</div></section>"
        : '<p class="note">点了用途，品类就出来了。</p>');
  }

  function renderToolbar() {
    var verdictOpts = [
      ["", "证据：全部"],
      ["rec", "证据够硬"],
      ["consider", "证据还行"],
      ["weak", "证据偏弱"],
      ["skip", "没啥证据"]
    ];
    var pOpts = [
      ["", "值不值：全部"],
      ["基础用途优选", "基础用途优选"],
      ["条件适用", "条件适用"],
      ["对照·选购成立", "对照·选购成立"],
      ["对照·条件适用", "对照·条件适用"],
      ["待核", "待核"],
      ["__none__", "还没评的"]
    ];
    var sortOpts = [
      ["default", "默认排序"],
      ["e", "证据最硬在前"],
      ["price", "价格从低到高"],
      ["pricedesc", "价格从高到低"],
      ["s", "老总分高的在前"],
      ["name", "按名字"]
    ];
    function opts(list, val) {
      return list.map(function (o) {
        return '<option value="' + esc(o[0]) + '"' + (val === o[0] ? " selected" : "") +
          ">" + esc(o[1]) + "</option>";
      }).join("");
    }
    return '<div class="toolbar">' +
      '<label class="grow">搜一下<input id="q" type="search" placeholder="品名 / 成分 / 品牌关键词" value="' +
        esc(state.q) + '"></label>' +
      '<label><select id="verdict" aria-label="证据">' + opts(verdictOpts, state.verdict) + "</select></label>" +
      '<label><select id="pband" aria-label="值不值">' + opts(pOpts, state.pband) + "</select></label>" +
      '<label><select id="sort" aria-label="排序">' + opts(sortOpts, state.sort) + "</select></label>" +
      '<button class="reset" type="button" id="reset">清空</button>' +
    "</div>";
  }

  function renderList() {
    var filtered = products.filter(matches).sort(compare);
    var head = '<p class="result-count">共 ' + filtered.length + " 条";

    if (!state.cat || state.cat === "__all__") {
      var groups = {};
      filtered.forEach(function (r) { (groups[r.cat] = groups[r.cat] || []).push(r); });
      if (!filtered.length) return head + '</p><p class="empty">这个筛法啥也没剩，清一清筛选再试。</p>';
      var html = head + "（按品类分了组，组跟组之间不比高下）</p>";
      CAT_ORDER.forEach(function (c) {
        var list = groups[c];
        if (!list || !list.length) return;
        html += '<h3 class="group-title">' + esc(list[0].cat_label) +
          " <span>" + list.length + " 条</span></h3>" +
          '<ul class="list">' + list.map(cardHtml).join("") + "</ul>";
      });
      return html;
    }
    if (!filtered.length) return head + '</p><p class="empty">这个筛法啥也没剩，清一清筛选再试。</p>';
    return head + "</p><ul class=\"list\">" + filtered.map(cardHtml).join("") + "</ul>";
  }

  function render() {
    if (!state.board) {
      lede.textContent = "挑个用途，再挑品类，一条条看。";
      app.innerHTML = renderChoices();
      syncHash();
      return;
    }
    lede.textContent = "现在看的是：" + BOARD_LABEL[state.board] +
      (state.cat && state.cat !== "__all__" ? " · " + (products.find(function (r) { return r.cat === state.cat; }) || {}).cat_label : " · 全部品类");
    app.innerHTML = renderChoices() +
      (state.cat ? renderToolbar() + '<div id="list">' + renderList() + "</div>" : "");
    syncHash();
  }

  function syncHash() {
    var parts = [];
    if (state.board) parts.push("board=" + state.board);
    if (state.cat && state.cat !== "__all__") parts.push("cat=" + state.cat);
    else if (state.cat === "__all__") parts.push("cat=__all__");
    if (state.q) parts.push("q=" + encodeURIComponent(state.q));
    if (state.verdict) parts.push("verdict=" + state.verdict);
    if (state.pband) parts.push("pband=" + encodeURIComponent(state.pband));
    if (state.sort && state.sort !== "default") parts.push("sort=" + state.sort);
    var hash = parts.length ? "#" + parts.join("&") : "#";
    if (location.hash !== hash) {
      history.replaceState(null, "", hash === "#" ? location.pathname + location.search : hash);
    }
  }

  function loadHash() {
    if (!location.hash || location.hash.length < 2) return;
    var params = {};
    location.hash.slice(1).split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) params[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
    });
    if (params.board === "daily" || params.board === "rx") state.board = params.board;
    if (params.cat) state.cat = params.cat;
    if (params.q) state.q = params.q;
    if (params.verdict) state.verdict = params.verdict;
    if (params.pband) state.pband = params.pband;
    if (params.sort) state.sort = params.sort;
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
    syncHash();
  }

  fetch("data/products.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      if (!Array.isArray(data) || !data.length) throw new Error("数据为空");
      products = data;
      loadHash();
      render();
      bind();
    })
    .catch(function (err) {
      app.innerHTML = '<p class="empty">数据没加载出来（' + esc(err.message) +
        "）。别双击 HTML 文件，起个本地服务再看：python3 -m http.server -d site/dist 8000</p>";
    });
})();
