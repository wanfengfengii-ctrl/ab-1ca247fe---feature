// 裁决参数表单：允许偏移范围、固定跳变量 / 缓变校时上限、最低命中数。
export default function ParamsPanel({ params, onChange, onSubmit, submitting, formValid }) {
  const set = (key) => (e) => onChange({ ...params, [key]: e.target.value });
  const setDrift = (e) => onChange({ ...params, drift_mode: e.target.checked });

  return (
    <section className="card params">
      <header className="card-head">
        <h2>裁决参数</h2>
      </header>

      <label className={`drift-toggle ${params.drift_mode ? 'active' : ''}`}>
        <input type="checkbox" checked={params.drift_mode} onChange={setDrift} />
        <span>
          <strong>缓变校时</strong>：时钟在连续命中间缓慢漂移（而非一次突跳）时启用。
          启用后不再使用固定跳变量，改为约束每相邻已匹配事件的整数偏移变化上限。
        </span>
      </label>

      <div className="params-grid">
        <label>
          <span>初始偏移下界</span>
          <input
            value={params.offset_min}
            inputMode="numeric"
            onChange={set('offset_min')}
          />
          <small>d = tA − tB，范围内整数</small>
        </label>
        <label>
          <span>初始偏移上界</span>
          <input
            value={params.offset_max}
            inputMode="numeric"
            onChange={set('offset_max')}
          />
          <small>含端点</small>
        </label>
        {params.drift_mode ? (
          <label>
            <span>相邻对最大偏移变化（≥0）</span>
            <input
              value={params.max_drift}
              inputMode="numeric"
              onChange={set('max_drift')}
            />
            <small>每相邻两对已匹配事件的偏移之差绝对值不超过该整数</small>
          </label>
        ) : (
          <label>
            <span>固定跳变量 J（≥1）</span>
            <input value={params.jump} inputMode="numeric" onChange={set('jump')} />
            <small>两段偏移之差恒为 ±J，且至多跳变一次</small>
          </label>
        )}
        <label>
          <span>最低命中数（1–80）</span>
          <input
            value={params.min_hits}
            inputMode="numeric"
            onChange={set('min_hits')}
          />
          <small>最大匹配数不足即判无解</small>
        </label>
      </div>

      <div className="rule-note">
        <details>
          <summary>规范首解同分排序规则</summary>
          {params.drift_mode ? (
            <ol>
              <li>最大化匹配数，未达最低命中数判无解；</li>
              <li>初始偏移 d（首对 tA−tB）升序；</li>
              <li>配对索引序列字典序。</li>
            </ol>
          ) : (
            <ol>
              <li>最大化匹配数，未达最低命中数判无解；</li>
              <li>初始偏移 d 升序；</li>
              <li>无跳变优先，其次减（d−J），再次加（d+J）；</li>
              <li>跳变前匹配数 k 升序；</li>
              <li>配对索引序列字典序。</li>
            </ol>
          )}
        </details>
      </div>

      <button
        type="button"
        className="btn btn-primary btn-lg"
        onClick={onSubmit}
        disabled={submitting || !formValid}
      >
        {submitting ? '裁决中…' : '发起复核裁决'}
      </button>
    </section>
  );
}
