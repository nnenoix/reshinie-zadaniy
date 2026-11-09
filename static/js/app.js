// Инструмент /app: форма с ползунком, расчёт, лучшая цена, салон, календарь, талон, история.
// Все числа приходят с сервера; здесь только показ. Вёрстка — pages/app.html, оформление — style.css.
import { get, latestOnly, post } from "./api.js";
import { downloadPdf, downloadPng, fillTicket, ticketData } from "./boarding-pass.js";
import { drawCalendar } from "./calendar.js";
import { drawQuantiles } from "./demand-chart.js";
import { dayMonth, dow, fmt, node, parsePrice, plural, rub, seatsText, shortDate, whole } from "./format.js";
import { drawProfit } from "./profit-chart.js";
import { drawQueue, drawSeats, salonText } from "./seat-map.js";

const STORY = { destination: "Санкт-Петербург", date: "2026-06-12" };
const SLIDER_DELAY_MS = 250;
const TABS = ["calc", "salon", "calendar", "ticket"];
const DOWN = ["Сервер прогноза не отвечает", "Параметры рейса сохранены. Попробуйте ещё раз через минуту."];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const form = $("#forecast-form");
const range = $("#price-range");
const priceInput = $("#price");
const result = $("#result");

// autoPrice: цену поставила страница (базовая цена маршрута), а не человек — при смене маршрута её можно менять.
const S = {
  sources: {}, origins: [], holidays: {}, forecast: null, curve: [], curveKey: "", calendarKey: "",
  scenario: 4, tab: "calc", autoPrice: true, timer: null,
};
const signals = { forecast: latestOnly(), curve: latestOnly(), calendar: latestOnly(), compare: latestOnly() };

// --- ошибки у полей ---

function clearErrors() {
  $$("[data-error-for]", form).forEach((slot) => { slot.hidden = true; slot.textContent = ""; });
  $$(".field.is-invalid", form).forEach((field) => field.classList.remove("is-invalid"));
  $('[data-error="general"]', form).hidden = true;
}

function showFieldError(data) {
  const detail = (data && data.detail) || "Что-то пошло не так. Попробуйте ещё раз.";
  const slot = data && data.field && $(`[data-error-for="${data.field}"]`, form);
  if (slot) {
    slot.textContent = detail;
    slot.hidden = false;
    slot.closest(".field").classList.add("is-invalid");
  }
  const general = $('[data-error="general"]', form);
  $("[data-error-text]", general).textContent = slot ? "Проверьте параметры рейса" : detail;
  general.hidden = false;
}

// --- состояния результата и вкладки ---

function setPanel(name) {
  $$("[data-panel]", result).forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
  $("#submit").disabled = name === "loading";
  $("[data-btn-text]", $("#submit")).textContent = name === "loading" ? "Считаем…" : "Рассчитать";
  const ready = name === "ready";
  $$("[data-needs-result]").forEach((part) => { part.hidden = !ready; });
  $$("[data-needs-empty]").forEach((part) => { part.hidden = ready; });
  $("#best").hidden = !ready;
}

function showError(code, title, text) {
  $("#error-code").textContent = `[ ${code} ]`;
  $("#error-title").textContent = title;
  $("#error-text").textContent = text;
  setPanel("error");
}

function setUpdating(on) {
  result.classList.toggle("is-updating", on);
  $(".side").classList.toggle("is-updating", on);
}

function setTab(name) {
  S.tab = name;
  $$(".tabs--main .tabs__btn").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  $$("[data-tabpanel]").forEach((panel) => { panel.hidden = panel.dataset.tabpanel !== name; });
  if (!S.forecast) return;
  if (name === "calc") drawDemand(S.forecast);
  if (name === "calendar") loadCalendar(S.forecast);
}

$$(".tabs--main .tabs__btn").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

// --- форма: источник, маршрут, дата, цена ---

function currentDestination() {
  const origin = S.origins.find((o) => o.name === form.elements.origin.value) || S.origins[0];
  return origin && origin.destinations.find((d) => d.name === form.elements.destination.value);
}

