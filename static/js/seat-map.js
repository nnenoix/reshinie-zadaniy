// Схема салона и очередь у трапа (вёрстка из макета Claude Design).
// Масштаб приходит с сервера (app/seatmap.py): одно кресло — 1, 2, 5, 10, 20 или 50 мест,
// кресел не больше 150, последнее может вмещать меньше. Кресло закрашено по доле проданных мест.
import { node, plural, whole } from "./format.js";

// cabin — seat_map из ответа /api/forecast; sold и over — для выбранного сценария.
export function drawSeats(grid, cabin, sold) {
  const N = cabin.seats_per_icon;
  const seats = [];
  for (let k = 0; k < cabin.icons_total; k++) {
    if (k % 6 === 3) seats.push(document.createElement("span")); // проход между креслами
    const capacity = k === cabin.icons_total - 1 ? cabin.last_icon_seats : N;
    const fill = Math.max(0, Math.min(1, (sold - k * N) / capacity));
    const seat = node("span", `seat${fill >= 1 ? " is-sold" : fill > 0 ? " is-part" : ""}`);
    if (fill > 0 && fill < 1) seat.style.setProperty("--f", `${Math.round(fill * 100)}%`);
    seats.push(seat);
  }
  grid.replaceChildren(...seats);
}

// Возвращает, сколько фигурок нарисовано и все ли поместились.
export function drawQueue(queue, cabin, over) {
  const N = cabin.seats_per_icon;
  const needed = Math.ceil(over / N - 1e-9);
  const shown = Math.min(needed, cabin.max_waiting_icons);
  const people = [];
  for (let j = 0; j < shown; j++) {
    const person = node("span", "person");
    const part = Math.min(1, over / N - j);
    if (part < 1) person.style.setProperty("--f", `${Math.round(part * 100)}%`);
    people.push(person);
  }
  queue.replaceChildren(...people);
  return { shown, capped: needed > shown };
}

export function salonText(cabin, scenarioLabel, wanted, sold, over, queue) {
  const N = cabin.seats_per_icon;
  const icons = cabin.icons_total;
  const scale = `1 кресло = ${N} ${plural(N, ["место", "места", "мест"])}, ` +
    `1 человечек = ${N} ${plural(N, ["человек", "человека", "человек"])}.`;
  let text = ` На рейсах дня ${whole(cabin.seats)} ${plural(cabin.seats, ["место", "места", "мест"])} — это ${icons} ` +
    `${plural(icons, ["значок", "значка", "значков"])}` +
    (cabin.last_icon_seats !== N ? `, последний вмещает ${cabin.last_icon_seats}` : "") + ".";
  if (cabin.more_than_one_aircraft) {
    text += " Это больше, чем в самом вместительном самолёте (A380, до 853 мест), значит, в данных сумма " +
      "по нескольким рейсам дня. Схема показывает их одним салоном.";
  }
  text += ` Сценарий ${scenarioLabel}: желают ${whole(Math.max(0, wanted))}. `;
  text += over > 0
    ? `Не хватило мест ${whole(over)} желающим — это ${queue.shown} ${plural(queue.shown, ["значок", "значка", "значков"])}` +
      (queue.capped ? ` (показана часть очереди, всего нужно ${Math.ceil(over / N)})` : "") + "."
    : `Мест хватило всем, свободно ${whole(cabin.seats - sold)}.`;
  return { scale, text };
}
