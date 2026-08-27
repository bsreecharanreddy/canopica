import { describe, expect, test } from 'vitest';
import { contrastRatio } from './contrast';

// Real token pairs from src/index.css (Stitch-derived modern SaaS palette,
// 2026-08-27-ui-modernization-stitch-direction.md). 4.5:1 is WCAG AA for
// normal text (§1.4.3) -- every pairing actually used for body or label
// text must clear it, not just look plausible. These values were
// hand-computed before being chosen; this test is what stops a future
// token edit from silently breaking accessibility.
describe('Stitch-direction token contrast (WCAG AA, 4.5:1 for normal text)', () => {
  test('foreground on background', () => {
    expect(contrastRatio('#1b1b1d', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });

  test('foreground on card', () => {
    expect(contrastRatio('#1b1b1d', '#ffffff')).toBeGreaterThanOrEqual(4.5);
  });

  test('sidebar-foreground on sidebar', () => {
    expect(contrastRatio('#f1f5f9', '#0f172a')).toBeGreaterThanOrEqual(4.5);
  });

  test('primary on background', () => {
    expect(contrastRatio('#000000', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });

  test('primary-foreground on primary', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeGreaterThanOrEqual(4.5);
  });

  test('muted-foreground on background', () => {
    expect(contrastRatio('#475569', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });

  test('secondary-foreground on secondary', () => {
    expect(contrastRatio('#0f172a', '#e2e8f0')).toBeGreaterThanOrEqual(4.5);
  });

  test('destructive on background', () => {
    expect(contrastRatio('#b91c1c', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });

  test('destructive-foreground on destructive', () => {
    expect(contrastRatio('#ffffff', '#b91c1c')).toBeGreaterThanOrEqual(4.5);
  });

  test('amber-foreground on amber', () => {
    expect(contrastRatio('#92400e', '#fffbeb')).toBeGreaterThanOrEqual(4.5);
  });

  test('amber-foreground on background', () => {
    expect(contrastRatio('#92400e', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });

  test('ai-badge-foreground on ai-badge', () => {
    expect(contrastRatio('#1e3a8a', '#eff6ff')).toBeGreaterThanOrEqual(4.5);
  });

  test('ai-badge-foreground on background', () => {
    expect(contrastRatio('#1e3a8a', '#f8fafc')).toBeGreaterThanOrEqual(4.5);
  });
});