function setRange(min, max, value, best) {
  range.min = min;
  range.max = max;
  if (value !== null && Number.isFinite(value)) range.value = Math.max(min, Math.min(max, value));
  $("#range-min").textContent = rub(min);
  $("#range-max").textContent = rub(max);
  range.style.setProperty("--fill", `${((range.value - min) / (max - min)) * 100}%`);
  const marker = $("#range-best");
  marker.hidden = best === null || best === undefined;
  if (!marker.hidden) {
    marker.style.setProperty("--best", (best - min) / (max - min));
    $("#range-best-label").textContent = `▲ ЛУЧШАЯ ${fmt(best)}`;
  }
}

function setPrice(value) {
  const number = Number(parsePrice(value));
  priceInput.value = Number.isFinite(number) && String(value).trim() !== "" ? fmt(number, 2) : String(value);
  const destination = currentDestination();
  if (destination && Number.isFinite(number)) {
    setRange(destination.price_min, destination.price_max, number, bestFor(destination));
  }
}

function bestFor(destination) {
  const d = S.forecast;
  return d && d.route.destination === destination.name && d.date === form.elements.date.value ? d.best.price : null;
}

function updateDateHint() {
  const destination = currentDestination();
  const day = form.elements.date.value;
  if (!destination || !day) return;
  const holiday = S.holidays[day];
  $("#date-hint").textContent = `${dow(day)}${holiday ? ` · ${holiday.toUpperCase()}` : ""} · ДОСТУПНО ` +
    `${dayMonth(destination.first_date)} — ${shortDate(destination.last_date)}`;
}

function onDestinationChange() {
  const destination = currentDestination();
  if (!destination) return;
  const { date } = form.elements;
  date.min = destination.first_date;
  date.max = destination.last_date;
  if (!date.value || date.value < date.min || date.value > date.max) date.value = destination.first_date;
  setPrice(S.autoPrice || !priceInput.value ? destination.base_price : priceInput.value);
  updateDateHint();
}

function fillDestinations(wanted) {
  const origin = S.origins[0];
  form.elements.origin.value = origin.name;
  const select = form.elements.destination;
  select.replaceChildren(...origin.destinations.map((d) => new Option(d.name, d.name)));
  if (origin.destinations.some((d) => d.name === wanted)) select.value = wanted;
  onDestinationChange();
}

async function loadSources() {
  const response = await get("/api/sources");
  if (!response.ok) return;
  S.sources = Object.fromEntries(response.data.sources.map((s) => [s.id, s]));
  for (const option of form.elements.source.options) {
    const source = S.sources[option.value];
    option.disabled = !source || !source.available;
  }
  const ml = S.sources.ml;
  $("#source-hint").textContent = ml && !ml.available ? ml.detail.toUpperCase() : sourceHint();
}

function sourceHint() {
  const source = S.sources[form.elements.source.value];
  return source ? `${source.file} · ${source.detail}`.toUpperCase() : "";
}

async function loadRoutes(source, wanted) {
  const keep = wanted || form.elements.destination.value || STORY.destination;
  const response = await get("/api/routes", source ? { source } : {});
  if (!response.ok) {
    showFieldError(response.data);
    return false;
  }
  S.origins = response.data.origins;
  S.holidays = response.data.holidays;
  form.elements.source.value = response.data.source;
  $("#source-hint").textContent = sourceHint();
  fillDestinations(keep);
  return true;
}

function readQuery() {
  return {
    source: form.elements.source.value,
    origin: form.elements.origin.value,
    destination: form.elements.destination.value,
    date: form.elements.date.value,
    price: parsePrice(priceInput.value),
  };
}

