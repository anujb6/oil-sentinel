/* Oil Sentinel: stocks vs forecast chart. Plain SVG, no libraries, text via textContent. */
'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';
const CHART_WEEKS = 26;
const CHART_HEIGHT = 240;
const PAD = { top: 14, right: 14, bottom: 30, left: 46 };
const DOT_RADIUS = 4.5;
const NEXT_DOT_RADIUS = 6;
const Y_TICKS = 4;

class ForecastChart {
  /**
   * @param {HTMLElement} plot   element the SVG is drawn into
   * @param {HTMLElement} readout element showing the value under the crosshair
   * @param {HTMLElement} table  tbody for the accessible table view
   */
  constructor(plot, readout, table) {
    this.plot = plot;
    this.readout = readout;
    this.table = table;
    this.points = [];
    this.active = -1;
    this.mode = 'level';
    if ('ResizeObserver' in window) {
      let width = 0;
      new ResizeObserver(entries => {
        const w = Math.round(entries[0].contentRect.width);
        if (w && w !== width) { width = w; this.draw(); }
      }).observe(plot);
    }
  }

  /** series: {history:[{date,mb}]}, forecast: {recent:[...], target_week, change_mb, low_mb, high_mb} */
  update(series, forecast, mode) {
    this.mode = mode;
    this.points = ForecastChart.buildPoints(series, forecast, mode);
    this.active = this.points.length - 1;
    this.draw();
    this.fillTable();
  }

  static buildPoints(series, forecast, mode) {
    const history = (series?.history || []).filter(p => Number.isFinite(p.mb));
    const levelOn = new Map(history.map(p => [p.date, p.mb]));
    const forecastOn = new Map((forecast?.recent || []).map(r => [r.week, r.forecast_mb]));
    const points = [];
    const start = Math.max(1, history.length - CHART_WEEKS);
    for (let i = start; i < history.length; i++) {
      const prev = history[i - 1].mb, cur = history[i].mb, change = cur - prev;
      const fc = forecastOn.get(history[i].date);
      const hasFc = typeof fc === 'number' && Number.isFinite(fc);
      points.push({
        date: history[i].date, next: false,
        actualChange: change, actualLevel: cur,
        forecastChange: hasFc ? fc : null,
        forecastLevel: hasFc ? prev + fc : null,
        actual: mode === 'level' ? cur : change,
        forecast: hasFc ? (mode === 'level' ? prev + fc : fc) : null,
      });
    }
    const last = history[history.length - 1];
    if (last && forecast && Number.isFinite(forecast.change_mb) && forecast.target_week > last.date) {
      const base = mode === 'level' ? last.mb : 0;
      points.push({
        date: forecast.target_week, next: true,
        actual: null, actualChange: null, actualLevel: null,
        forecast: base + forecast.change_mb, forecastChange: forecast.change_mb, forecastLevel: last.mb + forecast.change_mb,
        low: base + forecast.low_mb, high: base + forecast.high_mb, lowChange: forecast.low_mb, highChange: forecast.high_mb,
      });
    }
    return points;
  }

  // ---------- drawing ----------
  draw() {
    const plot = this.plot;
    plot.replaceChildren();
    if (this.points.length < 3) {
      const p = document.createElement('p');
      p.className = 'small-muted';
      p.textContent = 'Not enough history to draw the chart yet.';
      plot.append(p);
      this.readout.textContent = '';
      return;
    }
    const width = Math.max(plot.clientWidth || 340, 280);
    const height = CHART_HEIGHT;
    const svg = this.el('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', tabindex: '0',
      'aria-label': this.mode === 'level' ? 'Stock level with past and next forecasts. Use arrow keys to move between weeks.' : 'Weekly change versus forecast. Use arrow keys to move between weeks.' });
    const pts = this.points;
    const values = [];
    for (const p of pts) {
      for (const v of [p.actual, p.forecast, p.low, p.high]) if (typeof v === 'number' && Number.isFinite(v)) values.push(v);
    }
    if (this.mode === 'change') values.push(0);
    let lo = Math.min(...values), hi = Math.max(...values);
    if (hi - lo < 0.4) { lo -= 0.2; hi += 0.2; }
    const ticks = ForecastChart.niceTicks(lo, hi, Y_TICKS);
    lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
    const innerW = width - PAD.left - PAD.right, innerH = height - PAD.top - PAD.bottom;
    const step = innerW / pts.length;
    const x = i => PAD.left + step * (i + 0.5);
    const y = v => PAD.top + (1 - (v - lo) / (hi - lo)) * innerH;
    this.geom = { x, y, step, width, height };

