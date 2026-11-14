// График спроса по 9 сценариям (вёрстка из макета Claude Design).
// Столбик — «желают» в сценарии; выше линии мест — штриховка: этим людям не хватит кресел.
// Отрицательный спрос рисуется нулём, над столбиком мелко — значение по формуле.
import { fmt, whole } from "./format.js";
import { el, hatchDefs, niceScale } from "./svg.js";

const MEDIAN = 4;
const GAP = 2; // зазор между подписями соседних столбиков, px

// На узком графике (телефон) «997» и «1 039» над соседними столбиками налезают друг на друга:
// тогда подписи нечётных столбиков поднимаются над подписями соседей — соседи оказываются на разной высоте.
function separateValues(root) {
  const labels = [...root.querySelectorAll(".ch-val")];
  const boxes = labels.map((label) => label.getBBox());
  const clash = boxes.slice(1).some((b, i) => boxes[i].x + boxes[i].width + GAP > b.x);
  if (!clash) return;
  labels.forEach((label, i) => {
    if (i % 2 === 0) return;
    const top = Math.min(...[boxes[i - 1], boxes[i + 1]].filter(Boolean).map((b) => b.y));
    const lift = Math.max(0, boxes[i].y + boxes[i].height + GAP - top);
    for (const text of label.parentNode.querySelectorAll(".ch-val, .ch-raw")) {
      text.setAttribute("y", Number(text.getAttribute("y")) - lift);
    }
  });
}

export function drawQuantiles(box, { seats, quantiles }) {
  const W = box.clientWidth || 800;
  const H = box.clientHeight || 300;
  const compact = W < 500;
  // справа поле под подпись «Мест»: так она не налезает на столбик 0.9
  const L = compact ? 32 : 48, R = compact ? 38 : 64, T = 24, B = compact ? 42 : 46;
  const iw = W - L - R, ih = H - T - B;
  const top = Math.max(seats, ...quantiles.map((q) => Math.max(0, q))) * 1.08;
  const scale = niceScale(top);
  const y = (v) => T + ih * (1 - v / scale.max);
  const slot = iw / quantiles.length, bw = slot * (compact ? 0.66 : 0.5);

  const root = el("svg", { viewBox: `0 0 ${W} ${H}` });
  root.append(hatchDefs());
  for (let g = 0; g <= scale.max + 1e-9; g += scale.tick) {
    root.append(el("line", { class: "ch-grid", x1: L, x2: W - R, y1: y(g), y2: y(g) }));
    root.append(el("text", { class: "ch-tick", x: L - 6, y: y(g) + 4 }, fmt(g)));
  }
  root.append(el("line", { class: "ch-seats", x1: L, x2: W - R, y1: y(seats), y2: y(seats) }));
  quantiles.forEach((q, i) => {
    const v = Math.max(0, q), x = L + slot * i + (slot - bw) / 2, cx = x + bw / 2;
    const group = el("g", { class: i === MEDIAN ? "is-median" : "" });
    if (v > seats) {
      group.append(el("rect", { class: "ch-bar", x, y: y(seats), width: bw, height: y(0) - y(seats), rx: 2 }));
      group.append(el("rect", { class: "ch-hatch-box", x: x + 0.75, y: y(v) + 0.75, width: bw - 1.5,
        height: Math.max(0, y(seats) - y(v) - 1.5) }));
    } else if (v > 0) {
      group.append(el("rect", { class: "ch-bar", x, y: y(v), width: bw, height: y(0) - y(v), rx: 3 }));
    } else {
      group.append(el("rect", { class: "ch-bar", x, y: y(0) - 2, width: bw, height: 2 }));
    }
    group.append(el("text", { class: "ch-val", x: cx, y: y(v) - 7 }, whole(v)));
    if (q < 0) group.append(el("text", { class: "ch-raw", x: cx, y: y(v) - 24 }, whole(q)));
    group.append(el("text", { class: "ch-q", x: cx, y: H - B + 20 }, `0,${i + 1}`)); // квантиль с запятой, как в формуле
    if (i === MEDIAN) group.append(el("text", { class: "ch-median-label", x: cx, y: H - B + 35 }, "медиана"));
    root.append(group);
  });
  const label = el("text", { class: "ch-seats-label ch-seats-label--side", x: W - R + 6, y: y(seats) - 2 });
  label.append(el("tspan", { x: W - R + 6 }, "Мест"), el("tspan", { x: W - R + 6, dy: 13 }, whole(seats)));
  root.append(label);
  // подписи осей: слева над делениями — единицы, под подписями столбиков слева — что это за ряд
  root.append(el("text", { class: "ch-axis", x: 0, y: 11 }, "человек"));
  root.append(el("text", { class: "ch-axis", x: 0, y: H - B + 35 }, "сценарий"));
  box.replaceChildren(root);
  separateValues(root);
}