range.addEventListener("input", () => {
  S.autoPrice = false;
  setPrice(range.value);
  clearTimeout(S.timer);
  S.timer = setTimeout(() => calculate({ live: true }), SLIDER_DELAY_MS);
});
priceInput.addEventListener("input", () => { S.autoPrice = false; });
priceInput.addEventListener("blur", () => {
  if (Number.isFinite(Number(parsePrice(priceInput.value)))) setPrice(priceInput.value);
});
form.elements.destination.addEventListener("change", () => {
  onDestinationChange();
  calculate({ live: true });
});
form.elements.date.addEventListener("change", () => {
  updateDateHint();
  calculate({ live: true });
});
form.elements.source.addEventListener("change", async () => {
  if (await loadRoutes(form.elements.source.value)) calculate({ live: true });
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  calculate({ save: true });
});
$("#retry").addEventListener("click", () => calculate({}));
$("#apply-best").addEventListener("click", () => {
  if (!S.forecast) return;
  S.autoPrice = false;
  setPrice(S.forecast.best.price);
  calculate({ save: true, live: true });
});

// --- расчёт ---

async function calculate({ save = false, live = false }) {
  clearErrors();
  if (live && S.forecast) setUpdating(true);
  else setPanel("loading");
  const response = await post("/api/forecast", { ...readQuery(), save }, signals.forecast());
  if (response.aborted) return;
  setUpdating(false);
  if (response.status === 401) return location.assign("/login");
  if (response.status === 0 || response.status >= 500) return showError(response.status || 503, ...DOWN);
  if (!response.ok) {
    showFieldError(response.data);
    if (response.data && response.data.field === "date") return showMissingFlight(response.data.detail);
    setPanel(S.forecast ? "ready" : "empty");
    return;
  }
  render(response.data);
  if (save) refreshHistory();
}

// Рейса на эту дату нет: старый результат прячем, чтобы его не приняли за ответ на новый запрос.
function showMissingFlight(detail) {
  const { origin, destination, date } = readQuery();
  const day = /^\d{4}-\d{2}-\d{2}$/.test(date) ? ` на ${shortDate(date)}` : "";
  showError(422, `Рейса ${origin} → ${destination}${day} нет`, detail);
}

function render(d) {
  S.forecast = d;
  const want = Math.max(0, d.wanted);
  const out = (key) => $(`[data-out="${key}"]`, result);
  out("seats").textContent = whole(d.seats);
  out("want").textContent = fmt(want);
  out("buy").textContent = fmt(d.sold);
  out("load").textContent = whole(d.load * 100);
  out("wantRaw").hidden = d.wanted >= 0;
  out("wantRaw").textContent = `по формуле ${fmt(d.wanted)}`;
  $("#load-meter").style.setProperty("--p", `${Math.min(100, d.load * 100)}%`);
  renderNote(d, want);
  renderFormula(d);
  renderRoute(d);

  const quantiles = d.scenarios.map((s) => s.wanted);
  const over = quantiles.filter((q) => q > d.seats).length;
  $("#chart-title").textContent = `Спрос при цене ${rub(d.price)} по 9 сценариям`;
  $("#legend-hatch").hidden = !over;
  $("#chart-how").textContent = d.sold <= 0
    ? "При такой цене формула даёт отрицательный спрос. Отрицательных покупателей не бывает, поэтому столбики " +
      "равны 0; над ними мелко — значение по формуле."
    : over
      ? `Заштрихованная часть — желающие, которым не хватит кресел: так выходит в ${over} ` +
        `${plural(over, ["сценарии", "сценариях", "сценариях"])} из 9. Слева пессимистичный сценарий 0.1, справа оптимистичный 0.9.`
      : "Каждый столбик — сколько человек захотят купить билет в одном из 9 сценариев: слева пессимистичный (0.1), " +
        "справа оптимистичный (0.9). Выделенный столбик — медиана, её мы показываем как «желают».";

  setPanel("ready");
  setRange(d.route.price_min, d.route.price_max, d.price, d.best.price);
  renderBest(d);
  renderSalon(d);
  fillTicket($("#ticket"), ticketData(d));
  if (S.tab === "calc") drawDemand(d);
  if (S.tab === "calendar") loadCalendar(d);
  refreshCurve(d);
  refreshCompare(d);
}

