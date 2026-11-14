// Инструмент /app: форма с ползунком, расчёт, лучшая цена, салон, календарь, талон, история.
// Все числа приходят с сервера; здесь только показ. Вёрстка — pages/app.html, оформление — style.css.
import { get, latestOnly, post } from "./api.js";
import { downloadPdf, downloadPng, fillTicket, ticketData } from "./boarding-pass.js";
import { drawCalendar } from "./calendar.js";
import { drawQuantiles } from "./demand-chart.js";
import { dayMonth, dow, fmt, node, oddsText, parsePrice, percent, plural, rub, seatsText, shortDate, whole, withPercent } from "./format.js";
import { drawProfit } from "./profit-chart.js";
import { drawQueue, drawSeats, salonText } from "./seat-map.js";

const SLIDER_DELAY_MS = 250;
const TABS = ["calc", "salon", "calendar", "ticket"];
const DOWN = ["Сервер прогноза не отвечает", "Параметры рейса сохранены. Попробуйте ещё раз через минуту."];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const form = $("#forecast-form");
// Рейс по умолчанию — Москва → Санкт-Петербург, 12 июня — записан в pages/app.html: страница
// приходит с ним и с «Сервер считает…», не дожидаясь маршрутов. Параметры из адреса важнее.
const STORY = { destination: form.elements.destination.value, date: form.elements.date.value };
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

function setBusy(on) {
  $("#submit").disabled = on;
  $("[data-btn-text]", $("#submit")).textContent = on ? "Считаем…" : "Рассчитать";
}

function setPanel(name) {
  $$("[data-panel]", result).forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
  setBusy(name === "loading");
  const ready = name === "ready";
  $$("[data-needs-result]").forEach((part) => { part.hidden = !ready; });
  $$("[data-needs-empty]").forEach((part) => { part.hidden = ready; });
  $("#best").hidden = !ready;
}

// code — номер ошибки сервера, мелко, для поддержки; у ошибки в параметрах рейса его нет: менеджеру он ничего не скажет.
// retry — кнопка «Повторить расчёт»; её нет, когда повтор даст тот же ответ.
function showError({ code = null, title, text, retry = true }) {
  $("#error-code").textContent = code ? `Ошибка ${code}` : "";
  $("#error-title").textContent = title;
  $("#error-text").textContent = text;
  $("#retry").hidden = !retry;
  setPanel("error");
}

// Старый результат приглушён, пока считается новый: колонка не схлопывается в заготовку и не прыгает.
function setUpdating(on) {
  result.classList.toggle("is-updating", on);
  $("#best").classList.toggle("is-updating", on);
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
    $("#range-best-label").textContent = `▲ Лучшая ${fmt(best)}`;
  }
}

// Положительная цена приводится к виду «5 500», ползунок встаёт на неё. Ноль, минус и не-число
// остаются как введены: сервер ответит, что не так, и человек увидит свой ввод.
// Цена вне диапазона маршрута тоже не меняется молча: под полем сказано, каков диапазон.
function setPrice(value) {
  const number = Number(parsePrice(value));
  const valid = Number.isFinite(number) && number > 0 && String(value).trim() !== "";
  priceInput.value = valid ? fmt(number, 2) : String(value);
  const destination = currentDestination();
  const outside = Boolean(destination && valid && (number < destination.price_min || number > destination.price_max));
  $("#price-hint").hidden = !outside;
  if (outside) $("#price-hint").textContent = `Цена вне диапазона маршрута: ${fmt(destination.price_min)}–${rub(destination.price_max)}`;
  if (destination && valid) {
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
  $("#date-hint").textContent = `${dow(day)}${holiday ? ` · ${holiday}` : ""} · доступно ` +
    `${dayMonth(destination.first_date)}–${shortDate(destination.last_date)}`;
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
  $("#source-hint").textContent = ml && !ml.available ? ml.detail : sourceHint();
}

function sourceHint() {
  const source = S.sources[form.elements.source.value];
  return source ? `${source.file} · ${source.detail}` : "";
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
priceInput.addEventListener("blur", () => setPrice(priceInput.value));
form.elements.destination.addEventListener("change", () => {
  onDestinationChange();
  calculate({ live: true });
});
form.elements.date.addEventListener("change", () => {
  $("#date-note").hidden = true;
  updateDateHint();
  calculate({ live: true });
});
form.elements.source.addEventListener("change", async () => {
  if (await loadRoutes(form.elements.source.value)) calculate({ live: true });
});
const NARROW = window.matchMedia("(max-width: 960px)");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await calculate({ save: true });
  if (NARROW.matches) result.scrollIntoView({ behavior: "smooth", block: "start" }); // на телефоне результат ниже формы
});
$("#retry").addEventListener("click", () => calculate({}));
$("#apply-best").addEventListener("click", () => {
  if (!S.forecast) return;
  S.autoPrice = false;
  setPrice(S.forecast.best.price);
  calculate({ save: true, live: true });
});

