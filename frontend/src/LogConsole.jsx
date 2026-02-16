import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_KEY = import.meta.env.VITE_PIPELINE_API_KEY || '';

async function apiFetch(path, options = {}) {
  if (API_KEY) {
    options.headers = { ...options.headers, "X-API-Key": API_KEY };
  }
  options.credentials = 'include';
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

const LEVEL_COLORS = {
  DEBUG: { color: "#6b7280", bg: "rgba(107,114,128,0.1)" },
  INFO: { color: "#60a5fa", bg: "rgba(96,165,250,0.1)" },
  WARNING: { color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
  ERROR: { color: "#f87171", bg: "rgba(248,113,113,0.1)" },
  CRITICAL: { color: "#ef4444", bg: "rgba(239,68,68,0.15)" },
};

function LogEntry({ entry }) {
  const levelCfg = LEVEL_COLORS[entry.level] || LEVEL_COLORS.INFO;
  const time = new Date(entry.timestamp).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "68px 58px 1fr",
      gap: 8,
      padding: "3px 12px",
      fontSize: 12,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', monospace",
      lineHeight: 1.6,
      borderBottom: "1px solid rgba(255,255,255,0.02)",
      background: entry.level === "ERROR" || entry.level === "CRITICAL"
        ? "rgba(248,113,113,0.03)" : "transparent",
    }}>
      <span style={{ color: "rgba(255,255,255,0.25)" }}>{time}</span>
      <span style={{
        color: levelCfg.color,
        background: levelCfg.bg,
        padding: "0 6px",
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 600,
        textAlign: "center",
        letterSpacing: 0.3,
        alignSelf: "start",
        marginTop: 2,
      }}>
        {entry.level}
      </span>
      <span style={{
        color: entry.level === "ERROR" ? "#fca5a5" :
               entry.level === "WARNING" ? "#fde68a" :
               "rgba(255,255,255,0.65)",
        wordBreak: "break-word",
      }}>
        {entry.logger !== "root" && (
          <span style={{ color: "rgba(255,255,255,0.2)", marginRight: 6 }}>
            [{entry.logger}]
          </span>
        )}
        {entry.message}
      </span>
    </div>
  );
}

