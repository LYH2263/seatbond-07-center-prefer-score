import { useEffect, useState } from "react";
import { api } from "../api/client";

type Show = { id: number; film_title: string; hall_name?: string };
type Candidate = {
  rank: number;
  row: number;
  start_col: number;
  end_col: number;
  center: number;
  distance: number;
  score: number;
};
type Hold = {
  id: number;
  showtime_id: number;
  order_code: string;
  row: number;
  start_col: number;
  end_col: number;
  party_size: number;
};
type Preview = {
  showtime_id: number;
  party_size: number;
  hall_center: number;
  candidates: Candidate[];
};
type HoldResult = {
  hold: Hold;
  hall_center: number;
  score: number;
  distance: number;
  candidates: Candidate[];
};

export default function HoldPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [party, setParty] = useState(3);
  const [prefRow, setPrefRow] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<HoldResult | null>(null);

  useEffect(() => {
    api<Show[]>("/showtimes").then((s) => {
      setShows(s);
      if (s[0]) setSid(s[0].id);
    });
  }, []);

  function body(): Record<string, unknown> {
    const b: Record<string, unknown> = { showtime_id: sid, party_size: party };
    if (prefRow) b.preferred_row = Number(prefRow);
    return b;
  }

  async function trial() {
    setMsg("");
    setErr("");
    setResult(null);
    try {
      setPreview(await api<Preview>("/holds/preview", { method: "POST", body: JSON.stringify(body()) }));
    } catch (e) {
      setPreview(null);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function submit() {
    setMsg("");
    setErr("");
    try {
      const r = await api<HoldResult>("/holds", { method: "POST", body: JSON.stringify(body()) });
      setResult(r);
      setPreview({
        showtime_id: r.hold.showtime_id,
        party_size: r.hold.party_size,
        hall_center: r.hall_center,
        candidates: r.candidates,
      });
      const top = r.candidates[0];
      const matched =
        top &&
        top.row === r.hold.row &&
        top.start_col === r.hold.start_col &&
        top.end_col === r.hold.end_col;
      setMsg(
        `已锁座 ${r.hold.order_code}：第${r.hold.row}排 ${r.hold.start_col}-${r.hold.end_col}` +
          (matched ? "（与试算最高分段一致）" : "（警告：与试算最高分段不一致）"),
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

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
        <button onClick={trial}>试算候选段</button>
        <button onClick={submit}>查找并锁连座</button>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}
      {result && (
        <p className="mono">
          订单 {result.hold.order_code} · {result.hold.party_size} 人 · R{result.hold.row} C
          {result.hold.start_col}-{result.hold.end_col} · 得分 {result.score.toFixed(1)}（距中线{" "}
          {result.distance.toFixed(1)}）
        </p>
      )}
      {preview && (
        <>
          <h3 style={{ marginTop: "1rem" }}>
            候选段（{preview.candidates.length}）· 按居中得分降序
          </h3>
          {preview.candidates.length === 0 ? (
            <p className="err">无满足人数的连续空座</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>名次</th>
                  <th>排</th>
                  <th>起列</th>
                  <th>止列</th>
                  <th>中点</th>
                  <th>距厅中线</th>
                  <th>得分</th>
                </tr>
              </thead>
              <tbody>
                {preview.candidates.map((c) => {
                  const locked =
                    result &&
                    result.hold.row === c.row &&
                    result.hold.start_col === c.start_col &&
                    result.hold.end_col === c.end_col;
                  return (
                    <tr key={`${c.rank}-${c.row}-${c.start_col}`} style={locked ? { background: "#2a1a10" } : undefined}>
                      <td className="mono">{c.rank}</td>
                      <td>{c.row}</td>
                      <td>{c.start_col}</td>
                      <td>{c.end_col}</td>
                      <td className="mono">{c.center.toFixed(1)}</td>
                      <td className="mono">{c.distance.toFixed(1)}</td>
                      <td className="mono">
                        {c.score.toFixed(1)}
                        {locked ? " ✅ 已锁" : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}
