// Гостевой вход: временный аккаунт со своей историей, без пароля.
import { get, post } from "./api.js";

const FAILED = { detail: "Не удалось войти как гость. Попробуйте ещё раз." };

export async function enterAsGuest() {
  const response = await post("/api/guest");
  return response.ok ? response : { ...response, data: response.data || FAILED };
}

// Для «Открыть расчёт 12 июня»: если вход уже есть, остаёмся собой, иначе входим гостем.
export async function ensureSession() {
  const me = await get("/api/me");
  return me.ok ? me : enterAsGuest();
}
