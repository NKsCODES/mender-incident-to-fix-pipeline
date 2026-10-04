import { useCallback, useEffect, useState } from "react";
import { api, type Attempt, type EvalRun, type Rollout, type RunDetail, type RunSummary, type Span, type Stats } from "./api";

type Tab = "overview" | "runs" | "evals" | "rollout";

const OUTCOME: Record<string, { label: string; tone: "good" | "warn" | "bad" | "muted" }> = {
  pr_draft: { label: "Draft PR", tone: "good" },
  pr_ready: { label: "PR ready", tone: "good" },
  shadow_ok: { label: "Shadow pass", tone: "good" },
  blocked: { label: "Blocked", tone: "warn" },
  verify_failed: { label: "Verify failed", tone: "warn" },
  no_fix: { label: "No fix", tone: "muted" },
  skipped: { label: "Skipped", tone: "muted" },
  error: { label: "Error", tone: "bad" },
  resolved: { label: "Resolved", tone: "good" },
  correct_block: { label: "Correct block", tone: "good" },
  false_fix: { label: "False fix", tone: "bad" },
  over_block: { label: "Over block", tone: "warn" },
  unresolved: { label: "Unresolved", tone: "warn" },
};

const ms = (v: number | null | undefined) =>
  v == null ? "n/a" : v < 1000 ? `${Math.round(v)} ms` : v < 60_000 ? `${(v / 1000).toFixed(1)} s` : `${(v / 60_000).toFixed(1)} min`;
const usd = (v: number | null | undefined) => (v == null ? "n/a" : `$${v.toFixed(v < 1 ? 3 : 2)}`);
const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);
const when = (t: number) => new Date(t * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function usePoll<T>(load: () => Promise<T>, everyMs: number): [T | null, string | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    load().then((d) => { setData(d); setError(null); }).catch((e: Error) => setError(e.message));
  }, [load]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, everyMs);
    return () => clearInterval(timer);
  }, [refresh, everyMs]);
  return [data, error, refresh];
}

function Badge({ value }: { value: string | null }) {
  if (!value) return <span className="badge muted">Running</span>;
  const o = OUTCOME[value] ?? { label: value, tone: "muted" as const };
  return <span className={`badge ${o.tone}`}>{o.label}</span>;
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {hint && <div className="tile-hint">{hint}</div>}
    </div>
  );
}

function Bars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  if (!entries.length) return <p className="empty">Nothing recorded yet.</p>;
  return (
    <div className="bars">
      {entries.map(([key, n]) => (
        <div className="bar-row" key={key}>
          <span className="bar-label">{OUTCOME[key]?.label ?? key}</span>
          <span className="bar-track"><span className={`bar-fill ${OUTCOME[key]?.tone ?? "muted"}`} style={{ width: `${(n / max) * 100}%` }} /></span>
          <span className="bar-n">{n}</span>
        </div>
      ))}
    </div>
  );
}

