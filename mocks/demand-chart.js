// Замороженная копия графика для статичных макетов (mocks). Рабочая версия — static/demand-chart.js.
/*
 * График распределения спроса по 9 сценариям (квантили 10%…90%).
 *
 * Высота столбика — сколько человек «желают» купить билет при введённой цене.
 * Сплошная часть — сколько «купят» (не больше числа мест), штриховка — желающие,
 * которым не хватит мест. Пунктир — число мест в самолёте. Медиана (50%) выделена:
 * её число совпадает с «желают» из простого прогноза.
 *
 * Цвета берутся из CSS-переменных страницы:
 *   --chart-sold, --chart-median, --chart-excess, --chart-seats, --chart-grid, --chart-text
 */
(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const M = { left: 52, right: 62, top: 30, bottom: 58 };
  const HALO = `paint-order:stroke;stroke:${color("bg", "#fff")};stroke-width:4px;stroke-linejoin:round`;
  const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  let uid = 0;

  function niceStep(raw) {
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const factor = [1, 2, 2.5, 5, 10].find((f) => f * magnitude >= raw);
    return factor * magnitude;
  }

  function el(name, attrs, text) {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function color(name, fallback) {
    return `var(--chart-${name}, ${fallback})`;
  }

  // options.width / options.height — пропорции графика (в единицах viewBox), по умолчанию 720×340.
  function render(target, data, options = {}) {
    const W = options.width || 720;
    const H = options.height || 340;
    const id = `dc${++uid}`;
    const plotW = W - M.left - M.right;
    const plotH = H - M.top - M.bottom;
    const demand = (s) => Math.max(0, s.wanted);
    const top = Math.max(data.seats, ...data.scenarios.map(demand)) * 1.08 || 1;
    const step = niceStep(top / 6);
    const yMax = Math.ceil(top / step) * step;
    const y = (v) => M.top + plotH - (v / yMax) * plotH;
    const slot = plotW / data.scenarios.length;
    const barW = slot * 0.58;

    const svg = el("svg", {
      viewBox: `0 0 ${W} ${H}`,
      class: "demand-chart",
      role: "img",
      "aria-label": `Спрос по 9 сценариям. Мест: ${data.seats}. Медиана: ${number.format(Math.max(0, data.wanted))}.`,
      style: `width:100%;height:auto;font-family:inherit;color:${color("text", "#333")}`,
    });

    const defs = el("defs");
    const pattern = el("pattern", {
      id: `${id}-hatch`, patternUnits: "userSpaceOnUse", width: 7, height: 7, patternTransform: "rotate(45)",
    });
    pattern.append(
      el("rect", { width: 7, height: 7, style: `fill:${color("excess-bg", "transparent")}` }),
      el("line", { x1: 0, y1: 0, x2: 0, y2: 7, style: `stroke:${color("excess", "#c0392b")};stroke-width:3` }),
    );
    defs.append(pattern);
    svg.append(defs);

    for (let v = 0; v <= yMax; v += step) {
      svg.append(el("line", {
        x1: M.left, x2: W - M.right, y1: y(v), y2: y(v),
        style: `stroke:${color("grid", "#ddd")};stroke-width:1`,
      }));
      svg.append(el("text", {
        x: M.left - 8, y: y(v) + 4, "text-anchor": "end", "font-size": 12,
        style: `fill:${color("muted", "#777")}`,
      }, number.format(v)));
    }

    const valueLabels = el("g", { class: "values" });
    data.scenarios.forEach((s, i) => {
      const isMedian = Math.abs(s.quantile - 0.5) < 1e-9;
      const x = M.left + slot * i + (slot - barW) / 2;
      const group = el("g", { class: isMedian ? "bar median" : "bar" });
      const sold = Math.max(0, s.sold);
      const wanted = demand(s);
      group.append(el("title", {}, scenarioTitle(s)));
      if (wanted > sold) {
        group.append(el("rect", {
          x, width: barW, y: y(wanted), height: y(sold) - y(wanted),
          style: `fill:url(#${id}-hatch)`,
        }));
      }
      group.append(el("rect", {
        x, width: barW, y: y(sold), height: Math.max(0, M.top + plotH - y(sold)),
        style: `fill:${isMedian ? color("median", "#1f4e79") : color("sold", "#7f9cb8")}`,
      }));
      valueLabels.append(el("text", {
        x: x + barW / 2, y: y(wanted) - 7, "text-anchor": "middle", "font-size": isMedian ? 14 : 12,
        "font-weight": isMedian ? 700 : 400, style: `fill:currentColor;${HALO}`,
      }, number.format(wanted)));
      group.append(el("text", {
        x: x + barW / 2, y: H - M.bottom + 20, "text-anchor": "middle", "font-size": 13,
        "font-weight": isMedian ? 700 : 400, style: "fill:currentColor",
      }, `${Math.round(s.quantile * 100)}%`));
      if (isMedian) {
        group.append(el("text", {
          x: x + barW / 2, y: H - M.bottom + 37, "text-anchor": "middle", "font-size": 12,
          style: `fill:${color("muted", "#777")}`,
        }, "медиана"));
      }
      svg.append(group);
    });

    svg.append(el("line", {
      x1: M.left, x2: W - M.right, y1: y(data.seats), y2: y(data.seats),
      style: `stroke:${color("seats", "#c0392b")};stroke-width:2;stroke-dasharray:7 5`,
    }));
    const seatsLabel = el("text", {
      x: W - M.right + 8, y: y(data.seats) - 3, "font-size": 12, "font-weight": 700,
      style: `fill:${color("seats", "#c0392b")}`,
    });
    seatsLabel.append(
      el("tspan", { x: W - M.right + 8 }, "мест"),
      el("tspan", { x: W - M.right + 8, dy: 14 }, number.format(data.seats)),
    );
    svg.append(seatsLabel);

    svg.append(el("line", {
      x1: M.left, x2: W - M.right, y1: M.top + plotH, y2: M.top + plotH,
      style: "stroke:currentColor;stroke-width:1",
    }));
    svg.append(el("text", {
      x: M.left + plotW / 2, y: H - 4, "text-anchor": "middle", "font-size": 12,
      style: `fill:${color("muted", "#777")}`,
    }, "сценарий: с такой вероятностью спрос окажется ниже столбика"));
    svg.append(valueLabels);

    target.replaceChildren(svg);
    return svg;
  }

  function scenarioTitle(s) {
    const pct = Math.round(s.quantile * 100);
    const lines = [`Сценарий ${pct}%: желают ${number.format(s.wanted)}, купят ${number.format(s.sold)}`];
    if (s.sold_out) lines.push("Продажи упираются в число мест");
    if (s.wanted < 0) lines.push("По формуле спрос отрицательный — продаж нет");
    return lines.join("\n");
  }

  window.DemandChart = { render };
})();
