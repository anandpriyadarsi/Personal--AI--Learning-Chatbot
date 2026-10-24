"""Reproduce rough fixture server-render weight/timing, never production data."""
import argparse
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jinja2 import DictLoader
from tests.ui_v2_fixtures import build_ui_fixture


def measure(output, baseline):
    repo = Path(__file__).resolve().parents[1]
    prefix = 'personal_learning_assistant/ui/web/templates/'
    files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', baseline, prefix], cwd=repo, text=True).splitlines()
    templates = {name[len(prefix):]: subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=repo).decode('utf-8') for name in files}
    report = {'baseline_ref': baseline, 'method': 'Same disposable Flask services; before uses Git baseline templates, after current templates. Median of 7 warmed requests. Server render only, not network/browser latency; no performance guarantee.', 'measurements': []}
    with tempfile.TemporaryDirectory(prefix='anvaya-ui-metrics-') as temp:
        fixture = build_ui_fixture(Path(temp))
        app = fixture['app']; original = app.jinja_loader
        for version, loader in [('before', DictLoader(templates)), ('after', original)]:
            app.jinja_loader = loader; app.jinja_env.cache.clear()
            for surface in ('home','vault','obsidian-reader','notes','knowledge'):
                client = app.test_client(); route = fixture['routes'][surface]
                client.get(route)
                timings = []
                for _ in range(7):
                    start = time.perf_counter(); response = client.get(route)
                    timings.append((time.perf_counter() - start) * 1000)
                    assert response.status_code == 200
                html = response.get_data(as_text=True)
                assets = set(re.findall(r'(?:href|src)="/static/([^"?]+\.(?:css|js))', html))
                weight = 0
                for asset in assets:
                    name = 'personal_learning_assistant/ui/web/static/' + asset
                    weight += len(subprocess.check_output(['git','show',baseline+':'+name], cwd=repo)) if version == 'before' else (repo/name).stat().st_size
                report['measurements'].append({'version':version,'surface':surface,'html_bytes':len(response.data),'css_js_bytes':weight,'render_median_ms':round(statistics.median(timings),2)})
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', default='7906aa590bb663fffce8090e3d3a0158fa64c02f')
    args = parser.parse_args(); measure(args.output,args.baseline)
