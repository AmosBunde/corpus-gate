// Streaming client for the query endpoint. EventSource cannot POST, so the
// stream is consumed from a fetch body and parsed as server-sent events:
// blocks separated by a blank line, each with event and data lines.

export function getToken() {
  return sessionStorage.getItem("corpusgate_token") || "";
}

export function setToken(token) {
  sessionStorage.setItem("corpusgate_token", token);
}

function parseEventBlock(block) {
  let event = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  return { event, data: data.join("\n") };
}

// Calls onEvent({event, data}) for each server-sent event. Throws on a
// non-2xx response with a message the UI can show as-is.
export async function streamQuery(question, onEvent) {
  const response = await fetch("/api/query/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ question }),
  });
  if (response.status === 401) {
    throw new Error("unauthorized: check the API token");
  }
  if (response.status === 503) {
    throw new Error("the server has no API token configured");
  }
  if (!response.ok) {
    throw new Error(`the API returned ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      if (block.trim()) onEvent(parseEventBlock(block));
    }
  }
}