function drawDemand(d) {
  drawQuantiles($("#chart"), { seats: d.seats, quantiles: d.scenarios.map((s) => s.wanted) });
}

function renderRoute(d) {
  const arrow = node("span", "accent", "→");
  $("#result-route").replaceChildren(`${d.route.origin} `, arrow,
    ` ${d.route.destination} · ${shortDate(d.date)} · ${rub(d.price)}`);
}

function renderNote(d, want) {
  const capped = d.wanted > d.seats, none = d.sold <= 0;
  $("#note").className = `note ${capped ? "note--cap" : none ? "note--neg" : "note--ok"}`;
  const tag = $("#note-tag");
  tag.className = `tag${none ? " tag--err" : ""}`;
  if (capped) {
    tag.textContent = "УПОР В МЕСТА";
    $("#note-text").textContent = `Желают ${fmt(want)}, а мест ${whole(d.seats)} — купят ${fmt(d.sold)}. ` +
      `Не хватит мест для ${fmt(d.wanted - d.seats)} желающих.`;
  } else if (none) {
    tag.textContent = "НЕТ СПРОСА";
    $("#note-text").textContent = `При цене ${rub(d.price)} желающих нет: формула даёт ${fmt(d.wanted)}. ` +
      "Попробуйте снизить цену.";
  } else {
    tag.textContent = `ЗАПАС ${seatsText(d.seats - want).toUpperCase()}`;
    $("#note-text").textContent = "Продажи не упираются в число мест: желающих меньше, чем кресел.";
  }
}

function renderFormula(d) {
  const median = d.scenarios[4];
  $("#formula").textContent =
    `желают = ${fmt(median.base_demand)} − ${String(d.route.price_sensitivity).replace(".", ",")} × ` +
    `(${fmt(d.price, 2)} − ${fmt(d.route.base_price)}) = ${fmt(d.wanted, 2)} · ` +
    `купят = min(${whole(d.seats)}, max(0, ${fmt(d.wanted, 2)})) = ${fmt(d.sold, 2)}`;
}

// --- лучшая цена ---

function renderBest(d) {
  const { best } = d;
  $("#best-price").textContent = fmt(best.price);
  $("#apply-best-price").textContent = `${rub(best.price)} →`;
  const gain = Math.round(best.gain || 0);
  const text = $("#best-text");
  if (gain <= 0) {
    text.replaceChildren(`Ваша цена ${rub(d.price)} уже даёт максимум ожидаемой прибыли.`);
  } else {
    text.replaceChildren(`Лучшая цена ${rub(best.price)} — это `, node("b", "", `+${rub(gain)}`),
      " ожидаемой прибыли к вашей цене.");
  }
  let note = "Ожидаемая прибыль — среднее по 9 сценариям от (цена − расходы на пассажира) × купят. " +
    "Кривую и максимум считает сервер.";
  if (best.file_price !== null) {
    note += ` В файле прогноза для медианного сценария указана цена ${rub(best.file_price)} (0.5_price), ` +
      "а лучшая цена здесь подобрана под все девять сценариев.";
  }
  $("#best-note").textContent = note;
}

async function refreshCurve(d) {
  const key = `${d.source}|${d.route.code}|${d.date}`;
  if (key !== S.curveKey) {
    const response = await get("/api/best-price", {
      source: d.source, origin: d.route.origin, destination: d.route.destination, date: d.date,
    }, signals.curve());
    if (!response.ok) return;
    S.curve = response.data.curve;
    S.curveKey = key;
  }
  drawCurve();
}

function drawCurve() {
  const d = S.forecast;
  if (!d) return;
  drawProfit($("#profit-chart"), {
    curve: S.curve, min: d.route.price_min, max: d.route.price_max,
    best: d.best.price, bestProfit: d.best.expected.profit, price: d.price, profit: d.expected.profit,
  });
}

// --- сравнение прогнозов ---

