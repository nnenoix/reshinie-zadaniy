// Кривая ожидаемой прибыли от цены (вёрстка из макета Claude Design).
// Кривую с шагом 10 ₽ и точный максимум считает сервер; здесь только рисунок.
import { fmt } from "./format.js";
import { el, niceScale } from "./svg.js";

// d: { curve: [{price, profit}], min, max, best, bestProfit, price, profit }
export function drawProfit(box, d) {
  if (!d.curve.length) {
    box.replaceChildren();
    return;
  }
  const W = box.clientWidth || 360, H = box.clientHeight || 180;
  const L = 36, R = 8, T = 30, B = 24, iw = W - L - R, ih = H - T - B;
  const top = Math.max(...d.curve.map((c) => c.profit), d.bestProfit);
  const scale = niceScale(Math.max(top, 1) * 1.1);
  const x = (p) => L + (iw * (p - d.min)) / (d.max - d.min);
  const y = (v) => T + ih * (1 - Math.max(0, v) / scale.max);

  const root = el("svg", { viewBox: `0 0 ${W} ${H}` });
  for (let g = 0; g <= scale.max + 1e-9; g += scale.tick) {
    root.append(el("line", { class: "ch-grid", x1: L, x2: W - R, y1: y(g), y2: y(g) }));
    root.append(el("text", { class: "ch-tick", x: L - 6, y: y(g) + 3 }, fmt(g / 1e6, 2)));
  }
  root.append(el("text", { class: "ch-tick", x: L - 6, y: T - 16 }, "млн ₽"));
  const points = d.curve.map((c) => `${x(c.price).toFixed(1)},${y(c.profit).toFixed(1)}`).join(" ");
  root.append(el("polygon", { class: "pc-area", points: `${x(d.min)},${y(0)} ${points} ${x(d.max)},${y(0)}` }));
  root.append(el("polyline", { class: "pc-line", points }));

  const bx = x(d.best), by = y(d.bestProfit);
  const cp = Math.max(d.min, Math.min(d.max, d.price)), cx = x(cp), cy = y(d.profit);
  root.append(el("line", { class: "pc-best-line", x1: bx, x2: bx, y1: by, y2: y(0) }));
  root.append(el("line", { class: "pc-cur-line", x1: cx, x2: cx, y1: cy, y2: y(0) }));
  root.append(el("circle", { class: "pc-best", cx: bx, cy: by, r: 5 }));
  root.append(el("circle", { class: "pc-cur", cx, cy, r: 4.5 }));
  const nearRight = bx > W - 110;
  root.append(el("text", { class: "pc-label pc-label--best", x: bx + (nearRight ? -4 : 4), y: by - 10,
    "text-anchor": nearRight ? "end" : "start" }, `Макс · ${fmt(d.best)}`));
  const nearLeft = cx < 110;
  root.append(el("text", { class: "pc-label pc-label--cur", x: cx + (nearLeft ? 8 : -8), y: cy + 16,
    "text-anchor": nearLeft ? "start" : "end" }, `Ваша · ${fmt(d.price)}`));
  root.append(el("text", { class: "pc-label", x: L, y: H - 6 }, fmt(d.min)));
  root.append(el("text", { class: "pc-label", x: W - R, y: H - 6, "text-anchor": "end" }, `${fmt(d.max)} ₽`));
  box.replaceChildren(root);
}
