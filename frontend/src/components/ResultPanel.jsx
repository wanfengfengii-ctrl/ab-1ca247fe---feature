import { useState } from 'react';

const DIR_LABEL = { none: '无跳变', minus: '减 −J', plus: '加 +J' };

// 裁决结果面板：概览 + 逐对核对表 + 歧义见证切换。
export default function ResultPanel({ result, error }) {
  const [showWitness, setShowWitness] = useState(false);
  if (error) {
    return (
      <section className="card result">
        <header className="card-head">
          <h2>裁决结果</h2>
        </header>
        <div className="banner banner-err">请求失败：{error.message}</div>
      </section>
    );
  }
  if (!result) {
    return (
      <section className="card result">
        <header className="card-head">
          <h2>裁决结果</h2>
        </header>
        <p className="muted">在左侧编辑两条事件流并设置参数，点击「发起复核裁决」。</p>
      </section>
    );
  }

  const isDrift = result.mode === 'drift';

  if (result.status === 'no_solution') {
    return (
      <section className="card result">
        <header className="card-head">
          <h2>裁决结果</h2>
          <span className="badge badge-err">无解</span>
        </header>
        <div className="banner banner-warn">{result.reason}</div>
        <dl className="summary">
          <div>
            <dt>最大可能匹配数</dt>
            <dd>{result.matched_count}</dd>
          </div>
          <div>
            <dt>最低命中数</dt>
            <dd>{result.min_hits}</dd>
          </div>
          <div>
            <dt>{isDrift ? '范围内同码配对数' : '评估偏移数 / 方案组'}</dt>
            <dd>
              {isDrift
                ? result.diagnostics.pairs_evaluated
                : `${result.diagnostics.offsets_evaluated} / ${result.diagnostics.groups_evaluated}`}
            </dd>
          </div>
        </dl>
      </section>
    );
  }

  const ambiguous = result.uniqueness === 'ambiguous';
  const solKey = isDrift ? 'drift_solution' : 'solution';
  const witKey = isDrift ? 'drift_witness' : 'witness';
  const viewing =
    ambiguous && showWitness && result[witKey] ? result[witKey] : result[solKey];
  return (
    <section className="card result">
      <header className="card-head">
        <h2>裁决结果{isDrift ? '（缓变校时）' : ''}</h2>
        <span className={`badge ${ambiguous ? 'badge-warn' : 'badge-ok'}`}>
          {ambiguous ? '歧义：存在同分方案' : '唯一规范首解'}
        </span>
      </header>

      {ambiguous && (
        <div className="toggle-row">
          <button
            type="button"
            className={`btn btn-mini ${!showWitness ? 'btn-active' : ''}`}
            onClick={() => setShowWitness(false)}
          >
            规范首解
          </button>
          <button
            type="button"
            className={`btn btn-mini ${showWitness ? 'btn-active' : ''}`}
            onClick={() => setShowWitness(true)}
          >
            歧义见证（次解）
          </button>
        </div>
      )}

      {isDrift ? (
        <>
          <DriftSummary sol={viewing} maxDrift={result.diagnostics.max_drift} />
          <DriftPairTable sol={viewing} maxDrift={result.diagnostics.max_drift} />
        </>
      ) : (
        <>
          <SolutionSummary sol={viewing} />
          <PairTable sol={viewing} />
        </>
      )}

      <dl className="summary">
        <div>
          <dt>最大匹配数 / 最低命中数</dt>
          <dd>
            {result.matched_count} / {result.min_hits}
          </dd>
        </div>
        <div>
          <dt>{isDrift ? '范围内同码配对数' : '评估偏移数 / 方案组'}</dt>
          <dd>
            {isDrift
              ? result.diagnostics.pairs_evaluated
              : `${result.diagnostics.offsets_evaluated} / ${result.diagnostics.groups_evaluated}`}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function SolutionSummary({ sol }) {
  return (
    <dl className="summary">
      <div>
        <dt>初始偏移 d</dt>
        <dd>{sol.initial_offset}</dd>
      </div>
      <div>
        <dt>跳变方向</dt>
        <dd>{DIR_LABEL[sol.jump_direction]}</dd>
      </div>
      <div>
        <dt>跳变量</dt>
        <dd>{sol.jump_amount}</dd>
      </div>
      <div>
        <dt>跳变后偏移</dt>
        <dd>{sol.offset_after === null ? '—' : sol.offset_after}</dd>
      </div>
      <div>
        <dt>跳变前匹配数 k</dt>
        <dd>{sol.pairs_before_jump}</dd>
      </div>
      <div>
        <dt>总匹配数</dt>
        <dd>{sol.matched_count}</dd>
      </div>
    </dl>
  );
}

function PairTable({ sol }) {
  // 逐对核对：索引、时间、事件码、所处相位与该对实际偏移。
  return (
    <div className="table-wrap">
      <table className="pair-table">
        <thead>
          <tr>
            <th>对</th>
            <th>A 索引</th>
            <th>B 索引</th>
            <th>时间 A</th>
            <th>时间 B</th>
            <th>事件码</th>
            <th>相位</th>
            <th>该对偏移 tA−tB</th>
            <th>对时核对</th>
          </tr>
        </thead>
        <tbody>
          {sol.pairs.map((p, idx) => {
            const expectedOffset =
              p.phase === 'before' ? sol.initial_offset : sol.offset_after;
            const aligned = p.time_a - p.time_b === p.offset && p.offset === expectedOffset;
            return (
              <tr key={idx} className={p.phase === 'before' ? 'phase-before' : 'phase-after'}>
                <td>{idx + 1}</td>
                <td>{p.index_a}</td>
                <td>{p.index_b}</td>
                <td>{p.time_a}</td>
                <td>{p.time_b}</td>
                <td className="mono">{p.code}</td>
                <td>{p.phase === 'before' ? '跳变前' : '跳变后'}</td>
                <td>{p.offset}</td>
                <td>{aligned ? '✓ 完全相等' : '✗'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {sol.pairs_before_jump >= 1 && sol.jump_direction !== 'none' && (
        <p className="muted small">
          跳变发生在第 {sol.pairs_before_jump} 对与第 {sol.pairs_before_jump + 1} 对之间：
          偏移由 {sol.initial_offset} 永久{sol.jump_direction === 'plus' ? '加' : '减'}{' '}
          {sol.jump_amount} → {sol.offset_after}。
        </p>
      )}
    </div>
  );
}

function DriftSummary({ sol, maxDrift }) {
  const changes = sol.pairs
    .map((p) => p.offset_change)
    .filter((v) => v !== null && v !== undefined);
  const maxChange = changes.length ? Math.max(...changes.map((v) => Math.abs(v))) : 0;
  return (
    <dl className="summary">
      <div>
        <dt>初始偏移 d（首对）</dt>
        <dd>{sol.initial_offset}</dd>
      </div>
      <div>
        <dt>总匹配数</dt>
        <dd>{sol.matched_count}</dd>
      </div>
      <div>
        <dt>相邻偏移最大变化</dt>
        <dd>
          {maxChange} / 上限 {maxDrift}
        </dd>
      </div>
    </dl>
  );
}

function DriftPairTable({ sol, maxDrift }) {
  // 缓变校时逐对核对：实际偏移与相对上一对的变化，供判定漂移是否连续。
  return (
    <div className="table-wrap">
      <table className="pair-table">
        <thead>
          <tr>
            <th>对</th>
            <th>A 索引</th>
            <th>B 索引</th>
            <th>时间 A</th>
            <th>时间 B</th>
            <th>事件码</th>
            <th>该对偏移 tA−tB</th>
            <th>较上一对变化</th>
            <th>对时核对</th>
          </tr>
        </thead>
        <tbody>
          {sol.pairs.map((p, idx) => {
            const aligned = p.time_a - p.time_b === p.offset;
            const change = p.offset_change;
            const changeCls =
              change === null || change === undefined
                ? ''
                : change > 0
                  ? 'change-pos'
                  : change < 0
                    ? 'change-neg'
                    : 'change-zero';
            return (
              <tr key={idx}>
                <td>{idx + 1}</td>
                <td>{p.index_a}</td>
                <td>{p.index_b}</td>
                <td>{p.time_a}</td>
                <td>{p.time_b}</td>
                <td className="mono">{p.code}</td>
                <td>{p.offset}</td>
                <td className={changeCls}>
                  {change === null || change === undefined
                    ? '—（首对）'
                    : change > 0
                      ? `+${change}`
                      : `${change}`}
                </td>
                <td>{aligned ? '✓ 完全相等' : '✗'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">
        每相邻两对的偏移变化均不超过上限 {maxDrift}；变化列为零表示两卡时钟保持同步，
        连续同号变化即为单向漂移。
      </p>
    </div>
  );
}