async function refreshCompare(d) {
  const ml = S.sources.ml;
  $("#compare-meta").textContent = `${shortDate(d.date)} · ${rub(d.price)}`;
  if (!ml || !ml.available) {
    $("#compare-table").hidden = true;
    $("#compare-note").textContent = `Сравнение появится, когда будет файл нашей модели. ${ml ? ml.detail : ""}`;
    return;
  }
  const response = await get("/api/compare", {
    origin: d.route.origin, destination: d.route.destination, date: d.date, price: d.price,
  }, signals.compare());
  if (!response.ok) return;
  $("#compare-body").replaceChildren(...response.data.sources.map((s) => {
    const row = document.createElement("tr");
    if (s.source === d.source) row.className = "is-current";
    const f = s.forecast;
    const cells = f
      ? [[s.name, "l"], [fmt(Math.max(0, f.wanted))], [fmt(f.sold)], [`${whole(f.load * 100)} %`], [whole(f.best_price)]]
      : [[s.name, "l"], [s.detail], [""], [""], [""]];
    row.replaceChildren(...cells.map(([text, cls]) => node("td", cls, text)));
    return row;
  }));
  $("#compare-table").hidden = false;
  $("#compare-note").textContent = "Одна и та же цена, два прогноза спроса. Выделен прогноз, по которому посчитан расчёт выше.";
}

// --- салон ---

function buildScenarioButtons() {
  const group = $("#scen");
  for (let i = 0; i < 9; i++) {
    const button = node("button", `scen__btn${i === 4 ? " is-median" : ""}`, `0.${i + 1}`);
    button.type = "button";
    button.dataset.q = i;
    button.setAttribute("aria-pressed", String(i === S.scenario));
    group.append(button);
  }
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-q]");
    if (!button) return;
    S.scenario = Number(button.dataset.q);
    $$("[data-q]", group).forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    if (S.forecast) renderSalon(S.forecast);
  });
}

function renderSalon(d) {
  const cabin = d.seat_map;
  const scenario = d.scenarios[S.scenario];
  const sold = scenario.sold;
  const over = Math.max(0, scenario.wanted - d.seats);
  drawSeats($("#seats"), cabin, sold);
  const queue = drawQueue($("#queue"), cabin, over);
  $("#queue-title").hidden = !queue.shown;
  $("#queue-title").textContent = `НЕ ХВАТИЛО МЕСТ · ${fmt(over)}`;
  $('[data-salon="seats"]').textContent = whole(d.seats);
  $('[data-salon="sold"]').textContent = fmt(sold);
  $('[data-salon="over"]').textContent = fmt(over);
  const { scale, text } = salonText(cabin, `0.${S.scenario + 1}`, scenario.wanted, sold, over, queue);
  $("#salon-how").replaceChildren(node("strong", "", scale), text);
}

// --- календарь ---

async function loadCalendar(d) {
  const key = `${d.source}|${d.route.code}|${d.price}`;
  if (key === S.calendarKey) {
    $$(".cal__day[data-date]").forEach((c) => c.classList.toggle("is-selected", c.dataset.date === d.date));
    return;
  }
  $("#cal-title").textContent = `Июнь 2026 · ${d.route.origin} → ${d.route.destination} · ${rub(d.price)}`;
  const response = await get("/api/calendar", {
    source: d.source, origin: d.route.origin, destination: d.route.destination, price: d.price,
  }, signals.calendar());
  if (response.aborted) return;
  if (!response.ok) {
    $("#cal").replaceChildren(node("p", "panel-empty", "Не удалось загрузить календарь. Попробуйте позже."));
    return;
  }
  S.calendarKey = key;
  const loads = drawCalendar($("#cal"), response.data.days, { selected: d.date, onPick: pickDay });
  $("#cal-min").textContent = `${loads.min} %`;
  $("#cal-max").textContent = `${loads.max} %`;
  $("#cal-how").textContent = `Цвет — загрузка при цене ${rub(d.price)}: от самого слабого дня месяца (${loads.min} %) ` +
    `до самого сильного (${loads.max} %). Нажмите на день — откроется расчёт на эту дату.`;
}

