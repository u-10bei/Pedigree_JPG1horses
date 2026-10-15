// 日本G1勝ち馬の父系図（折りたたみ式の横向きツリー）
(() => {
  "use strict";

  // 「主要な系統を開く」で開く基準：子孫の G1 勝利数
  const MAJOR_THRESHOLD = 100;
  const INITIAL_SCALE = 0.85; // 最初の表示の倍率（ラベルが読める大きさ）
  const NODE_DX = 22; // 縦方向の間隔
  const NODE_DY = 190; // 横方向（世代）の間隔

  // 系統の色：ライトモードの色 → ダークモードの色（検証済みパレット）
  const DARK_STEP = {
    "#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
    "#e87ba4": "#d55181", "#008300": "#008300", "#6250d6": "#9085e9", "#e34948": "#e66767",
  };

  const svg = d3.select("#tree");
  const tooltip = document.getElementById("tooltip");
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  let data, byId, childrenOf, lineColor;
  let expanded = new Set();
  let showChain = false;
  let highlight = new Set();
  let root, viewport, zoom;

  const isDark = () => {
    const theme = document.documentElement.dataset.theme;
    return theme === "dark" || (theme !== "light" && darkQuery.matches);
  };

  const neutral = () => getComputedStyle(document.documentElement).getPropertyValue("--neutral-series").trim();

  function colorOf(horse) {
    const c = horse && horse.line ? lineColor.get(horse.line) : null;
    if (!c) return neutral();
    return isDark() ? DARK_STEP[c.toLowerCase()] || c : c;
  }

  // ---- データの準備 -------------------------------------------------------

  function prepare(json) {
    data = json;
    byId = new Map(json.horses.map((h) => [h.id, h]));
    childrenOf = new Map();
    for (const h of json.horses) {
      if (h.father === null) continue;
      if (!childrenOf.has(h.father)) childrenOf.set(h.father, []);
      childrenOf.get(h.father).push(h.id);
    }
    lineColor = new Map(json.lines.map((l) => [l.name, l.color]));

    // 子孫（自身を含む）の G1 勝利数
    const memo = new Map();
    const total = (id) => {
      if (memo.has(id)) return memo.get(id);
      const h = byId.get(id);
      let n = h.wins ? h.wins.length : 0;
      for (const c of childrenOf.get(id) || []) n += total(c);
      memo.set(id, n);
      return n;
    };
    // 深い系統で再帰が深くなりすぎないよう、葉から順に計算する
    const order = [];
    const stack = [0];
    while (stack.length) {
      const id = stack.pop();
      order.push(id);
      for (const c of childrenOf.get(id) || []) stack.push(c);
    }
    for (let i = order.length - 1; i >= 0; i--) total(order[i]);
    for (const h of json.horses) h.descWins = memo.get(h.id) || 0;
    // 子の並び：子孫の勝利数が多い順
    for (const list of childrenOf.values()) list.sort((a, b) => byId.get(b).descWins - byId.get(a).descWins);
  }

  // 中継ぎ（子が 1 頭だけで G1 未勝利、系統の起点でもない）か
  const isPassThrough = (h) =>
    h.id !== 0 && !h.wins && !h.lineRoot && (childrenOf.get(h.id) || []).length === 1;

  // 表示用の木を作る。中継ぎは省略し、省略した祖先は子の skipped に入れる
  function buildTree() {
    const make = (id, skipped) => {
      const h = byId.get(id);
      const node = { horse: h, skipped, hiddenCount: 0 };
      const kids = childrenOf.get(id) || [];
      if (id === 0 || expanded.has(id)) {
        node.children = kids.map((cid) => {
          let current = byId.get(cid);
          const chain = [];
          while (!showChain && isPassThrough(current)) {
            chain.push(current);
            current = byId.get(childrenOf.get(current.id)[0]);
          }
          return make(current.id, chain);
        });
      } else {
        node.hiddenCount = kids.length;
      }
      return node;
    };
    return make(0, []);
  }

  // ---- 開閉の状態 ---------------------------------------------------------

  function expandMajor() {
    expanded = new Set(data.horses.filter((h) => h.descWins >= MAJOR_THRESHOLD).map((h) => h.id));
    expanded.add(0);
  }

  function expandAll() {
    expanded = new Set(data.horses.map((h) => h.id));
  }

  function collapseAll() {
    expanded = new Set([0]);
    for (const id of childrenOf.get(0) || []) expanded.add(id);
  }

  // 始祖からその馬までを開く（中継ぎの省略に関係なく、実際の父系をすべて開く）
  function expandPathTo(id) {
    let h = byId.get(id);
    const path = [];
    while (h && h.father !== null) {
      h = byId.get(h.father);
      path.push(h.id);
    }
    for (const p of path) expanded.add(p);
    return path;
  }

  // ---- 描画 ---------------------------------------------------------------

  function radius(h) {
    return h.wins ? 3 + Math.sqrt(h.wins.length) * 2.6 : 3;
  }

  function setup() {
    svg.selectAll("g.viewport").remove();
    viewport = svg.append("g").attr("class", "viewport");
    viewport.append("g").attr("class", "links");
    viewport.append("g").attr("class", "skip-labels");
    viewport.append("g").attr("class", "nodes");
    zoom = d3.zoom().scaleExtent([0.15, 3]).on("zoom", (e) => viewport.attr("transform", e.transform));
    svg.call(zoom).on("dblclick.zoom", null);
  }

  function render(anchorId) {
    const before = anchorId !== undefined ? screenPosition(anchorId) : null;

    root = d3.hierarchy(buildTree(), (d) => d.children);
    d3.tree().nodeSize([NODE_DX, NODE_DY]).separation((a, b) => (a.parent === b.parent ? 1 : 1.3))(root);

    const nodes = root.descendants().filter((d) => d.data.horse.id !== 0);
    const links = root.links().filter((l) => l.source.data.horse.id !== 0);
    const linkPath = d3.linkHorizontal().x((d) => d.y).y((d) => d.x);

    viewport
      .select("g.links")
      .selectAll("path")
      .data(links, (l) => l.target.data.horse.id)
      .join("path")
      .attr("class", (l) => {
        const cls = ["link"];
        if (l.target.data.skipped.length) cls.push("skipped");
        if (highlight.has(l.target.data.horse.id) && highlight.has(l.source.data.horse.id)) cls.push("highlight");
        return cls.join(" ");
      })
      .attr("stroke", (l) => colorOf(l.target.data.horse))
      .attr("d", linkPath);

    viewport
      .select("g.skip-labels")
      .selectAll("text")
      .data(links.filter((l) => l.target.data.skipped.length), (l) => l.target.data.horse.id)
      .join("text")
      .attr("class", "skip-label")
      .attr("x", (l) => (l.source.y + l.target.y) / 2)
      .attr("y", (l) => (l.source.x + l.target.x) / 2 - 4)
      .attr("text-anchor", "middle")
      .text((l) => `⋯${l.target.data.skipped.length}代⋯`);

    const node = viewport
      .select("g.nodes")
      .selectAll("g.node")
      .data(nodes, (d) => d.data.horse.id)
      .join((enter) => {
        const g = enter.append("g").attr("class", "node");
        g.append("circle").attr("class", "hit");
        g.append("circle").attr("class", "dot");
        g.append("text").attr("class", "line-label");
        g.append("text").attr("class", "name");
        g.append("text").attr("class", "more");
        return g;
      })
      .attr("class", (d) => {
        const h = d.data.horse;
        const cls = ["node"];
        if (h.wins) cls.push("winner");
        if (d.data.hiddenCount) cls.push("collapsed");
        if (highlight.has(h.id)) cls.push("highlight");
        return cls.join(" ");
      })
      .attr("transform", (d) => `translate(${d.y},${d.x})`)
      .attr("tabindex", (d) => ((childrenOf.get(d.data.horse.id) || []).length ? 0 : -1))
      .attr("role", "button")
      .attr("aria-label", (d) => describe(d.data.horse))
      .on("click", (e, d) => toggle(d.data.horse.id))
      .on("keydown", (e, d) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle(d.data.horse.id);
        }
      })
      .on("mouseenter focus", (e, d) => showTooltip(e, d))
      .on("mousemove", (e) => moveTooltip(e))
      .on("mouseleave blur", hideTooltip);

    node.select("circle.hit").attr("r", (d) => radius(d.data.horse) + 6);
    node
      .select("circle.dot")
      .attr("r", (d) => radius(d.data.horse))
      .attr("fill", (d) => colorOf(d.data.horse))
      .style("stroke", (d) => (d.data.hiddenCount ? colorOf(d.data.horse) : null));
    node
      .select("text.name")
      .attr("x", (d) => radius(d.data.horse) + 5)
      .attr("dy", "0.32em")
      .text((d) => d.data.horse.name);
    node
      .select("text.more")
      .attr("dy", "0.32em")
      .attr("x", function (d) {
        const name = this.parentNode.querySelector("text.name");
        return radius(d.data.horse) + 9 + (name ? name.getComputedTextLength() : 0);
      })
      .text((d) => (d.data.hiddenCount ? `＋${d.data.hiddenCount}` : ""));
    // 系統の起点には系統名を直接表示する（色だけに頼らない）
    node
      .select("text.line-label")
      .attr("x", 0)
      .attr("y", (d) => -radius(d.data.horse) - 6)
      .attr("text-anchor", "middle")
      .text((d) => (d.data.horse.lineRoot ? d.data.horse.line : ""));

    if (before) {
      const after = screenPosition(anchorId);
      if (after) {
        const t = d3.zoomTransform(svg.node());
        svg.call(zoom.transform, t.translate((before[0] - after[0]) / t.k, (before[1] - after[1]) / t.k));
      }
    }
  }

  function screenPosition(id) {
    if (!root) return null;
    const d = root.descendants().find((n) => n.data.horse.id === id);
    if (!d) return null;
    const t = d3.zoomTransform(svg.node());
    return [t.applyX(d.y), t.applyY(d.x)];
  }

  function toggle(id) {
    if (!(childrenOf.get(id) || []).length) return;
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    render(id);
  }

  // 最初の表示：子孫の G1 勝利数が最も多い系統の起点を、画面の左寄り中央に置く。
  // 木は 20 世代以上あり全体を 1 画面に収めると文字が読めないため、読める倍率で主要部分を見せる
  function initialView() {
    const visible = root.descendants().filter((d) => d.data.horse.id !== 0);
    const roots = visible.filter((d) => d.data.horse.lineRoot && lineColor.get(d.data.horse.line));
    const target = (roots.length ? roots : visible).reduce((a, b) => (b.data.horse.descWins > a.data.horse.descWins ? b : a));
    const { width, height } = svg.node().getBoundingClientRect();
    const k = INITIAL_SCALE;
    svg.call(zoom.transform, d3.zoomIdentity.translate(width * 0.3 - target.y * k, height / 2 - target.x * k).scale(k));
  }

  function focusOn(id) {
    const d = root.descendants().find((n) => n.data.horse.id === id);
    if (!d) return;
    const { width, height } = svg.node().getBoundingClientRect();
    const k = Math.max(d3.zoomTransform(svg.node()).k, 0.9);
    svg
      .transition()
      .duration(500)
      .call(zoom.transform, d3.zoomIdentity.translate(width / 2 - d.y * k, height / 2 - d.x * k).scale(k));
  }

  // ---- ツールチップ ---------------------------------------------------------

  function describe(h) {
    const parts = [h.name];
    if (h.birth) parts.push(`${h.birth}年生`);
    if (h.wins) parts.push(`G1 ${h.wins.length}勝`);
    if (h.line) parts.push(h.line);
    return parts.join("、");
  }

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function showTooltip(event, d) {
    const h = d.data.horse;
    const father = h.father !== null && h.father !== 0 ? byId.get(h.father) : null;
    const rows = [];
    if (h.birth) rows.push(["生年", `${h.birth}年`]);
    if (father) rows.push(["父", father.name]);
    if (h.line) rows.push(["系統", h.line]);
    rows.push(["子孫の G1", `${h.descWins}勝`]);
    const kids = (childrenOf.get(h.id) || []).length;
    if (kids) rows.push(["子（データ内）", `${kids}頭`]);
    if (d.data.skipped.length) rows.push(["省略した祖先", d.data.skipped.map((s) => s.name).reverse().join(" → ")]);
    let html = `<h2>${escapeHtml(h.name)}</h2><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join("")}</dl>`;
    if (h.wins) {
      html += `<ul>${h.wins.map(([y, r]) => `<li>${y} ${escapeHtml(r)}</li>`).join("")}</ul>`;
    }
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    moveTooltip(event);
  }

  function moveTooltip(event) {
    const chart = document.getElementById("chart").getBoundingClientRect();
    let x, y;
    if (event.clientX !== undefined && event.type !== "focus") {
      x = event.clientX - chart.left + 16;
      y = event.clientY - chart.top + 12;
    } else {
      const r = event.target.getBoundingClientRect();
      x = r.right - chart.left + 8;
      y = r.top - chart.top;
    }
    const w = tooltip.offsetWidth;
    if (x + w > chart.width) x = Math.max(8, x - w - 32);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  // ---- 検索 ---------------------------------------------------------------

  function search(name) {
    const target = data.horses.find((h) => h.name === name.trim());
    if (!target) return false;
    const path = expandPathTo(target.id);
    highlight = new Set([target.id, ...path]);
    render();
    focusOn(target.id);
    return true;
  }

  // ---- 凡例・一覧表・概要 ---------------------------------------------------

  function renderLegend() {
    const legend = document.getElementById("legend");
    legend.innerHTML = "";
    const groups = new Map(); // 色 → 系統名
    for (const l of data.lines) {
      const key = l.color || "";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(l.name);
    }
    for (const [color, names] of groups) {
      const item = document.createElement("span");
      item.className = "legend-item";
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.background = color ? (isDark() ? DARK_STEP[color.toLowerCase()] || color : color) : neutral();
      item.append(swatch);
      const label = document.createElement("span");
      label.textContent = color ? names[0] : "その他";
      item.append(label);
      if (names.length > 1 || !color) {
        const sub = document.createElement("span");
        sub.className = "legend-sub";
        sub.textContent = color ? `（${names.slice(1).join("・")}を含む）` : `（${names.join("・")}）`;
        item.append(sub);
      }
      legend.append(item);
    }
  }

  function renderTable() {
    const tbody = document.querySelector("#winners tbody");
    const winners = data.horses.filter((h) => h.wins).sort((a, b) => a.wins[0][0] - b.wins[0][0] || a.name.localeCompare(b.name, "ja"));
    const frag = document.createDocumentFragment();
    for (const h of winners) {
      const tr = document.createElement("tr");
      const nameCell = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "link-button";
      btn.textContent = h.name;
      btn.addEventListener("click", () => {
        document.getElementById("search").value = h.name;
        search(h.name);
        document.getElementById("chart").scrollIntoView({ behavior: "smooth" });
      });
      nameCell.append(btn);
      const father = byId.get(h.father);
      const cells = [h.birth || "", father && father.id !== 0 ? father.name : "", h.line || "", h.wins.length, h.wins.map(([y, r]) => `${y} ${r}`).join("、")];
      tr.append(nameCell);
      cells.forEach((v, i) => {
        const td = document.createElement("td");
        td.textContent = v;
        if (i === 3) td.className = "num";
        tr.append(td);
      });
      frag.append(tr);
    }
    tbody.replaceChildren(frag);
  }

  function renderSummary() {
    const winners = data.horses.filter((h) => h.wins).length;
    const wins = data.horses.reduce((n, h) => n + (h.wins ? h.wins.length : 0), 0);
    document.getElementById("summary").textContent =
      `G1 勝ち馬 ${winners} 頭（${wins} 勝）とその父系 ${data.horses.length - 1} 頭。${data.lastYear} 年までのデータ（${data.generated} 更新）`;
    const list = document.getElementById("horse-names");
    list.replaceChildren(...data.horses.filter((h) => h.id !== 0).map((h) => Object.assign(document.createElement("option"), { value: h.name })));
  }

  // ---- 起動 ---------------------------------------------------------------

  function bindControls() {
    const input = document.getElementById("search");
    input.addEventListener("change", () => search(input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") search(input.value);
    });
    document.getElementById("expand-major").addEventListener("click", () => {
      expandMajor();
      highlight = new Set();
      render();
      initialView();
    });
    document.getElementById("expand-all").addEventListener("click", () => {
      expandAll();
      render();
      initialView();
    });
    document.getElementById("collapse-all").addEventListener("click", () => {
      collapseAll();
      highlight = new Set();
      render();
      initialView();
    });
    document.getElementById("show-chain").addEventListener("change", (e) => {
      showChain = e.target.checked;
      render();
    });
    darkQuery.addEventListener("change", () => {
      render();
      renderLegend();
    });
  }

  fetch("data/pedigree.json")
    .then((r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    })
    .then((json) => {
      prepare(json);
      setup();
      expandMajor();
      render();
      initialView();
      renderLegend();
      renderTable();
      renderSummary();
      bindControls();
      const initial = new URLSearchParams(location.search).get("horse");
      if (initial) {
        document.getElementById("search").value = initial;
        search(initial);
      }
    })
    .catch((err) => {
      document.getElementById("summary").textContent = `データを読み込めませんでした（${err.message}）。python -m pedigree build を実行してください。`;
    });
})();
