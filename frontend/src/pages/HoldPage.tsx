import { useEffect, useState } from "react";
import { api } from "../api/client";

type Show = { id: number; film_title: string; hall_name?: string };
type Hold = {
  id: number;
  order_code: string;
  row: number;
  start_col: number;
  end_col: number;
  party_size: number;
};
type Candidate = {
  row: number;
  start_col: number;
  end_col: number;
  seg_start_col: number;
  seg_end_col: number;
  score: number;
  distance: number;
};
type Trial = {
  showtime_id: number;
  party_size: number;
  centerline: number;
  candidates: Candidate[];
  selected: Candidate | null;
};

export default function HoldPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [party, setParty] = useState(3);
  const [prefRow, setPrefRow] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [last, setLast] = useState<Hold | null>(null);
  const [trial, setTrial] = useState<Trial | null>(null);
  const [trialKey, setTrialKey] = useState("");
  const [trialErr, setTrialErr] = useState("");

  useEffect(() => {
    api<Show[]>("/showtimes").then((s) => {
      setShows(s);
      if (s[0]) setSid(s[0].id);
    });
  }, []);

  function currentKey() {
    return `${sid}:${party}:${prefRow}`;
  }

  async function runTrial() {
    setTrialErr("");
    setTrial(null);
    try {
      const params = new URLSearchParams({ showtime_id: String(sid), party_size: String(party) });
      if (prefRow) params.set("preferred_row", prefRow);
      const data = await api<Trial>(`/trial?${params.toString()}`);
      setTrial(data);
      setTrialKey(currentKey());
    } catch (e) {
      setTrialErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function submit() {
    setMsg("");
    setErr("");
    try {
      const body: Record<string, unknown> = { showtime_id: sid, party_size: party };
      if (prefRow) body.preferred_row = Number(prefRow);
      const hold = await api<Hold>("/holds", { method: "POST", body: JSON.stringify(body) });
      setLast(hold);
      setMsg(`已锁座 ${hold.order_code}：第${hold.row}排 ${hold.start_col}-${hold.end_col}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  // The persisted block must be identical to the trial winner under the same inputs.
  const matchesTrial =
    last &&
    trial?.selected &&
    trialKey === currentKey() &&
    last.row === trial.selected.row &&
    last.start_col === trial.selected.start_col &&
    last.end_col === trial.selected.end_col;

  return (
    <>
      <h2>锁座</h2>
      <div className="toolbar">
        <select value={sid} onChange={(e) => setSid(Number(e.target.value))}>
          {shows.map((s) => (
            <option key={s.id} value={s.id}>
              {s.film_title} · {s.hall_name}
            </option>
          ))}
        </select>
        <label>
          人数{" "}
          <input
            type="number"
            min={1}
            max={12}
            value={party}
            onChange={(e) => setParty(Number(e.target.value))}
            style={{ width: 72 }}
          />
        </label>
        <label>
          优先排{" "}
          <input
            value={prefRow}
            onChange={(e) => setPrefRow(e.target.value)}
            placeholder="可选"
            style={{ width: 72 }}
          />
        </label>
        <button onClick={runTrial}>试算候选段</button>
        <button onClick={submit}>查找并锁连座</button>
      </div>
      {trialErr && <div className="err">{trialErr}</div>}
      {trial && (
        <>
          <p className="mono" style={{ margin: ".6rem 0 .3rem", fontSize: ".8rem", opacity: .8 }}>
            厅中线 {trial.centerline} · 得分 = −段中点到中线距离，越近越高；同分按排号、起始列升序
          </p>
          {trial.candidates.length === 0 ? (
            <div className="err">无满足 {trial.party_size} 人的连续空段</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>名次</th>
                  <th>排</th>
                  <th>落座起止列</th>
                  <th>所在空段</th>
                  <th>距中线</th>
                  <th>得分</th>
                </tr>
              </thead>
              <tbody>
                {trial.candidates.map((c, i) => (
                  <tr key={`${c.row}-${c.seg_start_col}`} style={i === 0 ? { background: "rgba(125,222,160,.12)" } : undefined}>
                    <td>{i + 1}{i === 0 ? " ★" : ""}</td>
                    <td>{c.row}</td>
                    <td className="mono">
                      {c.start_col}-{c.end_col}
                    </td>
                    <td className="mono">
                      {c.seg_start_col}-{c.seg_end_col}
                    </td>
                    <td className="mono">{c.distance}</td>
                    <td className="mono">{c.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}
      {last && (
        <p className="mono">
          订单 {last.order_code} · {last.party_size} 人 · R{last.row} C{last.start_col}-{last.end_col}
          {matchesTrial && <span className="ok"> ｜ ✓ 与试算首选段一致</span>}
        </p>
      )}
    </>
  );
}
