"""Render an inline HTML visualizer for hidden rail-tail benchmark output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render(rows: list[dict], summary: dict) -> str:
    data = json.dumps({"summary": summary["summary"], "frames": rows}, ensure_ascii=False, separators=(",", ":"))
    return f"""<div id="hidden-rail-tail-viz" class="hidden-rail-tail-viz">
  <style>
    #hidden-rail-tail-viz {{ color: var(--foreground); }}
    #hidden-rail-tail-viz .top {{ display:flex; gap:12px; align-items:end; justify-content:space-between; flex-wrap:wrap; margin-bottom:10px; }}
    #hidden-rail-tail-viz .controls {{ display:flex; gap:10px; align-items:end; flex-wrap:wrap; }}
    #hidden-rail-tail-viz label {{ display:grid; gap:4px; color:var(--muted-foreground); }}
    #hidden-rail-tail-viz select {{ min-width:120px; }}
    #hidden-rail-tail-viz .metric-row {{ display:grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap:8px; margin:8px 0 12px; }}
    #hidden-rail-tail-viz .metric {{ padding:4px 0; }}
    #hidden-rail-tail-viz .metric b {{ display:block; font-weight:500; }}
    #hidden-rail-tail-viz .metric span {{ color:var(--muted-foreground); }}
    #hidden-rail-tail-viz .plot-wrap {{ width:100%; }}
    #hidden-rail-tail-viz svg {{ width:100%; height:auto; display:block; }}
    #hidden-rail-tail-viz .legend {{ display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-top:8px; color:var(--muted-foreground); }}
    #hidden-rail-tail-viz .key {{ display:inline-flex; align-items:center; gap:5px; }}
    #hidden-rail-tail-viz .swatch {{ width:18px; height:3px; display:inline-block; background: currentColor; }}
    #hidden-rail-tail-viz .prefix {{ color:var(--foreground); }}
    #hidden-rail-tail-viz .hidden {{ color:var(--green); }}
    #hidden-rail-tail-viz .target {{ color:var(--orange); }}
    #hidden-rail-tail-viz .pred {{ color:var(--blue); }}
    #hidden-rail-tail-viz .muted-note {{ color:var(--muted-foreground); margin-top:8px; }}
    @media (max-width: 560px) {{ #hidden-rail-tail-viz .metric-row {{ grid-template-columns:1fr 1fr; }} }}
  </style>
  <div class="top">
    <div>
      <h2>Hidden Rail Tail</h2>
      <div class="text-muted">XY view: observed prefix, hidden real tail, selected prediction</div>
    </div>
    <div class="controls">
      <label class="text-small">Frame<select id="hrt-frame" class="form-select"></select></label>
      <label class="text-small">Method<select id="hrt-method" class="form-select"></select></label>
    </div>
  </div>
  <div class="metric-row" id="hrt-metrics"></div>
  <div class="plot-wrap"><svg id="hrt-svg" role="img" aria-label="Hidden rail tail XY comparison"></svg></div>
  <div class="legend">
    <span class="key prefix"><span class="swatch"></span>observed prefix</span>
    <span class="key hidden"><span class="swatch"></span>hidden target</span>
    <span class="key pred"><span class="swatch"></span>prediction</span>
    <span class="key target"><span class="swatch"></span>target points</span>
  </div>
  <div class="text-small muted-note">Lower XY error means the continuation landed closer to the hidden observed rail-pair centres. This is not an obstacle or safety metric.</div>
  <script>
    (() => {{
      const DATA = {data};
      const root = document.getElementById('hidden-rail-tail-viz');
      const frameSelect = root.querySelector('#hrt-frame');
      const methodSelect = root.querySelector('#hrt-method');
      const svg = root.querySelector('#hrt-svg');
      const metrics = root.querySelector('#hrt-metrics');
      const methods = ['tangent','arc_last3','arc_window_clamped','ml_ridge_step'];
      const labels = {{tangent:'tangent', arc_last3:'arc last3', arc_window_clamped:'arc clamped', ml_ridge_step:'ML ridge'}};
      DATA.frames.forEach((f, i) => {{
        const option = document.createElement('option');
        option.value = i;
        option.textContent = 'frame ' + f.frame;
        frameSelect.appendChild(option);
      }});
      methods.forEach(method => {{
        const option = document.createElement('option');
        option.value = method;
        option.textContent = labels[method];
        methodSelect.appendChild(option);
      }});
      methodSelect.value = 'ml_ridge_step';
      const fmt = value => value == null ? 'n/a' : Number(value).toFixed(3);
      const pointXY = point => {{
        const xyz = point.xyz || point.predicted_xyz;
        return {{x: xyz[0], y: xyz[1]}};
      }};
      function line(points, x, y, className, width, dash) {{
        if (!points.length) return;
        const element = document.createElementNS('http://www.w3.org/2000/svg','path');
        element.setAttribute('d', points.map((point, index) => (index ? 'L' : 'M') + ' ' + x(point.x) + ' ' + y(point.y)).join(' '));
        element.setAttribute('fill', 'none');
        element.setAttribute('stroke', 'currentColor');
        element.setAttribute('stroke-width', width);
        if (dash) element.setAttribute('stroke-dasharray', dash);
        element.setAttribute('class', className);
        svg.appendChild(element);
      }}
      function dot(point, x, y, className, label) {{
        const group = document.createElementNS('http://www.w3.org/2000/svg','g');
        group.setAttribute('class', className);
        const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
        circle.setAttribute('cx', x(point.x));
        circle.setAttribute('cy', y(point.y));
        circle.setAttribute('r', '4');
        circle.setAttribute('fill', 'currentColor');
        const title = document.createElementNS('http://www.w3.org/2000/svg','title');
        title.textContent = label;
        circle.appendChild(title);
        group.appendChild(circle);
        svg.appendChild(group);
      }}
      function render() {{
        const frame = DATA.frames[Number(frameSelect.value) || 0];
        const method = methodSelect.value;
        const methodData = frame.methods[method];
        const prefix = frame.prefix.map(pointXY);
        const hidden = frame.hidden.map(pointXY);
        const predicted = methodData.predictions.filter(point => point.predicted_xyz).map(pointXY);
        const all = prefix.concat(hidden, predicted);
        const xs = all.map(point => point.x);
        const ys = all.map(point => point.y);
        const width = 736;
        const height = 430;
        const margin = {{left:58, right:18, top:22, bottom:44}};
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        const padX = Math.max(0.2, (maxX - minX) * 0.15);
        const padY = Math.max(0.5, (maxY - minY) * 0.08);
        const x = value => margin.left + (value - (minX - padX)) / (maxX - minX + 2 * padX) * (width - margin.left - margin.right);
        const y = value => margin.top + (maxY + padY - value) / (maxY - minY + 2 * padY) * (height - margin.top - margin.bottom);
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        svg.replaceChildren();
        const frameRect = document.createElementNS('http://www.w3.org/2000/svg','rect');
        frameRect.setAttribute('x', margin.left);
        frameRect.setAttribute('y', margin.top);
        frameRect.setAttribute('width', width - margin.left - margin.right);
        frameRect.setAttribute('height', height - margin.top - margin.bottom);
        frameRect.setAttribute('fill', 'none');
        frameRect.setAttribute('stroke', 'var(--border)');
        svg.appendChild(frameRect);
        for (let index = 0; index <= 4; index += 1) {{
          const gridY = margin.top + index * (height - margin.top - margin.bottom) / 4;
          const grid = document.createElementNS('http://www.w3.org/2000/svg','line');
          grid.setAttribute('x1', margin.left);
          grid.setAttribute('x2', width - margin.right);
          grid.setAttribute('y1', gridY);
          grid.setAttribute('y2', gridY);
          grid.setAttribute('stroke', 'var(--border)');
          grid.setAttribute('opacity', '.45');
          svg.appendChild(grid);
        }}
        line(prefix, x, y, 'prefix', 2.5, '');
        line(hidden, x, y, 'hidden', 3, '');
        line(predicted, x, y, 'pred', 2.5, '7 5');
        hidden.forEach((point, index) => dot(point, x, y, 'target', 'target ' + (index + 1) + ': X ' + fmt(point.x) + ' Y ' + fmt(point.y)));
        predicted.forEach((point, index) => dot(point, x, y, 'pred', 'prediction ' + (index + 1) + ': X ' + fmt(point.x) + ' Y ' + fmt(point.y)));
        [['X, m', width / 2, height - 10], ['Y, m', 18, height / 2]].forEach(item => {{
          const text = document.createElementNS('http://www.w3.org/2000/svg','text');
          text.textContent = item[0];
          text.setAttribute('x', item[1]);
          text.setAttribute('y', item[2]);
          text.setAttribute('fill', 'var(--foreground)');
          text.setAttribute('font-size', '12');
          text.setAttribute('text-anchor', 'middle');
          if (item[0][0] === 'Y') text.setAttribute('transform', 'rotate(-90 ' + item[1] + ' ' + item[2] + ')');
          svg.appendChild(text);
        }});
        const stats = methodData.summary;
        metrics.innerHTML = '';
        [['Frame', frame.frame], ['Method', labels[method]], ['Mean XY error', fmt(stats.mean_xy_error_m) + ' m'], ['p95 XY error', fmt(stats.p95_xy_error_m) + ' m']].forEach(item => {{
          const metric = document.createElement('div');
          metric.className = 'metric';
          const label = document.createElement('span');
          label.textContent = item[0];
          const value = document.createElement('b');
          value.textContent = item[1];
          metric.append(label, value);
          metrics.appendChild(metric);
        }});
      }}
      frameSelect.addEventListener('change', render);
      methodSelect.addEventListener('change', render);
      render();
    }})();
  </script>
</div>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(load_rows(args.input), json.loads(args.summary.read_text(encoding="utf-8"))), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
