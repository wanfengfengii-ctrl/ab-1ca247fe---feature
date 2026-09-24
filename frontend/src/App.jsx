import { useMemo, useState } from 'react';
import StreamEditor from './components/StreamEditor.jsx';
import ParamsPanel from './components/ParamsPanel.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import { adjudicate } from './api.js';

// 示例：B 卡漏记 U 脉冲，且在首个 TRIG 后计数永久跳变 +100。
// 逐条就近配对会把重复的 TRIG 接错；真实对时为 d=-5 → d=+95。
const SAMPLE_A = [
  { time: 0, code: 'TRIG' },
  { time: 100, code: 'U' },
  { time: 200, code: 'TRIG' },
  { time: 300, code: 'V' },
];
const SAMPLE_B = [
  { time: 5, code: 'TRIG' },
  { time: 105, code: 'TRIG' },
  { time: 205, code: 'V' },
];

const INT_RE = /^-?\d+$/;

export default function App() {
  const [streamA, setStreamA] = useState(SAMPLE_A);
  const [streamB, setStreamB] = useState(SAMPLE_B);
  const [params, setParams] = useState({
    offset_min: '-50',
    offset_max: '50',
    jump: '100',
    min_hits: '2',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const formValid = useMemo(
    () => validateStreams(streamA, streamB) && validateParams(params),
    [streamA, streamB, params]
  );

  const run = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        stream_a: { events: normalize(streamA) },
        stream_b: { events: normalize(streamB) },
        offset_min: Number(params.offset_min),
        offset_max: Number(params.offset_max),
        jump: Number(params.jump),
        min_hits: Number(params.min_hits),
      };
      const data = await adjudicate(payload);
      setResult(data);
    } catch (e) {
      setError(e);
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>加速器束流事件流复核台</h1>
        <p className="subtitle">
          双采集卡漏记脉冲 / 单次永久计数跳变的对时裁决：保持顺序、同码匹配、可跳事件，
          最大化命中数并输出规范首解，歧义时附第二份见证。
        </p>
      </header>

      <main className="layout">
        <div className="col col-left">
          <StreamEditor title="事件流 A（采集卡 1）" color="a" events={streamA} onChange={setStreamA} />
          <StreamEditor title="事件流 B（采集卡 2）" color="b" events={streamB} onChange={setStreamB} />
          <ParamsPanel
            params={params}
            onChange={setParams}
            onSubmit={run}
            submitting={submitting}
            formValid={formValid}
          />
        </div>
        <div className="col col-right">
          <ResultPanel result={result} error={error} />
        </div>
      </main>

      <footer className="footer">
        React + FastAPI · 所有裁决经真实业务 API <code>POST /api/adjudicate</code> 完成
      </footer>
    </div>
  );
}

function normalize(events) {
  return events.map((e) => ({ time: Number(e.time), code: e.code }));
}

function validateStreams(a, b) {
  return validStream(a) && validStream(b);
}

function validStream(events) {
  if (events.length < 2 || events.length > 80) return false;
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (!INT_RE.test(String(e.time))) return false;
    const t = Number(e.time);
    if (t < 0 || t > 10 ** 12) return false;
    if (i > 0 && Number(events[i - 1].time) >= t) return false;
    if (!/^[A-Z0-9]{1,8}$/.test(e.code)) return false;
  }
  return true;
}

function validateParams(p) {
  if (![p.offset_min, p.offset_max, p.jump, p.min_hits].every((v) => INT_RE.test(v)))
    return false;
  const lo = Number(p.offset_min);
  const hi = Number(p.offset_max);
  const j = Number(p.jump);
  const hits = Number(p.min_hits);
  if (lo > hi) return false;
  if (Math.abs(lo) > 10 ** 12 || Math.abs(hi) > 10 ** 12) return false;
  if (j < 1 || j > 2 * 10 ** 12) return false;
  if (hits < 1 || hits > 80) return false;
  return true;
}