    // grid + y labels (recessive)
    const decimals = (hi - lo) < 4 ? 1 : 0;
    for (const t of ticks) {
      svg.append(this.el('line', { x1: PAD.left, x2: width - PAD.right, y1: y(t), y2: y(t), class: t === 0 && this.mode === 'change' ? 'c-zero' : 'c-grid' }));
      svg.append(this.text(PAD.left - 8, y(t) + 4, `${t.toFixed(decimals)}`, 'c-axis', 'end'));
    }
    // "next report" column
    const n = pts.length - 1;
    if (pts[n].next) {
      svg.append(this.el('rect', { x: x(n) - step / 2, y: PAD.top, width: step, height: innerH, class: 'c-next-col' }));
    }
    // x labels: first, middle, last actual, next
    // Dates sit under first, middle and last weeks; "Next" replaces the last date when there is no room for both.
    const lastActual = pts[n].next ? n - 1 : n;
    const labelIdx = [0, Math.floor(lastActual / 2)];
    if (!pts[n].next || step >= 56) labelIdx.push(lastActual);
    for (const i of labelIdx) svg.append(this.text(x(i), height - 9, ForecastChart.short(pts[i].date), 'c-axis', i === 0 ? 'start' : (i === n ? 'end' : 'middle')));
    if (pts[n].next) svg.append(this.text(Math.min(x(n) + step / 2, width - PAD.right), height - 9, 'Next', 'c-axis c-axis-strong', 'end'));

    if (this.mode === 'level') this.drawLevels(svg, pts, x, y);
    else this.drawChanges(svg, pts, x, y, step);
    this.drawNext(svg, pts[n], n, x, y, pts);

