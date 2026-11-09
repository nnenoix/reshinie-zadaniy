// Числа и даты по-русски, как в макете: «1 440», «917,3», «−494», «12.06.2026», «ПТ».

const DOW = ["ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"];

// Округляет до digits знаков, группирует тысячи неразрывным пробелом, минус — «−».
export function fmt(value, digits = 1) {
  const factor = 10 ** digits;
  const rounded = Math.round(Number(value) * factor) / factor;
  const abs = Math.abs(rounded);
  const [int, frac] = (Number.isInteger(abs) ? String(abs) : abs.toFixed(digits)).split(".");
  const fraction = frac ? frac.replace(/0+$/, "") : "";
  return (rounded < 0 ? "−" : "") + int.replace(/\B(?=(\d{3})+(?!\d))/g, " ") + (fraction ? `,${fraction}` : "");
}

export const whole = (value) => fmt(value, 0);
export const rub = (value) => `${whole(value)} ₽`;
export const signedRub = (value) => `${value > 0 ? "+" : ""}${rub(value)}`;
export const percent = (share) => `${whole(share * 100)} %`;

// «5 500 ₽», «5500,5» → «5500.5»: так цену понимает сервер.
export function parsePrice(text) {
  return String(text).replace(/[\s ₽]/g, "").replace(",", ".");
}

export function shortDate(iso) {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

export function dayMonth(iso) {
  const [, month, day] = iso.split("-");
  return `${day}.${month}`;
}

export function dateOf(iso) {
  return new Date(`${iso}T12:00:00`);
}

export function dow(iso) {
  return DOW[dateOf(iso).getDay()];
}

export function airportCodes(routeCode) {
  const [from, to] = routeCode.split("-");
  return { from, to };
}

// plural(5, ["место", "места", "мест"]) → «мест»
export function plural(n, [one, few, many]) {
  const tens = Math.abs(n) % 100;
  const units = tens % 10;
  if (tens > 10 && tens < 20) return many;
  if (units === 1) return one;
  if (units >= 2 && units <= 4) return few;
  return many;
}

// «523 места», «1 440 мест»; дробное — «523,5 места».
export function seatsText(n) {
  return `${fmt(n)} ${Number.isInteger(Math.round(n * 10) / 10) ? plural(Math.round(n), ["место", "места", "мест"]) : "места"}`;
}

// Элемент с классом и текстом: разметку собираем без innerHTML.
export function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
