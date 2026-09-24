// 与后端 /api 交互的薄客户端。生产环境同源由 nginx 反代，开发环境由 vite 代理。

const BASE = import.meta.env.VITE_API_BASE ?? '';

export async function fetchMeta() {
  const r = await fetch(`${BASE}/api/meta`);
  if (!r.ok) throw new Error(`meta 请求失败：${r.status}`);
  return r.json();
}

export async function adjudicate(payload) {
  const r = await fetch(`${BASE}/api/adjudicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const msg = formatValidation(data);
    const err = new Error(msg || `裁决请求失败：${r.status}`);
    err.payload = data;
    throw err;
  }
  return data;
}

function formatValidation(data) {
  if (!data || !Array.isArray(data.detail)) return null;
  return data.detail
    .map((d) => {
      const loc = Array.isArray(d.loc) ? d.loc.slice(1).join(' → ') : '';
      return loc ? `${loc}：${d.msg}` : d.msg;
    })
    .join('；');
}
