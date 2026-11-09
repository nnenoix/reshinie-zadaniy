// Минимальный PDF из одной JPEG-картинки: одна страница шириной A4 (842 pt), высота — по пропорциям.
// Без библиотек: каталог, страница, картинка (DCTDecode), поток с командой рисования, таблица xref.

const PAGE_WIDTH = 842;

export function pdfFromJpeg(jpeg, widthPx, heightPx) {
  const encoder = new TextEncoder();
  const parts = [];
  const offsets = [];
  let length = 0;
  const push = (chunk) => {
    const bytes = typeof chunk === "string" ? encoder.encode(chunk) : chunk;
    parts.push(bytes);
    length += bytes.length;
  };
  const object = (number, body) => {
    offsets[number] = length;
    push(`${number} 0 obj\n${body}\nendobj\n`);
  };

  const pageW = PAGE_WIDTH;
  const pageH = Math.round((PAGE_WIDTH * heightPx) / widthPx);
  const draw = `q ${pageW} 0 0 ${pageH} 0 0 cm /Im0 Do Q`;

  push("%PDF-1.4\n");
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  object(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] ` +
            "/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>");
  offsets[4] = length;
  push(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${widthPx} /Height ${heightPx} ` +
       `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);
  push(jpeg);
  push("\nendstream\nendobj\n");
  object(5, `<< /Length ${draw.length} >>\nstream\n${draw}\nendstream`);

  const xref = length;
  push("xref\n0 6\n0000000000 65535 f \n");
  for (let n = 1; n <= 5; n++) push(`${String(offsets[n]).padStart(10, "0")} 00000 n \n`);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts, { type: "application/pdf" });
}
