// Страница /login: вход, регистрация, гостевой вход. После входа — инструмент /app.
import { post } from "./api.js";
import { enterAsGuest } from "./guest.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function clearErrors(form) {
  $$("[data-error-for]", form).forEach((slot) => { slot.hidden = true; slot.textContent = ""; });
  $$(".field.is-invalid", form).forEach((field) => field.classList.remove("is-invalid"));
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

function switchTo(tab) {
  $$(".tabs__btn").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $$("[data-form]").forEach((form) => {
    form.hidden = form.dataset.form !== tab;
    clearErrors(form);
  });
  $(`[data-form="${tab}"] input`).focus();
}

$$("[data-tab]").forEach((b) => b.addEventListener("click", () => switchTo(b.dataset.tab)));

$$("[data-toggle-password]").forEach((toggle) => toggle.addEventListener("click", () => {
  const input = $("input", toggle.parentNode);
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  toggle.textContent = show ? "СКРЫТЬ" : "ПОКАЗАТЬ";
}));

$$("[data-form]").forEach((form) => form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors(form);
  const body = Object.fromEntries(new FormData(form).entries());
  const response = await post(`/api/${form.dataset.form}`, body);
  if (response.ok) return location.assign("/app");
  showError(form, response.data);
}));

$("[data-guest]").addEventListener("click", async () => {
  const error = $("[data-guest-error]");
  error.hidden = true;
  const response = await enterAsGuest();
  if (response.ok) return location.assign("/app");
  error.textContent = response.data.detail;
  error.hidden = false;
});

if (location.hash === "#register") switchTo("register");
