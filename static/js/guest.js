// Гостевой вход: временный аккаунт со своей историей, без пароля.
import { get, post } from "./api.js";

const FAILED = { detail: "Не удалось войти как гость. Попробуйте ещё раз." };

export async function enterAsGuest() {
  const response = await post("/api/guest");
  return response.ok ? response : { ...response, data: response.data || FAILED };
}

// Для «Открыть расчёт 12 июня» и «Войти как гость» на витрине: если вход уже есть, остаёмся собой
// (не выходим из аккаунта в нового гостя), иначе входим гостем.
// /api/session без входа отвечает 200 и user: null — в консоли нет ошибки 401, как было с /api/me.
export async function ensureSession() {
  const session = await get("/api/session");
  return session.ok && session.data.user ? { ...session, data: session.data.user } : enterAsGuest();
}
