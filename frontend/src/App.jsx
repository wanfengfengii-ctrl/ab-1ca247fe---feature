import { useMemo, useState } from 'react';
import StreamEditor from './components/StreamEditor.jsx';
import ParamsPanel from './components/ParamsPanel.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import { adjudicate } from './api.js';
import { DEFAULT_JUMP_PARAMS, buildPayload, validateParams } from './params.js';

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

// 缓变校时示例：逐对实际偏移 -2, 0, +2, +4 —— 既非固定偏移也不是一次跳变，
// 静态模型无法四对全中；max_offset_change=2 时可全部命中。
const DRIFT_SAMPLE_A = [
  { time: 0, code: 'A' },
  { time: 10, code: 'B' },
  { time: 20, code: 'C' },
  { time: 30, code: 'D' },
];
const DRIFT_SAMPLE_B = [
  { time: 2, code: 'A' },
  { time: 10, code: 'B' },
  { time: 18, code: 'C' },
  { time: 26, code: 'D' },
];

const DRIFT_PARAMS = {
  ...DEFAULT_JUMP_PARAMS,
  mode: 'drift',
  offset_min: '-10',
  offset_max: '10',
  max_offset_change: '2',
};

const INT_RE = /^-?\d+$/;

export default function App() {
  const [streamA, setStreamA] = useState(SAMPLE_A);
  const [streamB, setStreamB] = useState(SAMPLE_B);
  const [params, setParams] = useState(DEFAULT_JUMP_PARAMS);
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
      const data = await adjudicate(buildPayload(streamA, streamB, params));
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
          双采集卡漏记脉冲的对时裁决：支持静态偏移 / 一次永久计数跳变，以及时钟在连续命中间
          缓慢漂移的「缓变校时」——保持顺序、同码匹配、可跳事件，最大化命中数并输出规范首解，
          歧义时附第二份见证。
        </p>
      </header>

      <div className="sample-row">
        <span className="muted small">载入示例：</span>
        <button
          type="button"
          className="btn btn-mini"
          onClick={() => loadSample(SAMPLE_A, SAMPLE_B, DEFAULT_JUMP_PARAMS)}
        >
          漏记 + 一次跳变
        </button>
        <button
          type="button"
          className="btn btn-mini"
          onClick={() => loadSample(DRIFT_SAMPLE_A, DRIFT_SAMPLE_B, DRIFT_PARAMS)}
        >
          连续命中间缓慢漂移
        </button>
      </div>

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

  function loadSample(a, b, p) {
    setStreamA(a.map((e) => ({ ...e })));
    setStreamB(b.map((e) => ({ ...e })));
    setParams({ ...p });
    setResult(null);
    setError(null);
  }
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
