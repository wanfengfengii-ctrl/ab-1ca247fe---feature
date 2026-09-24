import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_JUMP_PARAMS,
  buildPayload,
  isDriftMode,
  validateParams,
} from './params.js';

const A = [
  { time: 0, code: 'A' },
  { time: 10, code: 'B' },
];
const B = [
  { time: 2, code: 'A' },
  { time: 10, code: 'B' },
];

test('默认参数为静态跳变模式', () => {
  assert.equal(isDriftMode(DEFAULT_JUMP_PARAMS), false);
  assert.equal(validateParams(DEFAULT_JUMP_PARAMS), true);
});

test('跳变模式请求体携带 jump 且不含漂移字段', () => {
  const p = { ...DEFAULT_JUMP_PARAMS };
  const payload = buildPayload(A, B, p);
  assert.equal(payload.jump, 100);
  assert.equal('drift_mode' in payload, false);
  assert.equal('max_offset_change' in payload, false);
  assert.equal(payload.offset_min, -50);
  assert.deepEqual(payload.stream_a.events, A);
});

test('缓变模式请求体携带 drift_mode 与 max_offset_change，不携带 jump', () => {
  const p = {
    ...DEFAULT_JUMP_PARAMS,
    mode: 'drift',
    offset_min: '-10',
    offset_max: '10',
    max_offset_change: '2',
  };
  const payload = buildPayload(A, B, p);
  assert.equal(payload.drift_mode, true);
  assert.equal(payload.max_offset_change, 2);
  assert.equal('jump' in payload, false);
});

test('缓变模式 max_offset_change 允许 0（恒定偏移）', () => {
  const p = { ...DEFAULT_JUMP_PARAMS, mode: 'drift', max_offset_change: '0' };
  assert.equal(validateParams(p), true);
});

test('缓变模式拒绝负数变化上限', () => {
  const p = { ...DEFAULT_JUMP_PARAMS, mode: 'drift', max_offset_change: '-1' };
  assert.equal(validateParams(p), false);
});

test('跳变模式仍要求 jump ≥ 1，漂移参数不参与校验', () => {
  assert.equal(validateParams({ ...DEFAULT_JUMP_PARAMS, jump: '0' }), false);
  // 跳变模式下 max_offset_change 非法也不影响（该字段不参与）
  assert.equal(
    validateParams({ ...DEFAULT_JUMP_PARAMS, max_offset_change: '' }),
    true
  );
});

test('两种模式共用范围与最低命中数校验', () => {
  assert.equal(
    validateParams({ ...DEFAULT_JUMP_PARAMS, offset_min: '10', offset_max: '1' }),
    false
  );
  assert.equal(
    validateParams({
      ...DEFAULT_JUMP_PARAMS,
      mode: 'drift',
      max_offset_change: '5',
      min_hits: '0',
    }),
    false
  );
  assert.equal(
    validateParams({
      ...DEFAULT_JUMP_PARAMS,
      mode: 'drift',
      max_offset_change: 'abc',
    }),
    false
  );
});
