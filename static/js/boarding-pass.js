// Посадочный талон: поля [data-t] и выгрузка в PNG и PDF.
// Картинку делает html2canvas по готовой вёрстке талона, PDF собирает pdf.js без библиотек.
import { airportCodes, dow, fmt, rub, seatsText, shortDate, whole } from "./format.js";
import { pdfFromJpeg } from "./pdf.js";

const NO_LIBRARY = "Не загрузилась библиотека для картинок (html2canvas с cdnjs). " +
  "Проверьте интернет. PDF можно сохранить через печать: Ctrl+P → «Сохранить как PDF».";

export function ticketData(d) {
  const codes = airportCodes(d.route.code);
  const want = Math.max(0, d.wanted);
  const capped = d.wanted > d.seats, none = d.sold <= 0;
  const compact = d.date.slice(8, 10) + d.date.slice(5, 7) + d.date.slice(2, 4);
  return {
    fromCode: codes.from, fromCity: d.route.origin, code: codes.to, city: d.route.destination,
    date: shortDate(d.date), day: dow(d.date) + (d.holiday ? " · ПРАЗДНИК" : ""),
    price: rub(d.price), seats: whole(d.seats), want: fmt(want), buy: fmt(d.sold),
    load: `${whole(d.load * 100)} %`, best: rub(d.best.price),
    tag: capped ? "УПОР В МЕСТА" : none ? "НЕТ СПРОСА" : `ЗАПАС ${seatsText(d.seats - want).toUpperCase()}`,
    status: capped ? `Не хватит мест для ${fmt(d.wanted - d.seats)} желающих`
      : none ? `Формула даёт ${fmt(d.wanted)}` : "Мест хватает всем желающим",
    stubRoute: `${codes.from} → ${codes.to}`, buySeats: `${fmt(d.sold)} / ${whole(d.seats)}`,
    id: `RA-${codes.to}-${compact}-${Math.round(d.price)}`,
    none,
  };
}

export function fillTicket(ticket, data) {
  ticket.querySelectorAll("[data-t]").forEach((field) => {
    field.textContent = data[field.dataset.t];
  });
  ticket.querySelector('[data-t="tag"]').className = `tag${data.none ? " tag--err" : ""}`;
}

async function snapshot(ticket, background) {
  if (typeof window.html2canvas !== "function") throw new Error(NO_LIBRARY);
  await document.fonts.ready;
  return window.html2canvas(ticket, { scale: 2, backgroundColor: background, logging: false });
}

function toBlob(canvas, type, quality) {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Не удалось сохранить картинку."))), type, quality));
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadPng(ticket, filename) {
  const canvas = await snapshot(ticket, null);
  download(await toBlob(canvas, "image/png"), filename);
}

export async function downloadPdf(ticket, filename) {
  const canvas = await snapshot(ticket, "#ffffff"); // у JPEG нет прозрачности
  const jpeg = new Uint8Array(await (await toBlob(canvas, "image/jpeg", 0.92)).arrayBuffer());
  download(pdfFromJpeg(jpeg, canvas.width, canvas.height), filename);
}
