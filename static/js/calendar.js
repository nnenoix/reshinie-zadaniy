// Календарь загрузки на месяц (вёрстка из макета Claude Design).
// Цвет клетки — загрузка при выбранной цене. Шкала идёт от самого слабого дня месяца
// до самого сильного: так на рейсе в Петербург видно, что 12 июня бледнее соседних пятниц.
import { dateOf, fmt, node, shortDate, withPercent } from "./format.js";

const WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const PALEST = 8, DARK_FROM = 78; // доля акцентного цвета, %: у самого слабого дня и с которой текст белый

export function loadRange(days) {
  const loads = days.map((d) => Math.round(d.load * 100));
  return { min: Math.min(...loads), max: Math.max(...loads) };
}

export function shade(loadPercent, { min, max }) {
  const k = max > min ? (loadPercent - min) / (max - min) : 1;
  return Math.round(PALEST + Math.max(0, Math.min(1, k)) * (100 - PALEST));
}

export function drawCalendar(box, days, { selected, onPick }) {
  const range = loadRange(days);
  const cells = WEEK.map((name) => node("span", `cal__dow${name === "Пт" ? " is-fri" : ""}`, name));
  const lead = (dateOf(days[0].date).getDay() + 6) % 7;
  for (let i = 0; i < lead; i++) cells.push(document.createElement("span"));
  const month = dateOf(days[0].date).getMonth();

  for (const day of days) {
    const pct = Math.round(day.load * 100);
    const mix = shade(pct, range);
    const date = dateOf(day.date);
    const cell = node("button", "cal__day" + (mix >= DARK_FROM ? " is-dark" : "") + (day.is_friday ? " is-fri" : "") +
      (day.sold_out ? " is-capped" : "") + (day.date === selected ? " is-selected" : ""));
    cell.type = "button";
    cell.dataset.date = day.date;
    cell.style.setProperty("--mix", `${mix}%`);
    cell.setAttribute("aria-label", `${shortDate(day.date)}, загрузка ${withPercent(pct)}` +
      (day.sold_out ? ", упор в места" : "") + (day.holiday ? `, ${day.holiday}` : ""));

    const topRow = node("span", "cal__top");
    const label = date.getMonth() === month ? String(date.getDate()) : `${date.getDate()}.${String(date.getMonth() + 1).padStart(2, "0")}`;
    topRow.append(node("span", "cal__date", label));
    if (day.holiday) {
      const holiday = node("span", "cal__hol");
      day.holiday.split(" ").forEach((word, i) => {
        if (i) holiday.append(document.createElement("br"));
        holiday.append(word);
      });
      topRow.append(holiday);
    }
    const bottomRow = node("span", "cal__bottom");
    const load = node("span", "cal__load", fmt(pct, 0));
    load.append(node("small", "", "%"));
    bottomRow.append(load);
    if (day.sold_out) bottomRow.append(node("span", "cal__cap", "Упор"));
    cell.append(topRow, bottomRow);
    cell.addEventListener("click", () => onPick(day.date));
    cells.push(cell);
  }

  // Пустые клетки до конца недели — следующие дни, которых нет в прогнозе.
  const next = dateOf(days[days.length - 1].date);
  for (let total = lead + days.length; total % 7; total++) {
    next.setDate(next.getDate() + 1);
    const off = node("span", "cal__day is-off");
    off.append(node("span", "cal__date", String(next.getDate())));
    cells.push(off);
  }
  box.replaceChildren(...cells);
  return range;
}
