// Общие помощники для SVG-графиков. Оформление — только через классы в style.css.

export const SVG_NS = "http://www.w3.org/2000/svg";

export function el(name, attrs = {}, text) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  if (text !== undefined) element.textContent = text;
  return element;
}

// Верх оси и шаг делений: самый мелкий «круглый» шаг (1, 2, 2.5, 5 × 10^n), при котором делений не больше пяти.
// Начинаем на порядок ниже, чем в макете: иначе при спросе около 1 100 ось уходила до 2 000.
export function niceScale(top) {
  const step = 10 ** (Math.floor(Math.log10(top || 1)) - 1);
  for (const factor of [1, 2, 2.5, 5, 10, 20, 25, 50, 100]) {
    const tick = factor * step;
    const max = Math.ceil(top / tick) * tick;
    if (max / tick <= 5) return { max, tick };
  }
  return { max: Math.ceil(top / step) * step, tick: step };
}

// Узоры штриховки «сверх мест»; цвет линии задают классы .hatch-line--other и .hatch-line--median.
export function hatchDefs() {
  const defs = el("defs");
  for (const kind of ["other", "median"]) {
    const pattern = el("pattern", { id: `hatch-${kind}`, width: 6, height: 6, patternUnits: "userSpaceOnUse",
      patternTransform: "rotate(45)" });
    pattern.append(el("line", { class: `hatch-line hatch-line--${kind}`, x1: 0, y1: 0, x2: 0, y2: 6 }));
    defs.append(pattern);
  }
  return defs;
}
