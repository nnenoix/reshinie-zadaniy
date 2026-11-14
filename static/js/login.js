// Страница /login: «Вход для жюри» (логин и пароль демо-аккаунта уже введены сервером), обычный вход
// и регистрация серой строкой внизу. После входа — инструмент /app.
// Гость тоже попадает сюда (ссылка «Зарегистрироваться» в /app): при регистрации его история переходит в аккаунт.
import { get, post, whileBusy } from "./api.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const EMPTY = { login: "Введите логин или email.", password: "Введите пароль.", password2: "Повторите пароль." };
const BUSY = { jury: "Входим…", login: "Входим…", register: "Создаём…" };
const GUEST_TRANSFER = "История расчётов гостя перейдёт в новый аккаунт";

function clearField(form, name) {
  const slot = $(`[data-error-for="${name}"]`, form);
  if (!slot) return;
  slot.hidden = true;
  slot.textContent = "";
  slot.closest(".field").classList.remove("is-invalid");
}

function clearErrors(form) {
  $$("[data-error-for]", form).forEach((slot) => clearField(form, slot.dataset.errorFor));
  $('[data-error="general"]', form).hidden = true;
}

function showError(form, data) {
  const detail = (data && data.detail) || "Не удалось выполнить запрос. Попробуйте ещё раз.";
  const slot = data && data.field && $(`[data-error-for="${data.field}"]`, form);
  if (slot) {
    slot.textContent = detail;
    slot.hidden = false;
    slot.closest(".field").classList.add("is-invalid");
    return;
  }
  const general = $('[data-error="general"]', form);
  $("[data-error-text]", general).textContent = detail;
  general.hidden = false;
}

// Пустые поля видны сразу, без запроса: иначе сервер ответил бы «Неверный логин или пароль».
function emptyFields(form) {
  return $$("input[name]", form).filter((input) => {
    const value = input.name === "login" ? input.value.trim() : input.value;
    return EMPTY[input.name] && value === "";
  });
}

function switchTo(tab) {
  $$(".tabs__btn").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $$("[data-form]").forEach((form) => {
    form.hidden = form.dataset.form !== tab;
    clearErrors(form);
  });
  $("[data-register-line]").hidden = tab === "register"; // в регистрации своя строка «Уже есть аккаунт?»
  $(`[data-form="${tab}"] input`).focus();
}

$$("[data-tab]").forEach((b) => b.addEventListener("click", () => switchTo(b.dataset.tab)));

// «Показать» раскрывает все поля пароля своей формы: в регистрации — и пароль, и повтор.
$$("[data-toggle-password]").forEach((toggle) => toggle.addEventListener("click", () => {
  const inputs = $$('input[name^="password"]', toggle.closest("form"));
  const show = inputs[0].type === "password";
  inputs.forEach((input) => { input.type = show ? "text" : "password"; });
  toggle.textContent = show ? "Скрыть" : "Показать";
}));

$$("[data-form]").forEach((form) => {
  form.addEventListener("input", (event) => clearField(form, event.target.name));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(form);
    const empty = emptyFields(form);
    if (empty.length) {
      empty.forEach((input) => showError(form, { field: input.name, detail: EMPTY[input.name] }));
      empty[0].focus();
      return;
    }
    const body = Object.fromEntries(new FormData(form).entries());
    const submit = $('button[type="submit"]', form);
    const response = await whileBusy(submit, BUSY[form.dataset.form], () => post(form.getAttribute("action"), body));
    if (response.ok) return location.assign("/app");
    showError(form, response.data);
  });
});

async function noteGuestTransfer() {
  const session = await get("/api/session");
  if (!session.ok || !session.data.user || !session.data.user.guest) return;
  const form = $('[data-form="register"]');
  const note = document.createElement("p");
  note.className = "field__hint";
  note.dataset.guestTransfer = "";
  note.textContent = GUEST_TRANSFER;
  $('button[type="submit"]', form).after(note);
}

if (location.hash === "#register") switchTo("register");
noteGuestTransfer();
