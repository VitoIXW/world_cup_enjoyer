import fs from "node:fs/promises";

const TARGET_URL =
  "https://www.fifa.com/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures?country=ES&wtw-filter=ALL";
const DEBUG_LIST_URL = "http://127.0.0.1:9222/json/list";
const OUTPUT_PATH = "/tmp/fifa_cdp_capture.json";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getTargetWebSocketUrl() {
  const response = await fetch(DEBUG_LIST_URL);
  const pages = await response.json();
  const target = pages.find(
    (page) =>
      page.type === "page" &&
      page.url.includes(
        "/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures",
      ),
  );

  if (!target) {
    throw new Error("No he encontrado la pestaña de scores-fixtures en Chrome.");
  }

  return target.webSocketDebuggerUrl;
}

async function main() {
  const wsUrl = await getTargetWebSocketUrl();
  const ws = new WebSocket(wsUrl);

  let nextId = 1;
  const pending = new Map();
  const interesting = new Map();
  const events = [];

  const send = (method, params = {}) => {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject, method });
    });
  };

  ws.addEventListener("message", async (event) => {
    const message = JSON.parse(event.data);

    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) {
        reject(new Error(JSON.stringify(message.error)));
      } else {
        resolve(message.result);
      }
      return;
    }

    if (message.method === "Network.requestWillBeSent") {
      const { requestId, request } = message.params;
      const url = request.url;
      if (
        url.includes("fifa.com") &&
        /match|fixture|broadcaster|wtw|score|calendar|tournament/i.test(url)
      ) {
        interesting.set(requestId, {
          url,
          method: request.method,
          requestHeaders: request.headers,
        });
        events.push({ type: "request", requestId, url, method: request.method });
      }
    }

    if (message.method === "Network.responseReceived") {
      const { requestId, response } = message.params;
      if (interesting.has(requestId)) {
        const item = interesting.get(requestId);
        item.status = response.status;
        item.mimeType = response.mimeType;
        item.responseHeaders = response.headers;
        events.push({
          type: "response",
          requestId,
          url: item.url,
          status: response.status,
          mimeType: response.mimeType,
        });
      }
    }

    if (message.method === "Network.loadingFinished") {
      const { requestId } = message.params;
      if (!interesting.has(requestId)) {
        return;
      }

      const item = interesting.get(requestId);
      try {
        const result = await send("Network.getResponseBody", { requestId });
        item.body = result.base64Encoded
          ? Buffer.from(result.body, "base64").toString("utf8")
          : result.body;
        item.bodyPreview = item.body.slice(0, 3000);
      } catch (error) {
        item.bodyError = String(error);
      }
    }
  });

  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  await send("Page.enable");
  await send("Network.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: TARGET_URL });

  await sleep(12000);

  const payload = {
    capturedAt: new Date().toISOString(),
    targetUrl: TARGET_URL,
    events,
    requests: [...interesting.values()],
  };

  await fs.writeFile(OUTPUT_PATH, JSON.stringify(payload, null, 2));
  console.log(OUTPUT_PATH);
  console.log(`captured_requests=${payload.requests.length}`);

  for (const request of payload.requests) {
    console.log(
      [
        request.status ?? "NA",
        request.mimeType ?? "unknown",
        request.url,
      ].join(" | "),
    );
  }

  ws.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
