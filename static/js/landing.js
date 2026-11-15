// Витрина /: пятницы июня и 9 сценариев 12 июня — с сервера (/api/story).
// Витрина открыта только после входа; «Открыть расчёт 12 июня» — ссылка на /app, «Выйти» — выход и /login.
import { get, post } from "./api.js";
import { drawQuantiles } from "./demand-chart.js";
import { dayMonth, dow, fmt, node, percent, rub, whole, withPercent } from "./format.js";

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
    `Медиана спроса при базовой цене. Пунктиром отмечено среднее по другим пятницам, ${whole(data.others_mean)}.`);
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
  setStory("source", story.source === "ml" ? "прогноз моей модели" : "прогноз организаторов");
  setStory("drop", `−${percent(story.drop)}`);
  setStory("summary", `медиана ${whole(story.median)} против ${whole(story.others_mean)} в\u00A0другие пятницы`);
  setStory("chart-title", `${story.route.origin} → ${story.route.destination} · ${dayMonth(story.date)} · ${rub(story.price)}`);
  // источник в дательном падеже после «по прогнозу»: «нашей ML-модели», а не «наша ml-модель»
  const source = story.source === "ml" ? "нашей ML-модели" : "организаторов";
  setStory("chart-how", `Девять сценариев спроса при базовой цене ${rub(story.price)} по прогнозу ${source}. ` +
    `С\u00A0вероятностью ${withPercent(80)} желающих будет от ${fmt(story.low)} до ${fmt(story.high)}, ` +
    `а\u00A0мест на всех рейсах дня ${whole(story.seats)}.`);
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

window.addEventListener("resize", drawStoryChart);
drawCapacityBars();
loadStory();

$("#logout").addEventListener("click", async (event) => {
  event.preventDefault();
  await post("/api/logout");
  location.assign("/login");
});
