// 裁决参数：模式（静态/一次跳变 ↔ 缓变校时）、表单校验与请求体构造。
// 纯函数，供前端与 node --test 单测共用。

export const INT_RE = /^-?\d+$/;

export const DEFAULT_JUMP_PARAMS = {
  mode: 'jump',
  offset_min: '-50',
  offset_max: '50',
  jump: '100',
  max_offset_change: '5',
  min_hits: '2',
};

export function isDriftMode(params) {
  return params.mode === 'drift';
}

export function validateParams(p) {
  const drift = isDriftMode(p);
  const modeFields = drift ? [p.max_offset_change] : [p.jump];
  if (![p.offset_min, p.offset_max, p.min_hits, ...modeFields].every((v) => INT_RE.test(v)))
    return false;
  const lo = Number(p.offset_min);
  const hi = Number(p.offset_max);
  const hits = Number(p.min_hits);
  if (lo > hi) return false;
  if (Math.abs(lo) > 10 ** 12 || Math.abs(hi) > 10 ** 12) return false;
  if (hits < 1 || hits > 80) return false;
  if (drift) {
    const c = Number(p.max_offset_change);
    if (c < 0 || c > 2 * 10 ** 12) return false;
  } else {
    const j = Number(p.jump);
    if (j < 1 || j > 2 * 10 ** 12) return false;
  }
  return true;
}

// 构造 /api/adjudicate 请求体：跳变模式发 jump；缓变模式发
// drift_mode + max_offset_change，不携带 jump。
export function buildPayload(streamA, streamB, params) {
  const normalize = (events) =>
    events.map((e) => ({ time: Number(e.time), code: e.code }));
  const payload = {
    stream_a: { events: normalize(streamA) },
    stream_b: { events: normalize(streamB) },
    offset_min: Number(params.offset_min),
    offset_max: Number(params.offset_max),
    min_hits: Number(params.min_hits),
  };
  if (isDriftMode(params)) {
    payload.drift_mode = true;
    payload.max_offset_change = Number(params.max_offset_change);
  } else {
    payload.jump = Number(params.jump);
  }
  return payload;
}
