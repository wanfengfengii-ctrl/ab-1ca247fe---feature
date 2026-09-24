import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseStreamText, streamToText } from './streamio.js';

test('解析标准逗号分隔并大写事件码', () => {
  const { events, errors } = parseStreamText('0,trig\n100, A1\n');
  assert.deepEqual(events, [
    { time: 0, code: 'TRIG' },
    { time: 100, code: 'A1' },
  ]);
  assert.equal(errors.length, 0);
});

test('忽略空行与注释，容忍多种分隔符', () => {
  const text = '# 注释\n\n0 X\n10\tY\n20；Z';
  const { events } = parseStreamText(text);
  assert.deepEqual(
    events.map((e) => e.code),
    ['X', 'Y', 'Z']
  );
  assert.deepEqual(
    events.map((e) => e.time),
    [0, 10, 20]
  );
});

test('格式与时间错误逐行报告', () => {
  const { events, errors } = parseStreamText('1 A B\nx, C\n3,D');
  assert.deepEqual(events, [{ time: 3, code: 'D' }]);
  assert.equal(errors.length, 2);
  assert.match(errors[0], /格式错误/);
  assert.match(errors[1], /时间不是整数/);
});

test('大整数时间不丢精度', () => {
  const { events } = parseStreamText(`${10 ** 12 - 1},CODE1234`);
  assert.equal(events[0].time, 10 ** 12 - 1);
  assert.equal(events[0].code, 'CODE1234');
});

test('导出往返', () => {
  const events = [
    { time: 0, code: 'A' },
    { time: 25, code: 'B7' },
  ];
  assert.equal(streamToText(events), '0,A\n25,B7');
  assert.deepEqual(parseStreamText(streamToText(events)).events, events);
});