// --- расчёт ---

// Номер последнего запроса расчёта: на экран попадает только его ответ.
let lastRequest = 0;

// Расчёт уже на экране — он приглушается до ответа; заготовка со скелетоном только при первой загрузке.
// Запрос с записью в историю не отменяется следующим (ползунком): запись всё равно будет в базе,
// поэтому таблица истории обновляется по его ответу, даже если на экран попадёт более новый расчёт.
async function calculate({ save = false, live = false }) {
  clearErrors();
  const shown = !$('[data-panel="ready"]', result).hidden;
  if (shown) setUpdating(true);
  else setPanel("loading");
  if (shown && !live) setBusy(true);
  const request = ++lastRequest;
  const cancel = signals.forecast(); // отменяет предыдущий запрос без записи
  const response = await post("/api/forecast", { ...readQuery(), save }, save ? undefined : cancel);
  if (save && response.ok) refreshHistory();
  if (response.aborted || request !== lastRequest) return;
  setUpdating(false);
  setBusy(false);
  if (response.status === 401) return location.assign("/login");
  if (response.status === 0 || response.status >= 500) {
    return showError({ code: response.status || 503, title: DOWN[0], text: DOWN[1] });
  }
  if (!response.ok) {
    showFieldError(response.data);
    if (response.data && response.data.field === "date") return showMissingFlight(response.data.detail);
    setPanel(S.forecast ? "ready" : "empty");
    return;
  }
  render(response.data);
}

// Рейса на эту дату нет: старый результат прячем, чтобы его не приняли за ответ на новый запрос.
// Повтор дал бы тот же ответ — вместо кнопки «Повторить расчёт» фокус в поле даты.
function showMissingFlight(detail) {
  const { origin, destination, date } = readQuery();
  const day = /^\d{4}-\d{2}-\d{2}$/.test(date) ? ` на ${shortDate(date)}` : "";
  showError({ title: `Рейса ${origin} → ${destination}${day} нет`, text: detail, retry: false });
  form.elements.date.focus();
}

