/* ==========================================================================
   site.js —— 数据驱动渲染（公开版 / 私有版共用）
   依赖 data/site-data.js (window.BENCH) 与 data/gallery.js (window.GALLERY)
   ========================================================================== */
(function () {
  "use strict";

  var D = window.BENCH || { models: [], prompts: [], categories: [], counts: {} };
  var G = window.GALLERY || [];
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var f1 = function (n) { return Number(n).toFixed(1); };
  var CAT = {}, MODEL = {};
  (D.categories || []).forEach(function (c) { CAT[c.key] = c.zh; });
  (D.models || []).forEach(function (m) { MODEL[m.id] = m; });

  var PALETTE = ["#e86a4a", "#c4451f", "#f0a184", "#9c3a1c", "#d97a5a", "#b35a3a", "#e8bda9"];
  var PALETTE2 = ["#8bb0a8", "#5f8a83", "#a9c8c2", "#436b65", "#7f9d97", "#bcd6d1", "#6f8f89"];

  /* ---------------------------------------------------------------- 动效 */
  function initReveal() {
    var els = $$(".reveal");
    if (!("IntersectionObserver" in window)) {
      els.forEach(function (e) { e.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("in");
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    els.forEach(function (e) { io.observe(e); });
  }


  /* ---------------------------------------------------------------- 首页 KPI */
  function renderKpis() {
    var el = $("#kpis");
    if (!el || !D.counts) return;
    var c = D.counts;
    var items = [
      [c.images, "张有效图片", "", 0],
      [c.total_hours, "总生成耗时", "h", 1],
      [c.models, "个模型配置", "", 0],
      [c.prompts, "条提示词", "", 0],
      [c.t4, "张来自 T4", "", 0],
      [c.a10, "张来自 A10", "", 0]
    ];
    el.innerHTML = items.map(function (it) {
      return '<div class="kpi"><div class="k">' + esc(it[1]) + "</div>" +
        '<div class="v">' + it[0] + 
        (it[2] ? "<small>" + it[2] + "</small>" : "") + "</div></div>";
    }).join("");
  }

  /* ---------------------------------------------------------------- 变体文案 */
  function fillVariantText() {
    var c = D.counts || {};
    var el = $("#scopeText");
    if (el) {
      el.innerHTML = D.variant === "private"
        ? "本站<b>包含全部结果</b>：" + c.prompts + " 条提示词、" + c.images + " 张图，其中 <b>" +
          c.nsfw + " 张成人向</b>默认隐藏，需确认年龄后查看。"
        : "本站<b>只包含 SFW（非成人向）结果</b>：" + c.prompts + " 条提示词、" + c.images + " 张图。";
    }
  }

  /* ---------------------------------------------------------------- 报告页文案 */
  function fillReportText() {
    var c = D.counts || {};
    var lead = $("#dsLead");
    if (lead) {
      lead.textContent = D.variant === "private"
        ? c.prompts + " 条提示词（51 SFW + 16 成人向）覆盖 " + c.categories + " 个类别"
        : c.prompts + " 条 SFW 提示词覆盖 " + c.categories + " 个类别";
    }
    var note = $("#dsNote");
    if (note) {
      note.textContent = D.variant === "private"
        ? "16 条成人向提示词（P52–P67）分四组：artistic / extreme / dark / guro，对应 " + c.nsfw + " 张图；图库中默认隐藏，需确认年龄后查看。"
        : "原 67 条中的 16 条成人向提示词与其 384 张生成图不在公开包内，相关统计已在生成站点时剔除。";
    }
    [["figT4", c.t4], ["figA10", c.a10], ["figAll", c.images]].forEach(function (it) {
      var el = document.getElementById(it[0]);
      if (el) el.textContent = it[1];
    });
  }

  /* ---------------------------------------------------------------- 首页规格牌 */
  function fillPlate() {
    var c = D.counts || {};
    var h = D.highlight || {};
    [["images", c.images, "张"], ["hours", c.total_hours, "小时"],
     ["fastT4", f1(h.fastest_t4.sec), "s"], ["slowT4", f1(h.slowest_t4.sec), "s"],
     ["vram", (h.vram_ceiling / 1000).toFixed(1), "/ 15.36 GB"]].forEach(function (it) {
      var el = document.querySelector('[data-fill="' + it[0] + '"]');
      if (!el) return;
      el.innerHTML = it[1] + "<small>" + it[2] + "</small>";
    });
  }

  /* ---------------------------------------------------------------- 结论卡 */
  function renderFindings() {
    var el = $("#finds");
    if (!el) return;
    var h = D.highlight, c = D.counts;
    var cards = [
      ['01', "T4 上最快与最慢差 " + h.speedup + " 倍",
        '<span class="big">' + h.fastest_t4.sec + "<em>s</em> → " + h.slowest_t4.sec + "<em>s</em></span>",
        "<p>" + esc(h.fastest_t4.name) + " 4 步出图，中位 " + h.fastest_t4.sec + " 秒；" +
        esc(h.slowest_t4.name) + " 12B 权重在 16G 卡上反复换入换出，中位 " + h.slowest_t4.sec +
        " 秒。差距主要来自显存，不是算力。</p>"],
      ['02', "显存不是「够用」，是「刚好」",
        '<span class="big">' + (h.vram_ceiling / 1000).toFixed(1) + "<em>G / 15.36G</em></span>",
        "<p>三个大模型峰值都贴在 14.9G，只剩约 450MB 余量，必须分块换入换出。" +
        "这是 Krea 单张破百秒的直接原因。</p>"],
      ['03', "一个启动参数，快 3.3 倍",
        '<span class="big">' + f1(h.flux2_all) + "<em>s → </em>" + f1(h.flux2_final) + "<em>s</em></span>",
        "<p>去掉 <code>--disable-smart-memory</code> 后权重在同模型连续跑时常驻显存，" +
        "FLUX.2 klein 4B 的中位耗时从 " + f1(h.flux2_all) + " 秒降到 " + f1(h.flux2_final) + " 秒。</p>"],
      ['04', "SDXL 的 CLIP 有长度边界",
        '<span class="big">77<em>token</em></span>',
        "<p>negative 跨过 77 token（约 300 字符）后，T4 上 <code>cublasSgemm</code> 必崩，" +
        "且与语义无关。规避方式是从 negative 末尾逐段裁词重试。</p>"],
      ['05', "A10 的价值是「装得下」",
        '<span class="big">18.8<em>G 峰值</em></span>',
        "<p>Krea 2 峰值 18.8G，Qwen 20B、MOSS 50 步也都只有 24G 卡能跑。" +
        "同一代模型在 A10 上快 2–5 倍，但真正的门槛是容量。</p>"]
    ];
    el.innerHTML = cards.map(function (x, i) {
      return '<div class="find' + (i === 0 ? " wide" : "") + '">' +
        '<span class="no">' + x[0] + "</span><h3>" + esc(x[1]) + "</h3>" + x[2] + x[3] + "</div>";
    }).join("");
  }

  /* ---------------------------------------------------------------- 总耗时面板 */
  function renderTimePanel() {
    var el = $("#timePanel");
    if (!el) return;
    var c = D.counts;
    var stat = [
      ["总生成耗时", c.total_hours, "小时", true],
      ["T4 累计", c.t4_hours, "小时", false],
      ["A10 累计", c.a10_hours, "小时", false],
      ["平均单张", c.avg_sec, "秒", false]
    ];
    var statsHtml = stat.map(function (s) {
      return '<div><div class="k">' + s[0] + '</div><div class="v' + (s[3] ? " accent" : "") +
        '">' + s[1] + "<small>" + s[2] + "</small></div></div>";
    }).join("");

    var sorted = D.models.slice().sort(function (a, b) { return b.total_sec - a.total_sec; });
    var total = sorted.reduce(function (s, m) { return s + m.total_sec; }, 0) || 1;
    var seg = "", legend = "", iT4 = 0, iA10 = 0;
    sorted.forEach(function (m) {
      var col = m.profile === "T4" ? PALETTE[iT4++ % PALETTE.length] : PALETTE2[iA10++ % PALETTE2.length];
      var pct = m.total_sec / total * 100;
      seg += '<span style="width:' + pct.toFixed(2) + "%;background:" + col +
        '" data-v="' + esc(m.name) + " · " + (m.total_sec / 3600).toFixed(1) + 'h"></span>';
      legend += '<span><i style="background:' + col + '"></i>' + esc(m.name) +
        " <b>" + (m.total_sec / 3600).toFixed(1) + "h</b></span>";
    });

    var tl = D.timeline || [];
    var maxN = Math.max.apply(null, tl.map(function (t) { return t.n; })) || 1;
    var tlHtml = tl.map(function (t) {
      var hpx = Math.max(6, Math.round(t.n / maxN * 66));
      return '<div class="tl-col" title="' + t.date + " · " + t.n + " 张 · " + t.hours +
        'h"><i style="height:' + hpx + 'px"></i></div>';
    }).join("");
    var tlAxis = tl.map(function (t) { return "<span>" + t.date.slice(5) + "</span>"; }).join("");

    el.innerHTML =
      '<div class="dp-head"><b>生成总耗时</b><span>' + c.records + " 次出图 · " +
      (D.sources.batches || []).length + " 个运行批次</span></div>" +
      '<div class="dp-stats">' + statsHtml + "</div>" +
      '<div class="stack"><div class="stack-bar">' + seg + "</div>" +
      '<div class="stack-legend">' + legend + "</div></div>" +
      '<div class="tl">' + tlHtml + "</div>" +
      '<div class="tl-axis">' + tlAxis + "</div>" +
      '<p style="margin:16px 0 0;font-size:11.5px;line-height:1.7;color:#9a8f7d">' +
      "耗时是提交 prompt 到取回图片字节的墙钟时间，含文本编码、采样与 VAE 解码，也含首张的模型加载。" +
      "堆叠条按模型累计耗时排序；时间线是每个运行批次的出图张数。</p>";
  }

  /* ---------------------------------------------------------------- 排行榜 */
  function renderBoards() {
    [["T4", "#boardT4"], ["A10", "#boardA10"]].forEach(function (pair) {
      var el = $(pair[1]);
      if (!el) return;
      var list = D.models.filter(function (m) { return m.profile === pair[0]; })
        .sort(function (a, b) { return a.median_final - b.median_final; });
      var max = Math.max.apply(null, list.map(function (m) { return m.median_final; }));
      el.innerHTML = list.map(function (m, i) {
        return '<a class="lb-row' + (pair[0] === "A10" ? " a10" : "") + '" href="gallery.html?model=' + esc(m.id) + '">' +
          '<span class="r">' + String(i + 1).padStart(2, "0") + "</span>" +
          '<span class="lb-name"><b>' + esc(m.name) + "</b><span>" + m.steps + " 步 · cfg " + m.cfg + " · " + esc(m.sampler) + "</span></span>" +
          '<span class="bar"><i style="width:' + (m.median_final / max * 100).toFixed(1) + '%"></i></span>' +
          '<span class="time">' + f1(m.median_final) + "<small>秒 / 张</small></span>" +
          '<span class="vram">' + (m.vram_mb / 1000).toFixed(1) + " G · " + (m.total_sec / 3600).toFixed(1) + " h</span></a>";
      }).join("");
    });
  }

  /* ---------------------------------------------------------------- 散点图 */
  function renderScatter() {
    var el = $("#scatter");
    if (!el) return;
    var W = 900, H = 430, L = 58, R = 150, T = 26, B = 46;
    var xs = [];
    D.models.forEach(function (m) { xs.push(m.median_final); });
    var xmin = 8, xmax = Math.max.apply(null, xs) * 1.25, ymax = 20;
    function x(v) { return L + (Math.log(v) - Math.log(xmin)) / (Math.log(xmax) - Math.log(xmin)) * (W - L - R); }
    function y(v) { return H - B - (v / ymax) * (H - T - B); }

    var g = "";
    [0, 5, 10, 15, 20].forEach(function (v) {
      g += '<line class="grid" x1="' + L + '" y1="' + y(v) + '" x2="' + (W - R) + '" y2="' + y(v) + '"/>';
      g += '<text class="tick" x="' + (L - 8) + '" y="' + (y(v) + 3) + '" text-anchor="end">' + v + "G</text>";
    });
    [10, 20, 50, 100, 200].forEach(function (v) {
      if (v > xmax) return;
      g += '<line class="grid" x1="' + x(v) + '" y1="' + T + '" x2="' + x(v) + '" y2="' + (H - B) + '"/>';
      g += '<text class="tick" x="' + x(v) + '" y="' + (H - B + 16) + '" text-anchor="middle">' + v + "s</text>";
    });
    g += '<line class="axis" x1="' + L + '" y1="' + y(15.36) + '" x2="' + (W - R) + '" y2="' + y(15.36) +
      '" stroke-dasharray="4 4"/>';
    g += '<text class="anno" x="' + (W - R - 4) + '" y="' + (y(15.36) - 6) + '" text-anchor="end">T4 可用上限 15.36G</text>';
    g += '<line class="axis" x1="' + L + '" y1="' + (H - B) + '" x2="' + (W - R) + '" y2="' + (H - B) + '"/>';
    g += '<line class="axis" x1="' + L + '" y1="' + T + '" x2="' + L + '" y2="' + (H - B) + '"/>';
    g += '<text class="tick" x="' + ((L + W - R) / 2) + '" y="' + (H - 8) + '" text-anchor="middle">中位耗时（对数）</text>';

    // 标签避让：贪心试位，放不下就只留点（悬停仍有数值）
    var placed = [];
    function boxW(t) {
      var w = 0;
      for (var i = 0; i < t.length; i++) w += t.charCodeAt(i) > 127 ? 10 : 5.6;
      return w;
    }
    function fits(b) {
      if (b[0] < L + 2 || b[2] > W - R - 2 || b[1] < T || b[3] > H - B - 2) return false;
      for (var i = 0; i < placed.length; i++) {
        var o = placed[i];
        if (!(b[2] < o[0] || b[0] > o[2] || b[3] < o[1] || b[1] > o[3])) return false;
      }
      return true;
    }

    var pts = D.models.map(function (m) {
      return { m: m, cx: x(m.median_final), cy: y(m.vram_mb / 1000) };
    }).sort(function (a, b) { return a.cy - b.cy; });

    pts.forEach(function (o) {
      var m = o.m, cx = o.cx, cy = o.cy;
      var col = m.profile === "T4" ? "#191612" : "#c4451f";
      var r = 4.5 + Math.sqrt(m.n) * 0.42;
      g += '<circle class="pt" cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + r.toFixed(1) +
        '" fill="' + col + '" fill-opacity="' + (m.profile === "T4" ? ".82" : ".9") + '">' +
        "<title>" + esc(m.name) + " · " + f1(m.median_final) + "s · " +
        (m.vram_mb / 1000).toFixed(1) + "G · " + m.n + " 张</title></circle>";

      var name = m.name.replace("FLUX.", "FLUX ");
      var w = boxW(name), hh = 11;
      var cands = [];
      [0, -13, 13, -26, 26].forEach(function (dy) {
        cands.push({ x: cx + 9, y: cy + 3 + dy, a: "start" });
        cands.push({ x: cx - 9, y: cy + 3 + dy, a: "end" });
      });
      for (var i = 0; i < cands.length; i++) {
        var c = cands[i];
        var x0 = c.a === "start" ? c.x : c.x - w;
        var b = [x0 - 2, c.y - hh, x0 + w + 2, c.y + 2];
        if (fits(b)) {
          placed.push(b);
          g += '<text class="lbl" x="' + c.x.toFixed(1) + '" y="' + c.y.toFixed(1) +
            '" text-anchor="' + c.a + '">' + esc(name) + "</text>";
          break;
        }
      }
    });

    el.innerHTML = '<svg class="scatter" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="速度与显存分布">' + g + "</svg>";
    var lg = $("#scatterLegend");
    if (lg) {
      lg.innerHTML = '<span><i style="background:#191612"></i>T4 · 16G</span>' +
        '<span><i style="background:#c4451f"></i>A10 · 24G</span>' +
        '<span style="margin-left:auto">点面积 ≈ 出图张数 · 悬停看数值</span>';
    }
  }

  /* ---------------------------------------------------------------- 类别 */
  function renderCats() {
    var el = $("#catbar");
    if (!el) return;
    var counts = {};
    (D.categories || []).forEach(function (c) { counts[c.key] = c.images || 0; });
    var max = Math.max.apply(null, Object.keys(counts).map(function (k) { return counts[k]; }));
    el.innerHTML = (D.categories || []).map(function (c) {
      var n = counts[c.key] || 0;
      return '<a class="cr" href="gallery.html?cat=' + esc(c.key) + '" style="color:inherit;text-decoration:none">' +
        '<span>' + esc(c.zh) + ' <em>' + c.count + " 题</em></span>" +
        '<span class="cb"><i style="width:' + (n / max * 100).toFixed(1) + '%"></i></span>' +
        '<span class="cn">' + n + " 张</span></a>";
    }).join("");
  }

  /* ---------------------------------------------------------------- 模型图鉴 */
  function renderModelCards() {
    var el = $("#mcards");
    if (!el) return;
    el.innerHTML = D.models.map(function (m, i) {
      return '<article class="mcard">' +
        '<div class="mc-top"><span>' + esc(m.profile) + " · " + esc(m.family) + "</span><span>" +
          String(i + 1).padStart(2, "0") + "</span></div>" +
        "<h3>" + esc(m.name) + "</h3>" +
        '<div class="maker">' + esc(m.maker) + " · " + esc(m.note) + "</div>" +
        "<p>" + esc(m.intro) + "</p>" +
        '<div class="chips">' + (m.strengths || []).map(function (s) {
          return '<span class="chip">' + esc(s) + "</span>";
        }).join("") + "</div>" +
        '<div class="mc-metrics">' +
          "<span><b>" + f1(m.median_final) + "</b> s / 张</span>" +
          "<span><b>" + (m.vram_mb / 1000).toFixed(1) + "</b> G 峰值</span>" +
          "<span><b>" + (m.total_sec / 3600).toFixed(1) + "</b> h 累计</span>" +
          "<span><b>" + m.n + "</b> 张</span>" +
        "</div></article>";
    }).join("");
  }

  /* ---------------------------------------------------------------- 模型索引（models 页） */
  function renderModels() {
    var el = $("#modelList");
    if (!el) return;
    el.innerHTML = D.models.map(function (m, i) {
      var gpu = m.profile === "T4" ? "t4" : "a10";
      return '<article class="m-row" data-id="' + esc(m.id) + '">' +
        '<button class="m-head" aria-expanded="false">' +
          '<span class="no">' + String(i + 1).padStart(2, "0") + "</span>" +
          '<span class="nm"><b>' + esc(m.name) + "</b><span>" + esc(m.note) + "</span></span>" +
          '<span class="pm">' + esc(m.profile) + "</span>" +
          '<span class="sp">' + f1(m.median_final) + "s</span>" +
          '<span class="lc">' + m.n + " 张 · " + m.prompts + "/" + D.counts.prompts + " 题</span>" +
          '<span class="tg" aria-hidden="true">+</span>' +
        "</button>" +
        '<div class="m-body"><div class="inner">' +
          "<div>" +
            "<h4>采样与权重</h4>" +
            '<dl class="kv">' +
              "<dt>步数</dt><dd>" + m.steps + " 步 · cfg " + m.cfg + "</dd>" +
              "<dt>采样器</dt><dd class=\"mono\">" + esc(m.sampler) + " / " + esc(m.scheduler) + "</dd>" +
              "<dt>主模型</dt><dd class=\"mono\" style=\"word-break:break-all\">" + esc(m.file) + "</dd>" +
              "<dt>文本编码</dt><dd class=\"mono\" style=\"word-break:break-all\">" + esc(m.te) + "</dd>" +
              "<dt>VAE</dt><dd class=\"mono\" style=\"word-break:break-all\">" + esc(m.vae) + "</dd>" +
              "<dt>许可</dt><dd>" + esc(m.license) + "</dd>" +
            "</dl>" +
            '<div style="margin-top:12px"><span class="chip ' + (gpu === "t4" ? "" : "hot") + '">' + esc(m.profile) + "</span>" +
            (m.chinese ? '<span class="chip hot">中文提示词</span>' : "") +
            '<span class="chip">' + esc(m.family) + "</span></div>" +
          "</div>" +
          "<div>" +
            "<h4>实测</h4>" +
            '<dl class="kv">' +
              "<dt>中位耗时</dt><dd>" + f1(m.median_final) + " 秒（定版批次 n=" + m.final_n + "）</dd>" +
              "<dt>全量中位</dt><dd>" + f1(m.median_all) + " 秒（跨批次）</dd>" +
              "<dt>P90</dt><dd>" + f1(m.p90_final) + " 秒</dd>" +
              "<dt>累计耗时</dt><dd>" + (m.total_sec / 3600).toFixed(1) + " 小时 / " + m.n + " 张</dd>" +
              "<dt>峰值显存</dt><dd>" + m.vram_mb + " MB（" + (m.vram_mb / 1000).toFixed(1) + " G）</dd>" +
              "<dt>批次</dt><dd class=\"mono\">" + m.first_date + " → " + m.last_date + "</dd>" +
            "</dl>" +
            '<p style="margin:12px 0 0"><a class="chip" href="gallery.html?model=' + esc(m.id) + '">看该模型的图 →</a></p>' +
          "</div>" +
        "</div></div></article>";
    }).join("");
    el.addEventListener("click", function (e) {
      var head = e.target.closest(".m-head");
      if (!head) return;
      var row = head.parentNode;
      var open = row.classList.toggle("open");
      head.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ---------------------------------------------------------------- 报告表格 */
  function renderReportTables() {
    [["T4", "#t4table"], ["A10", "#a10table"]].forEach(function (pair) {
      var el = $(pair[1]);
      if (!el) return;
      var list = D.models.filter(function (m) { return m.profile === pair[0]; })
        .sort(function (a, b) { return a.median_final - b.median_final; });
      el.innerHTML = list.map(function (m) {
        return "<tr><td><b>" + esc(m.name) + '</b><br><span class="muted" style="font-size:11px">' +
          esc(m.family) + "</span></td>" +
          '<td class="mono">' + m.steps + " · cfg " + m.cfg + "</td>" +
          '<td class="mono">' + esc(m.sampler) + "</td>" +
          '<td class="mono">' + f1(m.median_final) + "s</td>" +
          '<td class="mono muted">' + f1(m.median_all) + "s</td>" +
          '<td class="mono">' + f1(m.p90_final) + "s</td>" +
          '<td class="mono">' + (m.total_sec / 3600).toFixed(1) + "h</td>" +
          '<td class="mono">' + m.vram_mb + " MB</td>" +
          '<td class="mono">' + m.n + "</td></tr>";
      }).join("");
    });
  }

  /* ---------------------------------------------------------------- 图库 */
  var state = { gpu: "all", model: "all", cat: "all", q: "", showNsfw: false, idx: [], open: -1 };

  function renderGallery() {
    var el = $("#gal");
    if (!el) return;
    el.innerHTML = G.map(function (g, i) {
      return '<button class="shot' + (g.n ? " nsfw" : "") + '" data-i="' + i + '" data-m="' + esc(g.m) +
        '" data-g="' + esc(g.p) + '" data-c="' + esc(g.c) + '" data-n="' + g.n + '" data-s="' +
        esc((g.m + " " + g.t + " " + g.id + " " + (CAT[g.c] || "")).toLowerCase()) + '">' +
        '<img loading="lazy" src="' + esc(g.i) + '" alt="' + esc(g.t) + '" width="' + g.w + '" height="' + g.h + '">' +
        (g.n ? "" : '<span class="badge">' + esc(g.p) + " · s" + g.s + "</span>") +
        (g.n ? "" : '<span class="meta"><span>' + esc(g.m) + "</span><span>" + g.d + "s</span></span>") +
        "</button>";
    }).join("");
    apply();
  }

  function apply() {
    var shown = 0, hiddenNsfw = 0;
    $$("#gal .shot").forEach(function (b) {
      var isN = b.dataset.n === "1";
      if (isN && !state.showNsfw) { b.style.display = "none"; hiddenNsfw++; return; }
      var ok = (state.gpu === "all" || b.dataset.g === state.gpu) &&
               (state.model === "all" || b.dataset.m === state.model) &&
               (state.cat === "all" || b.dataset.c === state.cat) &&
               (!state.q || b.dataset.s.indexOf(state.q) > -1);
      b.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    var cl = $("#galCount");
    if (cl) {
      cl.textContent = "显示 " + shown + " / " + G.length + " 张" +
        (hiddenNsfw && !state.showNsfw ? " · " + hiddenNsfw + " 张成人向已隐藏" : "") +
        " · 点击看大图与完整参数";
    }
    var bar = $("#nsfwBar");
    if (bar && !state.showNsfw) {
      var n = G.filter(function (g) { return g.n; }).length;
      bar.classList.toggle("show", n > 0);
      var btn = $("#nsfwToggle");
      if (btn) btn.textContent = "我已成年，显示 " + n + " 张";
    }
  }

  function initGallery() {
    var bar = $("#galFilters");
    if (!bar) return;

    var qs = new URLSearchParams(location.search);
    if (qs.get("model")) state.model = qs.get("model");
    if (qs.get("cat")) state.cat = qs.get("cat");
    if (qs.get("gpu")) state.gpu = qs.get("gpu");

    var models = Array.from(new Set(G.map(function (g) { return g.m; })));
    var order = D.models.map(function (m) { return m.id; }).filter(function (id) { return models.indexOf(id) > -1; });
    $("#modelChips").innerHTML = '<button data-m="all">全部模型</button>' +
      order.map(function (id) {
        var m = MODEL[id] || { name: id };
        return '<button data-m="' + esc(id) + '">' + esc(m.name) + "</button>";
      }).join("");

    $("#catChips").innerHTML = '<button data-c="all">全部类别</button>' +
      (D.categories || []).map(function (c) {
        return '<button data-c="' + esc(c.key) + '"' + (c.nsfw ? ' class="r18"' : "") + ">" + esc(c.zh) + "</button>";
      }).join("");

    function sync() {
      $$("#gpuSeg button").forEach(function (b) { b.classList.toggle("on", b.dataset.g === state.gpu); });
      $$("#modelChips button").forEach(function (b) { b.classList.toggle("on", b.dataset.m === state.model); });
      $$("#catChips button").forEach(function (b) { b.classList.toggle("on", b.dataset.c === state.cat); });
      apply();
    }

    var NSFW_CATS = {};
    (D.categories || []).forEach(function (c) { if (c.nsfw) NSFW_CATS[c.key] = 1; });

    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      // 未确认年龄时，点成人向类别先提示门控，不直接展开
      if (b.dataset.c && NSFW_CATS[b.dataset.c] && !state.showNsfw) {
        var gate = $("#nsfwBar");
        if (gate) {
          gate.classList.add("show", "pulse");
          setTimeout(function () { gate.classList.remove("pulse"); }, 1200);
          gate.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
        return;
      }
      if (b.dataset.g) state.gpu = b.dataset.g;
      if (b.dataset.m) state.model = b.dataset.m;
      if (b.dataset.c) state.cat = b.dataset.c;
      sync();
    });

    var s = $("#galSearch");
    if (s) s.addEventListener("input", function () { state.q = s.value.trim().toLowerCase(); apply(); });

    var more = $("#moreChips");
    if (more) more.addEventListener("click", function () {
      $("#catChips").classList.toggle("expanded");
      more.textContent = $("#catChips").classList.contains("expanded") ? "收起" : "更多类别";
    });

    var nbtn = $("#nsfwToggle");
    if (nbtn) nbtn.addEventListener("click", function () {
      state.showNsfw = !state.showNsfw;
      document.body.classList.toggle("nsfw-on", state.showNsfw);
      nbtn.textContent = state.showNsfw ? "隐藏成人向内容" : "我已成年，显示全部成人向";
      if (!state.showNsfw) $("#nsfwBar").classList.add("show");
      apply();
    });

    sync();

    /* 灯箱 */
    var box = $("#lightbox");
    if (!box) return;
    var stage = $(".stage img", box);
    var side = $(".side", box);

    function openAt(i) {
      var visible = $$("#gal .shot").filter(function (b) { return b.style.display !== "none"; });
      state.idx = visible.map(function (b) { return +b.dataset.i; });
      state.open = Math.max(0, state.idx.indexOf(i));
      paint(i);
      box.classList.add("open");
      document.body.style.overflow = "hidden";
    }
    function paint(i) {
      var g = G[i];
      if (!g) return;
      stage.src = g.i;
      stage.alt = g.t;
      var pr = (D.prompts.filter(function (p) { return p.id === g.id; })[0] || {});
      side.innerHTML =
        "<h3>" + esc(g.t) + "</h3>" +
        '<div class="sub">' + esc(g.m) + " · " + esc(g.p) + " · seed " + g.s + "</div>" +
        "<dl>" +
          "<dt>提示词</dt><dd>" + esc(g.id) + "</dd>" +
          "<dt>类别</dt><dd>" + esc(CAT[g.c] || g.c) + "</dd>" +
          "<dt>分辨率</dt><dd>" + g.w + " × " + g.h + "（" + esc(g.a) + "）</dd>" +
          "<dt>步数</dt><dd>" + g.st + " 步 · cfg " + g.cf + "</dd>" +
          "<dt>采样器</dt><dd>" + esc(g.sa) + "</dd>" +
          "<dt>耗时</dt><dd>" + g.d + " 秒</dd>" +
          "<dt>峰值显存</dt><dd>" + g.v + " MB</dd>" +
          "<dt>语言</dt><dd>" + (g.lang === "zh" ? "中文提示词" : "英文") + "</dd>" +
        "</dl>" +
        '<div class="pr">' + esc(pr.prompt || "") + "</div>";
    }
    function step(d) {
      if (!state.idx.length) return;
      state.open = (state.open + d + state.idx.length) % state.idx.length;
      paint(state.idx[state.open]);
    }
    $("#gal").addEventListener("click", function (e) {
      var b = e.target.closest(".shot");
      if (b) openAt(+b.dataset.i);
    });
    function close() {
      box.classList.remove("open");
      document.body.style.overflow = "";
      stage.removeAttribute("src");
    }
    $(".close", box).addEventListener("click", close);
    $(".prev", box).addEventListener("click", function (e) { e.stopPropagation(); step(-1); });
    $(".next", box).addEventListener("click", function (e) { e.stopPropagation(); step(1); });
    box.addEventListener("click", function (e) {
      if (e.target === box || e.target.classList.contains("stage")) close();
    });
    document.addEventListener("keydown", function (e) {
      if (!box.classList.contains("open")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    });
  }

  /* ---------------------------------------------------------------- 启动 */
  document.addEventListener("DOMContentLoaded", function () {
    fillVariantText();
    fillReportText();
    fillPlate();
    renderKpis();
    renderFindings();
    renderTimePanel();
    renderBoards();
    renderScatter();
    renderCats();
    renderModelCards();
    renderModels();
    renderReportTables();
    renderGallery();
    initGallery();
    initReveal();
  });
})();
