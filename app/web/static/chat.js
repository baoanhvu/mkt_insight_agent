// SSE (Server-Sent Events) qua POST /api/chat. Dung fetch() + ReadableStream
// thay vi EventSource nguyen sinh vi EventSource khong ho tro POST/body JSON.
// Xem docs/15-streaming.md muc 15.3 (bang su kien) va 15.7 (phia client).

async function* parseSSE(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // sse-starlette/uvicorn phat dong bang CRLF ("\r\n"), khong phai LF
    // thuan ("\n") - chuan hoa VE LF truoc khi tach, dung theo spec SSE
    // (CR, LF, CRLF deu la dau xuong dong hop le). Thieu buoc nay thi
    // indexOf("\n\n") KHONG BAO GIO khop duoc voi "\r\n\r\n", du lieu van
    // ve du nhung khong bao gio duoc tach thanh su kien - UI ket "..." mai
    // du server da tra loi xong tu lau (hoi quy da gap thuc te). Chuan hoa
    // TREN CA BUFFER (khong phai tung chunk rieng) de khong bo sot truong
    // hop mot cap "\r\n" bi cat lam doi giua hai lan doc socket.
    buf = buf.replace(/\r\n/g, "\n");
    let sep;
    // Mot su kien SSE ket thuc bang dong trong (\n\n) - co the co nhieu su
    // kien don don don gom trong mot lan doc socket.
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      if (!raw.trim() || raw.startsWith(":")) continue; // comment/keep-alive
      let eventName = "message";
      const dataLines = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      let data = {};
      try {
        data = JSON.parse(dataLines.join("\n"));
      } catch (e) {
        continue;
      }
      yield { event: eventName, data };
    }
  }
}

/**
 * Goi POST /api/chat va phat su kien qua `handlers`. Khong throw ra ngoai -
 * loi mang duoc bao qua `handlers.onError`, giong nhu mot su kien "error"
 * cua server, de UI khong can phan biet hai nguon loi.
 */
async function streamChat(message, history, handlers, signal) {
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message, history: history || [] }),
      signal,
    });
    if (!res.ok || !res.body) {
      handlers.onError && handlers.onError({ code: "HTTP_ERROR", message: `HTTP ${res.status}` });
      return;
    }
    for await (const ev of parseSSE(res.body)) {
      switch (ev.event) {
        case "stage":
          handlers.onStage && handlers.onStage(ev.data);
          break;
        case "evidence":
          handlers.onEvidence && handlers.onEvidence(ev.data);
          break;
        case "table":
          handlers.onTable && handlers.onTable(ev.data);
          break;
        case "block":
          handlers.onBlock && handlers.onBlock(ev.data);
          break;
        case "warning":
          handlers.onWarning && handlers.onWarning(ev.data);
          break;
        case "verified":
          handlers.onVerified && handlers.onVerified(ev.data);
          break;
        case "done":
          handlers.onDone && handlers.onDone(ev.data);
          break;
        case "error":
          handlers.onError && handlers.onError(ev.data);
          break;
      }
    }
  } catch (e) {
    if (e && e.name === "AbortError") return; // nguoi dung bam Dung - khong phai loi
    handlers.onError && handlers.onError({ code: "NETWORK_ERROR", message: String(e) });
  }
}
