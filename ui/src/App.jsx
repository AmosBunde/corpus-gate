import React, { useEffect, useState } from "react";

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
    justifyContent: "center",
    gap: "12px",
  },
  sub: { color: "#8b949e", fontSize: "14px" },
  status: { color: "#3fb950", fontSize: "13px" },
};

export default function App() {
  const [apiStatus, setApiStatus] = useState("checking the API");

  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then((r) => r.json())
      .then((b) => setApiStatus(`API ${b.status}, backend ${b.model_backend}`))
      .catch(() => setApiStatus("API unreachable"));
  }, []);

  return (
    <div style={styles.page}>
      <h1>CorpusGate</h1>
      <p style={styles.sub}>
        Private corpus agent with an eval gate. The query box, streamed
        answers, and inline cited passages land in milestone M5.
      </p>
      <p style={styles.status}>{apiStatus}</p>
    </div>
  );
}
