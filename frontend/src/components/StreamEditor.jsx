import { useMemo, useState } from 'react';
import { parseStreamText, streamToText } from '../streamio.js';

const CODE_RE = /^[A-Z0-9]{1,8}$/;

// 单条事件流编辑器：表格逐行编辑，支持文本批量导入/导出。
export default function StreamEditor({ title, color, events, onChange }) {
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [importMsg, setImportMsg] = useState(null);

  const validation = useMemo(() => validate(events), [events]);

  const update = (idx, patch) => {
    onChange(events.map((e, k) => (k === idx ? { ...e, ...patch } : e)));
  };
  const removeRow = (idx) => onChange(events.filter((_, k) => k !== idx));
  const addRow = () => {
    const last = events.length ? events[events.length - 1].time : -1;
    onChange([...events, { time: last + 1, code: '' }]);
  };

  const doImport = () => {
    const { events: parsed, errors } = parseStreamText(importText);
    if (errors.length) {
      setImportMsg({ kind: 'error', lines: errors });
      return;
    }
    onChange(parsed);
    setImportMsg({ kind: 'ok', text: `已导入 ${parsed.length} 个事件` });
  };

  return (
    <section className={`card stream stream-${color}`}>
      <header className="card-head">
        <h2>{title}</h2>
        <span className={`badge ${validation.ok ? 'badge-ok' : 'badge-err'}`}>
          {events.length} 个事件
        </span>
      </header>

      <div className="row-hint">
        {validation.ok ? (
          <span className="muted">时间严格递增，事件码合法</span>
        ) : (
          <span className="error-text">{validation.msg}</span>
        )}
      </div>

      <div className="table-wrap">
        <table className="evt-table">
          <thead>
            <tr>
              <th className="col-idx">#</th>
              <th>时间 (0–10¹² 整数)</th>
              <th>事件码 (A–Z / 0–9，≤8 位)</th>
              <th className="col-op" />
            </tr>
          </thead>
          <tbody>
            {events.map((e, idx) => {
              const badTime = !isValidTime(e.time, idx, events);
              const badCode = !CODE_RE.test(e.code);
              return (
                <tr key={idx}>
                  <td className="col-idx">{idx}</td>
                  <td>
                    <input
                      className={badTime ? 'input-err' : ''}
                      value={e.time}
                      inputMode="numeric"
                      onChange={(ev) => update(idx, { time: ev.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className={badCode ? 'input-err' : ''}
                      value={e.code}
                      maxLength={8}
                      onChange={(ev) =>
                        update(idx, { code: ev.target.value.toUpperCase() })
                      }
                    />
                  </td>
                  <td className="col-op">
                    <button
                      type="button"
                      className="btn-mini"
                      onClick={() => removeRow(idx)}
                      title="删除该行"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="row-actions">
        <button type="button" className="btn" onClick={addRow}>
          ＋ 新增事件
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            setImportOpen((v) => !v);
            setImportText(streamToText(events));
            setImportMsg(null);
          }}
        >
          {importOpen ? '收起导入/导出' : '导入 / 导出文本'}
        </button>
      </div>

      {importOpen && (
        <div className="import-box">
          <textarea
            rows={7}
            value={importText}
            placeholder={'每行一个事件：时间,事件码\n0,TRIG\n100,A1'}
            onChange={(e) => setImportText(e.target.value)}
          />
          <div className="row-actions">
            <button type="button" className="btn" onClick={doImport}>
              应用导入
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                navigator.clipboard?.writeText(streamToText(events));
              }}
            >
              复制当前流
            </button>
          </div>
          {importMsg && (
            <div className={importMsg.kind === 'ok' ? 'ok-text' : 'error-text'}>
              {importMsg.text || importMsg.lines.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function isValidTime(value, idx, events) {
  if (!/^-?\d+$/.test(String(value))) return false;
  const t = Number(value);
  if (t < 0 || t > 10 ** 12) return false;
  if (idx > 0 && Number(events[idx - 1].time) >= t) return false;
  if (idx < events.length - 1 && Number(events[idx + 1].time) <= t) return false;
  return true;
}

function validate(events) {
  if (events.length < 2) return { ok: false, msg: '每条流至少需要 2 个事件' };
  if (events.length > 80) return { ok: false, msg: '每条流至多 80 个事件' };
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (!/^-?\d+$/.test(String(e.time)))
      return { ok: false, msg: `第 ${i} 行时间不是整数` };
    const t = Number(e.time);
    if (t < 0 || t > 10 ** 12)
      return { ok: false, msg: `第 ${i} 行时间超出 0–10¹²` };
    if (i > 0 && Number(events[i - 1].time) >= t)
      return { ok: false, msg: `第 ${i} 行时间未严格递增` };
    if (!CODE_RE.test(e.code))
      return { ok: false, msg: `第 ${i} 行事件码不合法（需 1–8 位大写字母或数字）` };
  }
  return { ok: true, msg: '' };
}
