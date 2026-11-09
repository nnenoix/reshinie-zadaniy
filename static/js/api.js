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
  if (response.status === 403 && !csrfToken()) {
    await get("/api/csrf"); // cookie потерялась — получаем новую и пробуем ещё раз
    response = await send();
  }
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
