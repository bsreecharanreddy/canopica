import { describe, expect, test } from 'vitest';
import { contrastRatio } from './contrast';

// Real Public Ledger token pairs from src/index.css. 4.5:1 is WCAG AA
// for normal text (§1.4.3) -- every pairing actually used for body or
// label text must clear it, not just look plausible. These values were
// hand-computed before being chosen (design doc §7); this test is what
// stops a future token edit from silently breaking accessibility.
describe('Public Ledger token contrast (WCAG AA, 4.5:1 for normal text)', () => {
  test('foreground on background', () => {
    expect(contrastRatio('#1b2b26', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });

  test('sidebar-foreground on sidebar', () => {
    expect(contrastRatio('#f7f3e9', '#17221f')).toBeGreaterThanOrEqual(4.5);
  });

  test('primary (verdigris) on background', () => {
    expect(contrastRatio('#167c6b', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });

  test('muted-foreground on background', () => {
    expect(contrastRatio('#56665e', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });

  test('amber-foreground on background', () => {
    expect(contrastRatio('#8a672c', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });

  test('amber-foreground on amber', () => {
    expect(contrastRatio('#8a672c', '#fbf3e7')).toBeGreaterThanOrEqual(4.5);
  });

  test('destructive on background', () => {
    expect(contrastRatio('#a13f2e', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });

  test('info on background', () => {
    expect(contrastRatio('#2f5f8a', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
  });
});
