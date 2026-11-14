// Запросы к серверу. POST получает заголовок X-CSRF-Token из cookie csrf_token.

const OFFLINE = { detail: "Сервер не отвечает. Проверьте подключение и попробуйте ещё раз.", field: null };

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request(path, options) {
  try {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    if (error.name === "AbortError") return { ok: false, status: -1, data: null, aborted: true };
    return { ok: false, status: 0, data: OFFLINE };
  }
}

export function get(path, params = {}, signal) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  const url = query.toString() ? `${path}?${query}` : path;
  return request(url, { method: "GET", signal });
}

export async function post(path, body, signal) {
  const send = () => request(path, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let response = await send();
  if (response.status === 403 && response.data && response.data.code === "NO_TOKEN") {
    await get("/api/csrf"); // cookie потерялась или устарела — берём действующую и повторяем один раз
    response = await send();
  }
  return response;
}

// Кнопка на время запроса: недоступна, aria-busy и текст вроде «Входим…» — при холодном старте
// сервера ответ идёт долго, и второй клик не должен слать второй запрос. После ошибки кнопка
// возвращается сразу, после успеха — когда страницу вернут кнопкой «Назад» (pageshow).
export async function whileBusy(button, label, task) {
  const before = [...button.childNodes];
  const restore = () => {
    button.replaceChildren(...before);
    button.disabled = false;
    button.removeAttribute("aria-busy");
  };
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = label;
  const response = await task();
  if (response.ok) window.addEventListener("pageshow", restore, { once: true });
  else restore();
  return response;
}

// Отменяет предыдущий запрос того же вида, когда начинается новый (ползунок, календарь).
export function latestOnly() {
  let controller = null;
  return () => {
    if (controller) controller.abort();
    controller = new AbortController();
    return controller.signal;
  };
}