function pickDay(day) {
  form.elements.date.value = day;
  updateDateHint();
  setTab("calc");
  calculate({ save: true, live: true });
}

// --- талон ---

async function exportTicket(kind) {
  const error = $("#ticket-error");
  error.hidden = true;
  if (!S.forecast) return;
  const name = `talon-${ticketData(S.forecast).id}`;
  try {
    if (kind === "png") await downloadPng($("#ticket"), `${name}.png`);
    else await downloadPdf($("#ticket"), `${name}.pdf`);
  } catch (problem) {
    error.textContent = problem.message;
    error.hidden = false;
  }
}

$("#dl-png").addEventListener("click", () => exportTicket("png"));
$("#dl-pdf").addEventListener("click", () => exportTicket("pdf"));

// --- история ---

async function refreshHistory() {
  const response = await get("/api/history", { limit: 5 });
  if (!response.ok) return;
  const items = response.data.items;
  if (!items.length) return;
  $("#history-body").replaceChildren(...items.map(historyRow));
}

function timeOf(iso) {
  const when = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const time = when.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const today = new Date().toDateString() === when.toDateString();
  return today ? time : `${when.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })} ${time}`;
}

function historyRow(entry) {
  const want = Math.max(0, entry.wanted);
  const row = document.createElement("tr");
  const route = node("td", "l route", `${entry.origin} `);
  route.append(node("span", "accent", "→"), ` ${entry.destination}`,
    node("span", "history__src", entry.source === "ml" ? "ML" : "ОРГ"));
  const flag = node("td");
  if (want > entry.seats) flag.append(node("span", "tag", "УПОР В МЕСТА"));
  else if (entry.sold <= 0) flag.append(node("span", "tag tag--err", "НЕТ СПРОСА"));
  const again = node("button", "link-btn", "Повторить →");
  again.type = "button";
  again.addEventListener("click", () => repeat(entry));
  flag.append(again);
  row.append(node("td", "l time", timeOf(entry.created_at)), route, node("td", "l", shortDate(entry.date)),
    node("td", "", fmt(entry.price, 2)), node("td", "", whole(entry.seats)), node("td", "", fmt(want)),
    node("td", "buy", fmt(entry.sold)), node("td", "", `${whole(entry.load * 100)} %`), flag);
  return row;
}

async function repeat(entry) {
  if (form.elements.source.value !== entry.source) {
    form.elements.source.value = entry.source;
    if (!(await loadRoutes(entry.source))) return;
  }
  form.elements.destination.value = entry.destination;
  form.elements.date.value = entry.date;
  S.autoPrice = false;
  onDestinationChange();
  setPrice(entry.price);
  setTab("calc");
  calculate({ save: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// --- выход и запуск ---

$("#logout").addEventListener("click", async (event) => {
  event.preventDefault();
  await post("/api/logout");
  location.assign("/login");
});

window.addEventListener("resize", () => {
  if (!S.forecast) return;
  if (S.tab === "calc") drawDemand(S.forecast);
  drawCurve();
});

async function start() {
  const me = await get("/api/me");
  if (me.status === 401) return location.assign("/login");
  if (me.ok) $("#user-login").textContent = me.data.login;
  buildScenarioButtons();
  await loadSources();
  const params = new URLSearchParams(location.search);
  if (!(await loadRoutes(params.get("source"), params.get("destination")))) return setPanel("empty");
  form.elements.date.value = params.get("date") || STORY.date;
  if (params.get("price")) {
    S.autoPrice = false;
    setPrice(params.get("price"));
  }
  onDestinationChange();
  const tab = params.get("tab");
  setTab(TABS.includes(tab) ? tab : "calc");
  refreshHistory();
  calculate({}); // при открытии страницы расчёт не пишется в историю: её пополняют «Рассчитать» и действия человека
}

start();