function render(d) {
  S.forecast = d;
  const want = Math.max(0, d.wanted);
  const out = (key) => $(`[data-out="${key}"]`, result);
  out("seats").textContent = whole(d.seats);
  out("want").textContent = whole(want);
  out("buy").textContent = whole(d.sold);
  out("load").textContent = whole(d.load * 100);
  out("wantRaw").hidden = d.wanted >= 0;
  out("wantRaw").textContent = `по формуле ${whole(d.wanted)}`;
  $("#load-meter").style.setProperty("--p", `${Math.min(100, d.load * 100)}%`);
  renderNote(d, want);
  renderFormula(d);
  renderRoute(d);

  const quantiles = d.scenarios.map((s) => s.wanted);
  const over = quantiles.filter((q) => q > d.seats).length;
  $("#chart-title").textContent = `Спрос при цене ${rub(d.price)} по 9\u00A0сценариям`;
  $("#legend-hatch").hidden = !over;
  $("#chart-how").textContent = d.sold <= 0
    ? "При такой цене формула даёт отрицательный спрос. Отрицательных покупателей не бывает, поэтому столбики " +
      "равны 0; над ними мелко — значение по формуле."
    : over
      ? `Заштрихованная часть — желающие, которым не хватит кресел: так выходит в ${over} ` +
        `${plural(over, ["сценарии", "сценариях", "сценариях"])} из\u00A09. Слева пессимистичный сценарий 0,1, справа оптимистичный 0,9.`
      : "Каждый столбик — сколько человек захотят купить билет в одном из 9\u00A0сценариев: слева пессимистичный (0,1), " +
        "справа оптимистичный (0,9). Выделенный столбик — медиана, её мы показываем как «желают».";
  $("#chart-odds").textContent = oddsText(d.odds);

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
    tag.textContent = "Упор в места";
    $("#note-text").textContent = `Желают ${whole(want)}, а мест ${whole(d.seats)} — купят ${whole(d.sold)}. ` +
      `Не хватит мест для ${whole(d.wanted - d.seats)} желающих.`;
  } else if (none) {
    tag.textContent = "Нет спроса";
    $("#note-text").textContent = `При цене ${rub(d.price)} желающих нет: формула даёт ${whole(d.wanted)}. ` +
      "Попробуйте снизить цену.";
  } else {
    tag.textContent = `Запас ${seatsText(d.seats - want)}`;
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
  let note = "Ожидаемая прибыль — среднее по 9\u00A0сценариям от (цена − расходы на пассажира) × купят. " +
    "Кривую и максимум считает сервер.";
  if (best.file_price !== null) {
    note += ` Цена медианного сценария из файла (0.5_price) — ${rub(best.file_price)}; ` +
      "лучшая цена здесь подобрана под все девять сценариев.";
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
      ? [[s.name, "l"], [whole(Math.max(0, f.wanted))], [whole(f.sold)], [percent(f.load)], [whole(f.best_price)]]
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
    const button = node("button", `scen__btn${i === 4 ? " is-median" : ""}`, `0,${i + 1}`);
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
  $("#queue-title").textContent = `Не хватило мест · ${whole(over)}`;
  $('[data-salon="seats"]').textContent = whole(d.seats);
  $('[data-salon="sold"]').textContent = whole(sold);
  $('[data-salon="over"]').textContent = whole(over);
  const { scale, text } = salonText(cabin, `0,${S.scenario + 1}`, scenario.wanted, sold, over, queue);
  const note = node("span"); // одним блоком: у .how display: flex, и <strong> иначе становился узкой колонкой
  note.append(node("strong", "", scale), text);
  $("#salon-how").replaceChildren(note);
  $("#salon-odds").textContent = oddsText(d.odds);
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
  $("#cal-min").textContent = withPercent(loads.min);
  $("#cal-max").textContent = withPercent(loads.max);
  $("#cal-how").textContent = `Цвет — загрузка при цене ${rub(d.price)}: от самого слабого дня месяца (${withPercent(loads.min)}) ` +
    `до самого сильного (${withPercent(loads.max)}). Нажмите на день — откроется расчёт на эту дату.`;
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
    node("span", "history__src", entry.source === "ml" ? "ML" : "орг."));
  const flag = node("td");
  if (want > entry.seats) flag.append(node("span", "tag", "Упор в места"));
  else if (entry.sold <= 0) flag.append(node("span", "tag tag--err", "Нет спроса"));
  const again = node("button", "link-btn", "Повторить →");
  again.type = "button";
  again.addEventListener("click", () => repeat(entry));
  flag.append(again);
  row.append(node("td", "l time", timeOf(entry.created_at)), route, node("td", "l", shortDate(entry.date)),
    node("td", "", fmt(entry.price, 2)), node("td", "", whole(entry.seats)), node("td", "", whole(want)),
    node("td", "buy", whole(entry.sold)), node("td", "", percent(entry.load)), flag);
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

// «Зарегистрироваться» гостя — обычная ссылка на /login#register: из гостя не выходим,
// его история переходит в новый аккаунт на сервере.

window.addEventListener("resize", () => {
  if (!S.forecast) return;
  if (S.tab === "calc") drawDemand(S.forecast);
  drawCurve();
});

// Дата из адреса, которой нет в прогнозе маршрута (или в календаре вовсе): поле встаёт на первый день,
// и под полем сказано почему, а не молча.
function useDateFromAddress(wanted) {
  form.elements.date.value = wanted || STORY.date;
  onDestinationChange();
  const shown = form.elements.date.value;
  const note = $("#date-note");
  note.hidden = !wanted || shown === wanted;
  if (!note.hidden) note.textContent = `Даты ${wanted} из адреса страницы нет в прогнозе. Показано ${shortDate(shown)}.`;
}

// /api/session без входа отвечает 200 и user: null, а не 401: после «Выйти» и «Назад» страница
// из кэша уходит на /login без ошибки в консоли.
async function start() {
  const session = await get("/api/session");
  const user = session.ok ? session.data.user : null;
  if (!user) return location.assign("/login");
  $("#user-login").textContent = user.login;
  $("#register-link").hidden = !user.guest;
  buildScenarioButtons();
  await loadSources();
  const params = new URLSearchParams(location.search);
  const routed = await loadRoutes(params.get("source"), params.get("destination")) ||
    (params.get("source") !== null && await loadRoutes(null, params.get("destination"))); // неизвестный источник — по умолчанию
  if (!routed) return setPanel("empty");
  if (params.get("price")) {
    S.autoPrice = false;
    setPrice(params.get("price"));
  }
  useDateFromAddress(params.get("date"));
  const tab = params.get("tab");
  setTab(TABS.includes(tab) ? tab : "calc");
  refreshHistory();
  calculate({}); // при открытии страницы расчёт не пишется в историю: её пополняют «Рассчитать» и действия человека
}

start();