function Overview({ runner }: { runner?: string }) {
  const [stats, error] = usePoll<Stats>(api.stats, 4000);
  if (error) return <p className="error">{error}</p>;
  if (!stats) return <p className="empty">Loading.</p>;
  return (
    <>
      {runner === "replay" && <p className="notice">Scripted replay runner is active. Tokens and cost come from fixture values, and agent latency is replay time, not model time. Outcomes, verification and guardrails are real.</p>}
      <div className="tiles">
        <Tile label="Fix rate" value={pct(stats.fix_rate)} hint={`${stats.attempted} incidents attempted`} />
        <Tile label="PRs opened" value={String(stats.prs_opened)} hint={`${stats.occurrences_covered} error occurrences covered`} />
        <Tile label="PR accept rate" value={pct(stats.accept_rate)} hint={`${stats.reviewed} reviewed by engineers`} />
        <Tile label="Time to fix, p50" value={ms(stats.p50_time_to_fix_ms)} hint={`p95 ${ms(stats.p95_time_to_fix_ms)}`} />
        <Tile label="Cost per fix" value={usd(stats.cost_per_fix_usd)} hint={`${usd(stats.cost_usd)} total`} />
        <Tile label="Tokens" value={`${Math.round((stats.tokens_in + stats.tokens_out) / 1000)}k`} hint={`${Math.round(stats.tokens_in / 1000)}k in, ${(stats.tokens_out / 1000).toFixed(1)}k out`} />
      </div>
      <div className="grid2">
        <section className="card"><h2>Outcomes</h2><Bars data={stats.outcomes} /></section>
        <section className="card"><h2>Guardrail hits</h2><Bars data={stats.guardrail_rules} /></section>
      </div>
      <section className="card">
        <h2>Stage latency</h2>
        <table>
          <thead><tr><th>Stage</th><th className="num">Count</th><th className="num">p50</th><th className="num">p95</th></tr></thead>
          <tbody>
            {Object.entries(stats.stages).map(([name, s]) => (
              <tr key={name}><td>{name}</td><td className="num">{s.count}</td><td className="num">{ms(s.p50_ms)}</td><td className="num">{ms(s.p95_ms)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function Runs({ onOpen }: { onOpen: (id: string) => void }) {
  const [runs, error] = usePoll<RunSummary[]>(api.runs, 3000);
  if (error) return <p className="error">{error}</p>;
  if (!runs) return <p className="empty">Loading.</p>;
  if (!runs.length) return <p className="empty">No incidents yet. POST one to /api/incidents or run `make demo`.</p>;
  return (
    <section className="card flush">
      <table className="rows">
        <thead><tr><th>Incident</th><th>Outcome</th><th>Mode</th><th className="num">Seen</th><th className="num">Attempts</th><th className="num">Duration</th><th className="num">Cost</th><th>Review</th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} onClick={() => onOpen(r.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen(r.id)}>
              <td><div className="title">{r.title}</div><div className="sub">{r.service} · {when(r.created_at)} · {r.reason ?? ""}</div></td>
              <td><Badge value={r.status === "done" ? r.outcome : null} /></td>
              <td>{r.mode ?? ""}</td>
              <td className="num">{r.occurrences}</td>
              <td className="num">{r.attempts}</td>
              <td className="num">{ms(r.duration_ms)}</td>
              <td className="num">{usd(r.cost_usd)}</td>
              <td>{r.feedback ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Waterfall({ spans }: { spans: Span[] }) {
  if (!spans.length) return <p className="empty">No spans.</p>;
  const t0 = Math.min(...spans.map((s) => s.start_ms));
  const total = Math.max(1, Math.max(...spans.map((s) => s.end_ms)) - t0);
  const depth = (s: Span): number => { const p = spans.find((x) => x.id === s.parent_id); return p ? depth(p) + 1 : 0; };
  return (
    <div className="waterfall">
      {spans.map((s) => {
        const attrs = Object.entries(s.attrs).filter(([, v]) => v !== null && v !== "").map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("  ");
        return (
          <div className="wf-row" key={s.id} title={attrs}>
            <span className="wf-name" style={{ paddingLeft: depth(s) * 14 }}>{s.name}{typeof s.attrs.attempt === "number" ? ` #${s.attrs.attempt}` : ""}</span>
            <span className="wf-track">
              <span className={`wf-bar ${s.status}`} style={{ left: `${((s.start_ms - t0) / total) * 100}%`, width: `${Math.max(0.6, ((s.end_ms - s.start_ms) / total) * 100)}%` }} />
            </span>
            <span className="wf-ms">{ms(s.end_ms - s.start_ms)}</span>
          </div>
        );
      })}
    </div>
  );
}

function Diff({ text }: { text: string }) {
  return (
    <pre className="diff">
      {text.split("\n").map((line, i) => {
        const cls = line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("new file") ? "meta"
          : line.startsWith("@@") ? "hunk" : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
        return <span key={i} className={cls}>{line + "\n"}</span>;
      })}
    </pre>
  );
}

function AttemptCard({ a }: { a: Attempt }) {
  return (
    <div className="attempt">
      <div className="attempt-head">
        <strong>Attempt {a.attempt}</strong>
        <span className="sub">{a.model ?? "unknown model"} · agent time {ms(a.duration_ms)} · {a.tokens_in ?? "n/a"} in, {a.tokens_out ?? "n/a"} out</span>
      </div>
      {a.error && <p className="error">{a.error}</p>}
      {a.text && <p className="agent-text">{a.text}</p>}
      {a.tool_calls.length > 0 && (
        <div className="tools">{a.tool_calls.map((t, i) => <code key={i} className={t.ok === false ? "bad" : ""}>{t.tool} {t.path ?? t.command ?? ""}</code>)}</div>
      )}
    </div>
  );
}

function RunView({ id, onBack }: { id: string; onBack: () => void }) {
  const load = useCallback(() => api.run(id), [id]);
  const [run, error, refresh] = usePoll<RunDetail>(load, 3000);
  const [note, setNote] = useState("");
  if (error) return <p className="error">{error}</p>;
  if (!run) return <p className="empty">Loading.</p>;
  const send = (verdict: "accepted" | "rejected") => api.feedback(run.id, verdict, note).then(refresh);
  const shipped = run.outcome === "pr_draft" || run.outcome === "pr_ready";
  return (
    <>
      <button className="link" onClick={onBack}>Back to runs</button>
      <div className="run-head">
        <h1>{run.title}</h1>
        <Badge value={run.status === "done" ? run.outcome : null} />
      </div>
      <p className="sub">
        <code>{run.id}</code> · {run.service} · {run.incident.environment} · mode {run.mode} · runner {run.runner} · prompt {run.prompt_version} · seen {run.occurrences} times
        {run.reason ? ` · ${run.reason}` : ""}
      </p>
      {run.error && <p className="error">{run.error}</p>}

      <section className="card"><h2>Trace</h2><Waterfall spans={run.spans} /></section>

      <div className="grid2">
        <section className="card">
          <h2>Verification</h2>
          {run.verify ? (
            <dl>
              <dt>New regression test</dt><dd>{run.verify.new_tests.join(", ") || "none"}</dd>
              <dt>Fails before the fix</dt><dd>{run.verify.repro}</dd>
              <dt>Suite after the fix</dt><dd>{run.verify.suite_passed ? "passed" : "failed"}</dd>
            </dl>
          ) : <p className="empty">Not reached.</p>}
        </section>
        <section className="card">
          <h2>Guardrails</h2>
          {run.guardrails == null ? <p className="empty">Not reached.</p> : run.guardrails.length === 0 ? <p className="empty">No violations.</p> : (
            <ul className="violations">
              {run.guardrails.map((v, i) => <li key={i}><span className={`badge ${v.severity === "block" ? "bad" : "warn"}`}>{v.severity}</span> <strong>{v.rule}</strong><div className="sub">{v.detail}</div></li>)}
            </ul>
          )}
        </section>
      </div>

      <section className="card"><h2>Agent</h2>{run.agent?.length ? run.agent.map((a) => <AttemptCard key={a.attempt} a={a} />) : <p className="empty">The agent was not invoked.</p>}</section>
      {run.diff && <section className="card"><h2>Patch{run.branch ? <span className="sub"> on {run.branch}</span> : null}</h2><Diff text={run.diff} /></section>}

      {shipped && (
        <section className="card">
          <h2>Reviewer verdict</h2>
          <p className="sub">Rejections feed the circuit breaker and the next eval case. Current: {run.feedback ?? "none"}{run.feedback_note ? `, "${run.feedback_note}"` : ""}</p>
          <div className="feedback">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why? (optional)" aria-label="Feedback note" />
            <button onClick={() => send("accepted")}>Accepted</button>
            <button className="danger" onClick={() => send("rejected")}>Rejected</button>
          </div>
        </section>
      )}
    </>
  );
}

function Evals({ onOpen }: { onOpen: (id: string) => void }) {
  const [runs, error, refresh] = usePoll<EvalRun[]>(api.evals, 4000);
  const [busy, setBusy] = useState(false);
  if (error) return <p className="error">{error}</p>;
  if (!runs) return <p className="empty">Loading.</p>;
  const start = () => { setBusy(true); api.startEval().then(() => setTimeout(() => { refresh(); setBusy(false); }, 6000)); };
  const latest = runs[0];
  return (
    <>
      <div className="toolbar">
        <p className="sub">Each case is a captured incident plus a held-out contract test the agent never sees.</p>
        <button onClick={start} disabled={busy}>{busy ? "Running" : "Run eval suite"}</button>
      </div>
      {!latest ? <p className="empty">No eval runs yet.</p> : (
        <>
          {latest.runner === "replay" && <p className="notice">This run used the scripted replay runner. It measures the harness (verification and guardrails), not model quality. Run with the cursor runner for model numbers.</p>}
          <div className="tiles">
            <Tile label="Gate" value={latest.summary.passed ? "Pass" : "Fail"} hint={`${latest.runner} · ${latest.prompt_version}`} />
            <Tile label="Resolve rate" value={pct(latest.summary.resolve_rate)} hint={`${latest.summary.labels.resolved} of ${latest.summary.cases} cases`} />
            <Tile label="False fix rate" value={pct(latest.summary.false_fix_rate)} hint="shipped but fails held-out test" />
            <Tile label="Correct blocks" value={String(latest.summary.labels.correct_block)} hint={`${latest.summary.labels.over_block} over-blocks`} />
            <Tile label="Cost per resolved" value={usd(latest.summary.cost_per_resolved_usd)} hint={`${usd(latest.summary.total_cost_usd)} total`} />
          </div>
          {latest.summary.failures.length > 0 && <ul className="error">{latest.summary.failures.map((f) => <li key={f}>{f}</li>)}</ul>}
          <section className="card flush">
            <table className="rows">
              <thead><tr><th>Case</th><th>Label</th><th>Pipeline outcome</th><th>Held-out test</th><th className="num">Attempts</th><th className="num">Cost</th></tr></thead>
              <tbody>
                {latest.cases.map((c) => (
                  <tr key={c.case} onClick={() => onOpen(c.run_id)} tabIndex={0}>
                    <td><div className="title">{c.case}</div><div className="sub">{c.reason}</div></td>
                    <td><Badge value={c.label} /></td>
                    <td>{OUTCOME[c.outcome]?.label ?? c.outcome}</td>
                    <td>{c.heldout == null ? "n/a" : c.heldout ? "pass" : "fail"}</td>
                    <td className="num">{c.attempts}</td>
                    <td className="num">{usd(c.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="card">
            <h2>History</h2>
            <table>
              <thead><tr><th>When</th><th>Runner</th><th>Prompt</th><th className="num">Resolve</th><th className="num">False fix</th><th>Gate</th></tr></thead>
              <tbody>{runs.map((r) => <tr key={r.id}><td>{when(r.created_at)}</td><td>{r.runner}</td><td>{r.prompt_version}</td><td className="num">{pct(r.summary.resolve_rate)}</td><td className="num">{pct(r.summary.false_fix_rate)}</td><td>{r.summary.passed ? "pass" : "fail"}</td></tr>)}</tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}

function RolloutView() {
  const [data, error, refresh] = usePoll<Rollout>(api.rollout, 5000);
  const [draft, setDraft] = useState<Record<string, { mode: string; sample_pct: number }>>({});
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="empty">Loading.</p>;
  return (
    <>
      <section className={`card kill ${data.kill_switch ? "on" : ""}`}>
        <div>
          <h2>Kill switch</h2>
          <p className="sub">{data.kill_switch ? "On. Every incoming incident is skipped across all services." : "Off. Incidents are processed according to each service policy."}</p>
        </div>
        <button className={data.kill_switch ? "" : "danger"} onClick={() => api.setKill(!data.kill_switch).then(refresh)}>{data.kill_switch ? "Resume" : "Stop everything"}</button>
      </section>
      <section className="card">
        <h2>Service policies</h2>
        <p className="sub">off: ignore · shadow: run and record only · suggest: open draft PRs · auto_pr: open ready PRs</p>
        <table>
          <thead><tr><th>Service</th><th>Mode</th><th>Sample %</th><th>Circuit breaker</th><th /></tr></thead>
          <tbody>
            {data.services.map((s) => {
              const d = draft[s.service] ?? { mode: s.mode, sample_pct: s.sample_pct };
              const dirty = d.mode !== s.mode || d.sample_pct !== s.sample_pct;
              const set = (patch: Partial<typeof d>) => setDraft({ ...draft, [s.service]: { ...d, ...patch } });
              return (
                <tr key={s.service}>
                  <td>{s.service}</td>
                  <td><select value={d.mode} onChange={(e) => set({ mode: e.target.value })} aria-label="Mode">{data.modes.map((m) => <option key={m}>{m}</option>)}</select></td>
                  <td><input type="number" min={0} max={100} value={d.sample_pct} onChange={(e) => set({ sample_pct: Number(e.target.value) })} aria-label="Sample percent" /></td>
                  <td>{s.breaker.open ? <span className="badge bad">Open, held in shadow</span> : <span className="badge good">Closed</span>} <span className="sub">{s.breaker.bad} bad of last {s.breaker.window}</span></td>
                  <td><button disabled={!dirty} onClick={() => api.setPolicy(s.service, d.mode, d.sample_pct).then(() => { setDraft({}); refresh(); })}>Save</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}

export function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [open, setOpen] = useState<string | null>(null);
  const [health] = usePoll(api.health, 15000);
  const tabs: [Tab, string][] = [["overview", "Overview"], ["runs", "Runs"], ["evals", "Evals"], ["rollout", "Rollout"]];
  return (
    <div className="shell">
      <header>
        <div className="brand">Mender<span>incident to fix</span></div>
        <nav>{tabs.map(([key, label]) => <button key={key} className={tab === key && !open ? "active" : ""} onClick={() => { setTab(key); setOpen(null); }}>{label}</button>)}</nav>
        <div className="sub">{health ? `runner: ${health.runner}` : "offline"}</div>
      </header>
      <main>
        {open ? <RunView id={open} onBack={() => setOpen(null)} />
          : tab === "overview" ? <Overview runner={health?.runner} />
          : tab === "runs" ? <Runs onOpen={setOpen} />
          : tab === "evals" ? <Evals onOpen={setOpen} />
          : <RolloutView />}
      </main>
    </div>
  );
}
