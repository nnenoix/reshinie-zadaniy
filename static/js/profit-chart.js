// Кривая ожидаемой прибыли от цены (вёрстка из макета Claude Design).
// Кривую с шагом 10 ₽ и точный максимум считает сервер; здесь только рисунок.
import { fmt } from "./format.js";
import { el, niceScale } from "./svg.js";

// Места для подписи «Ваша · цена»: сдвиг базовой линии от точки, px. Сначала над точкой,
// потом под ней и ниже; на каждой высоте сначала сторона от максимума — там кривая уходит вниз.
const ROWS = [-10, 16, -24, 30, 44, 58, 72, 86, 100, 114];
const GAP = 8; // от точки до подписи по горизонтали
const PAD = 2; // зазор между подписью и тем, что она не должна задевать

const near = (b, [px, py], r = 0) =>
  px >= b.x - PAD - r && px <= b.x + b.width + PAD + r && py >= b.y - PAD - r && py <= b.y + b.height + PAD + r;
const crossesVertical = (b, lx, y1, y2) => lx >= b.x - PAD && lx <= b.x + b.width + PAD && b.y <= y2 && b.y + b.height >= y1;
const overlaps = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

// Подпись встаёт на первое место, где isFree(её рамка); если такого нет — на первое из списка.
function placeLabel(label, spots, isFree) {
  const put = ([x, y, anchor]) => {
    label.setAttribute("x", x);
    label.setAttribute("y", y);
    label.setAttribute("text-anchor", anchor);
  };
  const free = spots.find((spot) => {
    put(spot);
    return isFree(label.getBBox());
  });
  put(free || spots[0]);
}

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
  const curve = d.curve.map((c) => [x(c.price), y(c.profit)]);
  const points = curve.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  root.append(el("polygon", { class: "pc-area", points: `${x(d.min)},${y(0)} ${points} ${x(d.max)},${y(0)}` }));
  root.append(el("polyline", { class: "pc-line", points }));

  const bx = x(d.best), by = y(d.bestProfit);
  const cp = Math.max(d.min, Math.min(d.max, d.price)), cx = x(cp), cy = y(d.profit);
  root.append(el("line", { class: "pc-best-line", x1: bx, x2: bx, y1: by, y2: y(0) }));
  root.append(el("line", { class: "pc-cur-line", x1: cx, x2: cx, y1: cy, y2: y(0) }));
  root.append(el("circle", { class: "pc-best", cx: bx, cy: by, r: 5 }));
  root.append(el("circle", { class: "pc-cur", cx, cy, r: 4.5 }));
  const nearRight = bx > W - 110;
  const bestLabel = el("text", { class: "pc-label pc-label--best", x: bx + (nearRight ? -4 : 4), y: by - 10,
    "text-anchor": nearRight ? "end" : "start" }, `Макс · ${fmt(d.best)}`);
  const yours = el("text", { class: "pc-label pc-label--cur" }, `Ваша · ${fmt(d.price)}`);
  root.append(bestLabel, yours);
  root.append(el("text", { class: "pc-label", x: L, y: H - 6 }, fmt(d.min)));
  root.append(el("text", { class: "pc-label", x: W - R, y: H - 6, "text-anchor": "end" }, `${fmt(d.max)} ₽`));
  box.replaceChildren(root); // рамки подписей (getBBox) есть только у нарисованного SVG

  const bestBox = bestLabel.getBBox();
  const away = cx <= bx ? -1 : 1;
  const spots = ROWS.flatMap((dy) => [away, -away].map((side) => [cx + side * GAP, cy + dy, side > 0 ? "start" : "end"]));
  placeLabel(yours, spots, (b) => b.width > 0 && b.x >= L && b.x + b.width <= W && b.y >= 0 && b.y + b.height <= y(0) &&
    !curve.some((point) => near(b, point)) && !overlaps(b, bestBox) &&
    !crossesVertical(b, bx, by, y(0)) && !crossesVertical(b, cx, cy, y(0)) &&
    !near(b, [bx, by], 5) && !near(b, [cx, cy], 4.5));
}