    // crosshair + hit layer
    this.hair = this.el('line', { y1: PAD.top, y2: PAD.top + innerH, class: 'c-hair' });
    svg.append(this.hair);
    const hit = this.el('rect', { x: PAD.left, y: 0, width: innerW, height, class: 'c-hit' });
    const pick = ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) * (width / r.width);
      this.setActive(Math.max(0, Math.min(pts.length - 1, Math.floor((px - PAD.left) / step))));
    };
    hit.addEventListener('pointermove', pick);
    hit.addEventListener('pointerdown', pick);
    svg.addEventListener('pointerleave', () => this.setActive(pts.length - 1));
    svg.addEventListener('keydown', ev => {
      if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
        ev.preventDefault();
        this.setActive(Math.max(0, Math.min(pts.length - 1, this.active + (ev.key === 'ArrowLeft' ? -1 : 1))));
      }
    });
    svg.append(hit);
    plot.append(svg);
    this.setActive(this.active >= 0 && this.active < pts.length ? this.active : pts.length - 1);
  }

  drawLevels(svg, pts, x, y) {
    const actual = pts.map((p, i) => [i, p.actual]).filter(([, v]) => v !== null);
    const line = actual.map(([i, v], k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
    const baseY = this.geom.height - PAD.bottom;
    const [fi] = actual[0], [li] = actual[actual.length - 1];
    svg.append(this.el('path', { d: `${line}L${x(li).toFixed(1)},${baseY}L${x(fi).toFixed(1)},${baseY}Z`, class: 'c-area' }));
    svg.append(this.el('path', { d: line, class: 'c-actual-line' }));
    pts.forEach((p, i) => {
      if (!p.next && p.forecast !== null) svg.append(this.el('circle', { cx: x(i), cy: y(p.forecast), r: DOT_RADIUS, class: 'c-fc-dot' }));
    });
  }

  drawChanges(svg, pts, x, y, step) {
    const barW = Math.max(3, Math.min(14, step * 0.55));
    const zero = y(0);
    pts.forEach((p, i) => {
      if (p.actual === null) return;
      const top = y(p.actual);
      svg.append(this.el('path', { d: ForecastChart.bar(x(i) - barW / 2, zero, barW, top), class: 'c-bar' }));
    });
    pts.forEach((p, i) => {
      if (!p.next && p.forecast !== null) svg.append(this.el('circle', { cx: x(i), cy: y(p.forecast), r: DOT_RADIUS, class: 'c-fc-dot' }));
    });
  }

  drawNext(svg, p, i, x, y, pts) {
    if (!p.next) return;
    const w = Math.max(8, Math.min(16, this.geom.step * 0.6));
    const top = y(p.high), bottom = y(p.low);
    svg.append(this.el('rect', { x: x(i) - w / 2, y: top, width: w, height: Math.max(2, bottom - top), rx: 4, class: 'c-range' }));
    if (this.mode === 'level') {
      const prev = pts[i - 1];
      svg.append(this.el('line', { x1: x(i - 1), y1: y(prev.actual), x2: x(i), y2: y(p.forecast), class: 'c-fc-link' }));
    }
    svg.append(this.el('circle', { cx: x(i), cy: y(p.forecast), r: NEXT_DOT_RADIUS, class: 'c-fc-next' }));
  }

  setActive(i) {
    if (!this.geom || !this.points[i]) return;
    this.active = i;
    const xi = this.geom.x(i);
    this.hair.setAttribute('x1', xi);
    this.hair.setAttribute('x2', xi);
    this.renderReadout(this.points[i]);
  }

  renderReadout(p) {
    const r = this.readout;
    r.replaceChildren();
    const fmt = v => (v > 0 ? '+' : '') + v.toFixed(Math.abs(v) < 10 ? 2 : 1);
    const fmt1 = v => (v > 0 ? '+' : '') + v.toFixed(1);
    const date = document.createElement('span');
    date.className = 'c-read-date';
    date.textContent = p.next ? `Next report · week ending ${ForecastChart.long(p.date)}` : `Week ending ${ForecastChart.long(p.date)}`;
    r.append(date);
    const row = (key, value, label) => {
      const item = document.createElement('span');
      item.className = 'c-read-item';
      const k = document.createElement('i');
      k.className = `c-key ${key}`;
      const strong = document.createElement('strong');
      strong.textContent = value;
      const small = document.createElement('small');
      small.textContent = label;
      item.append(k, strong, small);
      r.append(item);
    };
    if (p.next) {
      row('fc', `${fmt(p.forecastChange)}M`, `forecast change · likely ${fmt1(p.lowChange)} to ${fmt1(p.highChange)}M`);
      if (this.mode === 'level') row('fc', `${p.forecastLevel.toFixed(2)}M`, 'forecast stock level');
      return;
    }
    row('actual', `${fmt(p.actualChange)}M`, `actual change · stock ${p.actualLevel.toFixed(2)}M`);
    if (p.forecastChange !== null) {
      const miss = p.actualChange - p.forecastChange;
      row('fc', `${fmt(p.forecastChange)}M`, `forecast · missed by ${Math.abs(miss).toFixed(2)}M`);
    }
  }

  fillTable() {
    const rows = this.points.slice().reverse().slice(0, 13);
    const fmt = v => (typeof v === 'number' ? (v > 0 ? '+' : '') + v.toFixed(2) : '—');
    this.table.replaceChildren(...rows.map(p => {
      const tr = document.createElement('tr');
      const cells = [p.next ? `${ForecastChart.short(p.date)} (next)` : ForecastChart.short(p.date), fmt(p.actualChange), fmt(p.forecastChange),
        p.next ? `${fmt(p.lowChange)} to ${fmt(p.highChange)}` : (p.forecastChange === null ? '—' : Math.abs(p.actualChange - p.forecastChange).toFixed(2))];
      for (const c of cells) { const td = document.createElement('td'); td.textContent = c; tr.append(td); }
      return tr;
    }));
  }

  // ---------- helpers ----------
  el(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  }

  text(xp, yp, content, cls, anchor) {
    const t = this.el('text', { x: xp, y: yp, class: cls, 'text-anchor': anchor });
    t.textContent = content;
    return t;
  }

  /** Bar from the zero line to `top`, rounded only at the data end. */
  static bar(x0, zero, w, top) {
    const h = Math.abs(zero - top);
    const r = Math.min(4, w / 2, h);
    if (h < 0.5) return `M${x0},${zero}h${w}`;
    if (top < zero) return `M${x0},${zero}V${top + r}Q${x0},${top} ${x0 + r},${top}H${x0 + w - r}Q${x0 + w},${top} ${x0 + w},${top + r}V${zero}Z`;
    return `M${x0},${zero}V${top - r}Q${x0},${top} ${x0 + r},${top}H${x0 + w - r}Q${x0 + w},${top} ${x0 + w},${top - r}V${zero}Z`;
  }

  static niceTicks(lo, hi, count) {
    const raw = (hi - lo) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || 10 * mag;
    const ticks = [];
    const top = Math.ceil(hi / step - 1e-9) * step;
    for (let v = Math.floor(lo / step) * step; v <= top + step * 0.001; v += step) ticks.push(Math.round(v / step) * step);
    return ticks;
  }

  static short(iso) {
    const d = new Date(`${iso}T12:00:00Z`);
    return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  }

  static long(iso) {
    const d = new Date(`${iso}T12:00:00Z`);
    return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  }
}

window.ForecastChart = ForecastChart;
