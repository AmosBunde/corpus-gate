import React, { useState } from "react";

// Rule three in the browser: every citation renders its actual passage,
// not a bare identifier. The quote is the model's claimed support; the
// passage is the indexed chunk text it must live inside.

const styles = {
  list: { display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" },
  card: {
    background: "#0d1117",
    border: "1px solid #30363d",
    borderRadius: "6px",
    padding: "12px",
    fontSize: "13px",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: "8px",
    flexWrap: "wrap",
    alignItems: "baseline",
  },
  chunkId: { color: "#79c0ff", fontSize: "12px", wordBreak: "break-all" },
  doc: { color: "#8b949e", fontSize: "12px" },
  quote: {
    borderLeft: "3px solid #238636",
    margin: "10px 0 0",
    padding: "2px 0 2px 10px",
    color: "#e6edf3",
    fontStyle: "italic",
  },
  toggle: {
    background: "none",
    border: "none",
    color: "#8b949e",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: "12px",
    padding: "8px 0 0",
    textAlign: "left",
  },
  passage: {
    marginTop: "8px",
    padding: "10px",
    background: "#161b22",
    borderRadius: "6px",
    color: "#c9d1d9",
    whiteSpace: "pre-wrap",
    lineHeight: 1.6,
  },
  refusal: {
    background: "#1c1710",
    border: "1px solid #d2992266",
    borderRadius: "6px",
    padding: "16px",
    color: "#d29922",
    fontSize: "14px",
    lineHeight: 1.6,
  },
};

function CitationCard({ citation, ordinal }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.chunkId}>
          [{ordinal}] {citation.chunk_id}
        </span>
        <span style={styles.doc}>
          {citation.doc_id} · {citation.section}
        </span>
      </div>
      {citation.quote && <blockquote style={styles.quote}>{citation.quote}</blockquote>}
      {citation.passage && (
        <>
          <button style={styles.toggle} onClick={() => setOpen(!open)}>
            {open ? "hide the full passage" : "show the full passage"}
          </button>
          {open && <div style={styles.passage}>{citation.passage}</div>}
        </>
      )}
    </div>
  );
}

export function Refusal({ answer }) {
  return (
    <div style={styles.refusal}>
      <strong>Declined.</strong> {answer}
      <div style={{ fontSize: "12px", color: "#8b949e", marginTop: "8px" }}>
        The corpus does not support an answer, so none is given. No citations
        accompany a refusal.
      </div>
    </div>
  );
}

export function CitationList({ citations }) {
  if (!citations.length) return null;
  return (
    <div style={styles.list}>
      {citations.map((c, i) => (
        <CitationCard key={`${c.chunk_id}-${i}`} citation={c} ordinal={i + 1} />
      ))}
    </div>
  );
}