export default function LogConsole() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [logs, setLogs] = useState([]);
  const [streaming, setStreaming] = useState(true);
  const [levelFilter, setLevelFilter] = useState("INFO");
  const [searchFilter, setSearchFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const [errorCount, setErrorCount] = useState(0);

  const logEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setAutoScroll(atBottom);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    apiFetch(`/api/logs/recent?limit=200&level=${levelFilter}`)
      .then(data => {
        if (data?.entries) {
          setLogs(data.entries);
          setErrorCount(data.entries.filter(e => e.level === "ERROR" || e.level === "CRITICAL").length);
        }
      })
      .catch(err => console.warn("Failed to load logs:", err));
  }, [isOpen, levelFilter]);

  useEffect(() => {
    if (!isOpen || !streaming) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        setConnected(false);
      }
      return;
    }

    const url = `${API_BASE}/api/logs/stream?level=${levelFilter}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);
    
    es.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data);
        if (entry.type === "connected") return;
        
        setLogs(prev => {
          const updated = [...prev, entry];
          return updated.length > 1000 ? updated.slice(-800) : updated;
        });

        if (entry.level === "ERROR" || entry.level === "CRITICAL") {
          setErrorCount(prev => prev + 1);
        }
      } catch (e) {}
    };

    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      eventSourceRef.current = null;
      setConnected(false);
    };
  }, [isOpen, streaming, levelFilter]);

  const filteredLogs = searchFilter
    ? logs.filter(l => l.message.toLowerCase().includes(searchFilter.toLowerCase()) ||
                       l.logger.toLowerCase().includes(searchFilter.toLowerCase()))
    : logs;

  const clearLogs = () => { setLogs([]); setErrorCount(0); };

  const panelHeight = isExpanded ? "65vh" : 320;

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{
          position: "fixed", bottom: 16, right: 16, zIndex: 999,
          display: "flex", alignItems: "center", gap: 6,
          padding: "8px 14px",
          background: "rgba(15,15,25,0.9)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 10,
          color: "rgba(255,255,255,0.5)",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
          backdropFilter: "blur(12px)",
          fontFamily: "'DM Sans', sans-serif",
          transition: "all 0.2s",
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(96,165,250,0.3)"; e.currentTarget.style.color = "#60a5fa"; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "rgba(255,255,255,0.5)"; }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" />
        </svg>
        Logs
        {errorCount > 0 && (
          <span style={{
            background: "rgba(248,113,113,0.2)", color: "#f87171",
            fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 8,
          }}>
            {errorCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 1000,
      height: panelHeight, display: "flex", flexDirection: "column",
      background: "rgba(8,8,16,0.97)",
      borderTop: "1px solid rgba(255,255,255,0.08)",
      backdropFilter: "blur(20px)",
      transition: "height 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "6px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              background: connected ? "#34d399" : "#f87171",
              boxShadow: connected ? "0 0 6px rgba(52,211,153,0.5)" : "0 0 6px rgba(248,113,113,0.5)",
            }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)", fontFamily: "'DM Sans', sans-serif" }}>
              Log Console
            </span>
          </div>

          <select
            value={levelFilter}
            onChange={e => setLevelFilter(e.target.value)}
            style={{
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 6, color: "rgba(255,255,255,0.6)", fontSize: 11,
              padding: "3px 8px", outline: "none", cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
            }}
          >
            <option value="DEBUG" style={{ background: "#0e0e1a" }}>DEBUG</option>
            <option value="INFO" style={{ background: "#0e0e1a" }}>INFO</option>
            <option value="WARNING" style={{ background: "#0e0e1a" }}>WARNING</option>
            <option value="ERROR" style={{ background: "#0e0e1a" }}>ERROR</option>
          </select>

          <input
            type="text" value={searchFilter}
            onChange={e => setSearchFilter(e.target.value)}
            placeholder="Filter..."
            style={{
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 6, color: "rgba(255,255,255,0.6)", fontSize: 11,
              padding: "3px 10px", outline: "none", width: 150,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          />

          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }}>
            {filteredLogs.length} entries
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            onClick={() => setStreaming(!streaming)}
            style={{
              background: streaming ? "rgba(52,211,153,0.1)" : "rgba(251,191,36,0.1)",
              border: `1px solid ${streaming ? "rgba(52,211,153,0.2)" : "rgba(251,191,36,0.2)"}`,
              borderRadius: 6, padding: "4px 8px",
              color: streaming ? "#34d399" : "#fbbf24",
              cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
              fontSize: 10, fontWeight: 600,
            }}
          >
            {streaming ? "⏸ Live" : "▶ Paused"}
          </button>

          <button onClick={clearLogs} title="Clear logs" style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 8px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 11,
          }}>🗑</button>

          <button onClick={() => setIsExpanded(!isExpanded)} style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 8px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 11,
          }}>{isExpanded ? "▼" : "▲"}</button>

          <button onClick={() => setIsOpen(false)} style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 10px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 12, fontWeight: 600,
          }}>✕</button>
        </div>
      </div>

      {/* Log entries */}
      <div ref={scrollContainerRef} onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
        {filteredLogs.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "rgba(255,255,255,0.15)", fontSize: 12, fontFamily: "'DM Sans', sans-serif" }}>
            {connected ? "Waiting for log entries..." : "Connecting to log stream..."}
          </div>
        ) : (
          filteredLogs.map((entry, i) => (
            <LogEntry key={`${entry.timestamp}-${i}`} entry={entry} />
          ))
        )}
        <div ref={logEndRef} />
      </div>

      {!autoScroll && (
        <button
          onClick={() => { setAutoScroll(true); logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }}
          style={{
            position: "absolute", bottom: 8, right: 16,
            background: "rgba(96,165,250,0.15)", border: "1px solid rgba(96,165,250,0.3)",
            borderRadius: 8, padding: "4px 12px", color: "#60a5fa",
            fontSize: 11, fontWeight: 500, cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
          }}
        >
          ↓ Jump to latest
        </button>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
      `}</style>
    </div>
  );
}
