import { useState } from "react";
import { api } from "../api.js";
import LoginRequired from "./LoginRequired.jsx";

// HW7 Part 4 - Bay Wheels membership vs pay-per-use advisor (ReAct/MRKL agent).
// One CSV upload, one pricing URL, one Run button; then the tool-call timeline,
// the results panel (cost comparison, decision, citations) and the metrics strip.
const OFFICIAL_URL = "https://www.lyft.com/bikes/bay-wheels/pricing";
const money = (v) => (v === null || v === undefined ? "–" : `$${Number(v).toFixed(2)}`);

export default function BikeShare({ user, onLogin }) {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState(OFFICIAL_URL);
  const [scenario, setScenario] = useState("membership_wins");
  const [promptDefense, setPromptDefense] = useState(true);
  const [toolDefense, setToolDefense] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  if (!user) return <LoginRequired action="run the bike share advisor" onLogin={onLogin} />;

  async function handleRun(e) {
    e.preventDefault();
    if (!file) { setError("Choose a trip CSV first."); return; }
    setError(""); setResult(null); setRunning(true);
    const fd = new FormData();
    fd.append("trips_csv", file);
    fd.append("pricing_url", url);
    fd.append("scenario", scenario);
    fd.append("prompt_defense", promptDefense ? "true" : "false");
    fd.append("tool_defense", toolDefense ? "true" : "false");
    try {
      setResult(await api.runBikeAgent(fd));
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  const c = result?.computed;
  const m = result?.metrics;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bay Wheels advisor</h1>
          <p className="lede">Monthly membership or pay per ride? A LangGraph ReAct agent with three MRKL
            tools (csv_sql, policy_retriever, calculator) reads your trips and the official pricing page.</p>
        </div>
      </div>

      <form className="form-card bike-form" onSubmit={handleRun}>
        <div className="field">
          <label htmlFor="csv">Trip CSV <span className="req">Required</span></label>
          <input id="csv" type="file" accept=".csv" onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>
        <div className="field">
          <label htmlFor="url">Pricing page URL <span className="req">Required</span></label>
          <input id="url" type="text" value={url} onChange={(e) => setUrl(e.target.value)} />
          <p className="hint">Part 5 fixtures: fixture:hostile_pricing_override.html, fixture:hostile_pricing_sql.html,
            fixture:hostile_pricing_exfil.html</p>
        </div>
        <div className="bike-row">
          <div className="field">
            <label htmlFor="scenario">Scenario label</label>
            <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
              <option value="membership_wins">membership_wins</option>
              <option value="payg_wins">payg_wins</option>
              <option value="adhoc">adhoc</option>
            </select>
          </div>
          <label className="check"><input type="checkbox" checked={promptDefense}
            onChange={(e) => setPromptDefense(e.target.checked)} /> Prompt defense</label>
          <label className="check"><input type="checkbox" checked={toolDefense}
            onChange={(e) => setToolDefense(e.target.checked)} /> Tool defense</label>
        </div>
        <button className="btn" type="submit" disabled={running}>
          {running ? "Running agent… (can take a few minutes)" : "Run"}
        </button>
        {error && <p className="alert alert-error" role="alert">{error}</p>}
      </form>

      {result && (
        <>
          <section className="metrics-strip" aria-label="Run metrics">
            <div><span>Steps</span><strong>{m?.step_count ?? "–"}</strong></div>
            <div><span>Agent tool calls</span><strong>{m?.agent_tool_calls ?? "–"}</strong></div>
            <div><span>Total time</span><strong>{m ? `${(m.total_time_ms / 1000).toFixed(1)} s` : "–"}</strong></div>
            <div><span>Stop reason</span><strong>{result.stop_reason}</strong></div>
            <div><span>Defenses</span><strong>{result.security.prompt_defense ? "prompt" : "–"} / {result.security.tool_defense ? "tool" : "–"}</strong></div>
            <div><span>Rows before / after</span><strong>{result.data_integrity?.rows_before} / {result.data_integrity?.rows_after ?? "dropped"}</strong></div>
          </section>

          <div className="bike-grid">
            <section className="panel">
              <h2>Tool-call timeline</h2>
              <ol className="timeline">
                {result.timeline.map((t) => (
                  <li key={t.step} className={t.success ? "ok" : "err"}>
                    <div className="tl-head">
                      <span className="tl-step">#{t.step}</span>
                      <span className={`tl-phase ${t.phase}`}>{t.phase}</span>
                      <code>{t.tool}</code>
                      <span className="tl-ms">{t.ms} ms</span>
                    </div>
                    <pre className="tl-in">{JSON.stringify(t.input)}</pre>
                    <pre className="tl-out">{t.success ? t.observation : `ERROR: ${t.error}`}</pre>
                  </li>
                ))}
              </ol>
            </section>

            <section className="panel">
              <h2>Result</h2>
              <div className="decision">
                <div><span>Agent decision</span><strong>{result.agent_decision || "(none parsed)"}</strong></div>
                <div><span>Tool-computed decision</span><strong>{c?.decision || "–"}</strong></div>
                {result.decision_agrees === false && (
                  <p className="alert alert-error">Agent decision disagrees with the tool-computed costs.</p>
                )}
              </div>
              {c?.ok ? (
                <>
                  <h3>Cost comparison ({c.riders} riders, {c.rides} rides, {c.period.days} days)</h3>
                  <table className="board small">
                    <tbody>
                      <tr><th>Pay per ride/minute (total)</th><td>{money(c.payg_total)}</td></tr>
                      <tr><th>Monthly membership fees ({c.riders} × {c.period.membership_months_per_rider} mo)</th><td>{money(c.membership_fees)}</td></tr>
                      <tr><th>Member residual charges (overage / ebike min)</th><td>{money(c.member_residual)}</td></tr>
                      <tr><th>Membership total</th><td>{money(c.membership_total)}</td></tr>
                      <tr><th>Break-even rides per rider-month</th><td>{c.break_even_rides_per_rider_month ?? "never"}</td></tr>
                      <tr><th>Actual rides per rider-month</th><td>{c.actual_rides_per_rider_month}</td></tr>
                      <tr><th>Riders cheaper with membership</th><td>{c.per_rider?.riders_cheaper_with_membership} / {c.per_rider?.riders}</td></tr>
                    </tbody>
                  </table>
                  <h3>By week</h3>
                  <table className="board small">
                    <thead><tr><th>Week of</th><th>Rides</th><th>Avg min</th><th>Pay-per-use spend</th><th>Member residual</th></tr></thead>
                    <tbody>
                      {c.weekly.map((w) => (
                        <tr key={w.week}><td>{w.week}</td><td>{w.rides}</td><td>{w.avg_duration_min}</td>
                          <td>{money(w.payg_spend)}</td><td>{money(w.member_residual_spend)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="state state-error">Cost breakdown unavailable: {c?.error}</p>
              )}
              <h3>Agent answer</h3>
              <pre className="answer">{result.final_answer || "(no final answer)"}</pre>
              <h3>Assumptions &amp; caveats</h3>
              <ul>{(c?.caveats || []).map((x) => <li key={x}>{x}</li>)}</ul>
              <h3>Citations</h3>
              <p className="hint">Pricing page: {result.snapshot?.url} → {result.snapshot?.final_url}<br />
                captured {result.snapshot?.accessed_at} · SHA-256 {result.snapshot?.sha256}</p>
              <ol className="citations">
                {result.citations.map((ct) => <li key={ct.id}>“{ct.text}”</li>)}
              </ol>
            </section>
          </div>
        </>
      )}
    </>
  );
}
