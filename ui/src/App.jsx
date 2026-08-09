import React, { useEffect, useState } from "react";
import { getToken, setToken, streamQuery } from "./api.js";
import { CitationList, Refusal } from "./Citations.jsx";

const styles = {
  page: {
    minHeight: "100vh",
    margin: 0,
    background: "#0d1117",
    color: "#e6edf3",
    fontFamily: "'JetBrains Mono', monospace",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "48px 16px",
    gap: "16px",
  },
  sub: { color: "#8b949e", fontSize: "14px", margin: 0 },
  status: { color: "#3fb950", fontSize: "13px", margin: 0 },
  column: {
    width: "100%",
    maxWidth: "760px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  row: { display: "flex", gap: "8px" },
  input: {
    flex: 1,
    background: "#161b22",
    color: "#e6edf3",
    border: "1px solid #30363d",
    borderRadius: "6px",
    padding: "10px 12px",
    fontFamily: "inherit",
    fontSize: "14px",
  },
  button: {
    background: "#238636",
    color: "#ffffff",
    border: "none",
    borderRadius: "6px",
    padding: "10px 18px",
    fontFamily: "inherit",
    fontSize: "14px",
    cursor: "pointer",
  },
  buttonDisabled: { background: "#21262d", color: "#8b949e", cursor: "wait" },
  working: { color: "#d29922", fontSize: "13px" },
  error: {
    color: "#f85149",
    background: "#161b22",
    border: "1px solid #f8514966",
    borderRadius: "6px",
    padding: "10px 12px",
    fontSize: "13px",
  },
  answer: {
    background: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "6px",
    padding: "16px",
    fontSize: "14px",
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
  },
  meta: { color: "#8b949e", fontSize: "12px" },
};

export default function App() {
  const [apiStatus, setApiStatus] = useState("checking the API");
  const [token, setTokenState] = useState(getToken());
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((b) => setApiStatus(`API ${b.status}, backend ${b.model_backend}`))
      .catch(() => setApiStatus("API unreachable"));
  }, []);

  function updateToken(value) {
    setTokenState(value);
    setToken(value);
  }

  async function ask() {
    if (!question.trim() || phase !== "idle") return;
    setPhase("starting");
    setError("");
    setResult(null);
    try {
      await streamQuery(question, ({ event, data }) => {
        if (event === "status") setPhase(data);
        if (event === "answer") setResult(JSON.parse(data));
      });
    } catch (err) {
      setError(err.message);
    }
    setPhase("idle");
  }

  const working = phase !== "idle";

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>CorpusGate</h1>
      <p style={styles.sub}>Ask the contract corpus; every claim cites its passage.</p>
      <p style={styles.status}>{apiStatus}</p>
      <div style={styles.column}>
        <input
          style={styles.input}
          type="password"
          placeholder="API token"
          value={token}
          onChange={(e) => updateToken(e.target.value)}
        />
        <div style={styles.row}>
          <input
            style={styles.input}
            placeholder="Which law governs the distributor agreement?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
          />
          <button
            style={{ ...styles.button, ...(working ? styles.buttonDisabled : {}) }}
            onClick={ask}
            disabled={working}
          >
            {working ? "working" : "ask"}
          </button>
        </div>
        {working && <p style={styles.working}>{phase}…</p>}
        {error && <div style={styles.error}>{error}</div>}
        {result && result.refused && <Refusal answer={result.answer} />}
        {result && !result.refused && (
          <div style={styles.answer}>
            {result.answer}
            <CitationList citations={result.citations} />
            <div style={{ marginTop: "12px" }}>
              <span style={styles.meta}>
                {`${result.citations.length} cited passage${
                  result.citations.length === 1 ? "" : "s"
                }`}
                {" · "}
                {(result.latency_ms / 1000).toFixed(1)}s
                {" · "}
                {result.prompt_tokens + result.completion_tokens} tokens
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
