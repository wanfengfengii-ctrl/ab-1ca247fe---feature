// 裁决参数表单：允许偏移范围、固定跳变量、最低命中数。
export default function ParamsPanel({ params, onChange, onSubmit, submitting, formValid }) {
  const set = (key) => (e) => onChange({ ...params, [key]: e.target.value });

  return (
    <section className="card params">
      <header className="card-head">
        <h2>裁决参数</h2>
      </header>
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
        <label>
          <span>固定跳变量 J（≥1）</span>
          <input value={params.jump} inputMode="numeric" onChange={set('jump')} />
          <small>两段偏移之差恒为 ±J，且至多跳变一次</small>
        </label>
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
          <ol>
            <li>最大化匹配数，未达最低命中数判无解；</li>
            <li>初始偏移 d 升序；</li>
            <li>无跳变优先，其次减（d−J），再次加（d+J）；</li>
            <li>跳变前匹配数 k 升序；</li>
            <li>配对索引序列字典序。</li>
          </ol>
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
