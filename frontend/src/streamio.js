// 事件流文本导入/导出：每行一个事件，形如 “时间,事件码”（逗号/空白/Tab 分隔）。
// 空行与 # 开头的注释行会被忽略。

export function parseStreamText(text) {
  const events = [];
  const errors = [];
  text.split(/\r?\n/).forEach((raw, idx) => {
    const line = raw.trim();
    if (!line || line.startsWith('#')) return;
    const parts = line.split(/[\s,;，；\t]+/).filter(Boolean);
    if (parts.length !== 2) {
      errors.push(`第 ${idx + 1} 行格式错误，应为 “时间,事件码”：${raw}`);
      return;
    }
    const [timeStr, code] = parts;
    if (!/^-?\d+$/.test(timeStr)) {
      errors.push(`第 ${idx + 1} 行时间不是整数：${timeStr}`);
      return;
    }
    events.push({ time: Number(timeStr), code: code.toUpperCase() });
  });
  return { events, errors };
}

export function streamToText(events) {
  return events.map((e) => `${e.time},${e.code}`).join('\n');
}
