// Витрина /: пятницы июня и 9 сценариев 12 июня — с сервера (/api/story), кнопки входа в инструмент.
import { get } from "./api.js";
import { drawQuantiles } from "./demand-chart.js";
import { dayMonth, dow, fmt, node, rub, whole } from "./format.js";
import { ensureSession, enterAsGuest } from "./guest.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let story = null;

function setStory(key, text) {
  $$(`[data-story="${key}"]`).forEach((field) => { field.textContent = text; });
}

// Столбики от нуля: длина честно отвечает спросу; пунктир — среднее других пятниц.
function drawFridays(box, data) {
  const top = Math.ceil((Math.max(...data.fridays.map((f) => f.median)) * 1.12) / 100) * 100;
  const rows = data.fridays.map((friday) => {
    const row = node("div", `fri__row${friday.is_story_day ? " is-story" : ""}`);
    const track = node("span", "fri__track");
    const fill = node("span", "fri__fill");
    fill.style.setProperty("--w", `${(friday.median / top) * 100}%`);
    const mean = node("span", "fri__mean");
    mean.style.setProperty("--m", `${(data.others_mean / top) * 100}%`);
    track.append(fill, mean);
    row.append(node("span", "", `${dow(friday.date)} ${dayMonth(friday.date)}`), track,
      node("span", "fri__value", whole(friday.median)));
    return row;
  });
  const legend = node("p", "fri__legend",
    `МЕДИАНА СПРОСА ПО БАЗОВОЙ ЦЕНЕ · ПУНКТИР — СРЕДНЕЕ ДРУГИХ ПЯТНИЦ, ${whole(data.others_mean)}`);
  box.replaceChildren(...rows, legend);
}

function drawStoryChart() {
  if (!story) return;
  drawQuantiles($("#story-chart"), { seats: story.seats, quantiles: story.scenarios.map((s) => s.wanted) });
}

async function loadStory() {
  const response = await get("/api/story");
  if (!response.ok) {
    $("#story-fridays").replaceChildren(node("p", "fri__empty", "Прогноз по пятницам сейчас недоступен."));
    return;
  }
  story = response.data;
  setStory("source", story.source_name);
  setStory("drop", `−${whole(story.drop * 100)} %`);
  setStory("summary", `медиана ${whole(story.median)} против ${whole(story.others_mean)} в другие пятницы`);
  setStory("chart-title", `[ ${story.route.origin} → ${story.route.destination} / ${dayMonth(story.date)} / ${rub(story.price)} ]`);
  setStory("chart-how", `Девять сценариев спроса при базовой цене ${rub(story.price)}, источник: ` +
    `${story.source_name.toLowerCase()}. Коридор 10–90 %: от ${fmt(story.low)} до ${fmt(story.high)} желающих ` +
    `при ${whole(story.seats)} местах. Лучшая цена по ожидаемой прибыли — ${rub(story.best.price)}.`);
  drawFridays($("#story-fridays"), story);
  drawStoryChart();
}

// Полоса «желают / мест» из макета: заполнение и места задаются через CSS-переменные.
function drawCapacityBars() {
  $$("[data-cbar]").forEach((bar) => {
    const want = Number(bar.dataset.want), seats = Number(bar.dataset.seats), max = Number(bar.dataset.max);
    bar.style.setProperty("--w", `${(Math.min(want, seats) / max) * 100}%`);
    bar.style.setProperty("--s", `${(seats / max) * 100}%`);
  });
}

function showGuestError(data) {
  const slot = $("[data-guest-error]");
  slot.textContent = data.detail;
  slot.hidden = false;
}

$$("[data-guest]").forEach((button) => button.addEventListener("click", async () => {
  const response = await enterAsGuest();
  if (response.ok) location.assign("/app");
  else showGuestError(response.data);
}));

$$("[data-open-story]").forEach((link) => link.addEventListener("click", async (event) => {
  event.preventDefault();
  const response = await ensureSession();
  if (response.ok) location.assign(link.getAttribute("href"));
  else showGuestError(response.data);
}));

window.addEventListener("resize", drawStoryChart);
drawCapacityBars();
loadStory();
