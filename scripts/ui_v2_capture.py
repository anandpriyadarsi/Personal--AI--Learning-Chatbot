"""Capture real Flask UI with public synthetic fixture content only."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from tests.ui_v2_fixtures import live_ui


def capture(output, widths):
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    with tempfile.TemporaryDirectory(prefix='anvaya-ui-') as temp, live_ui(temp) as fixture, sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get("ANVAYA_CHROMIUM_CHANNEL"))
        for width in widths:
            height = 844 if width < 700 else 1024 if width == 768 else 768
            context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(fixture['base']) else route.abort())
            page = context.new_page()
            for name, route in fixture['routes'].items():
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                response = page.goto(fixture['base'] + route, wait_until='networkidle')
                page.screenshot(path=str(output / f'{name}-{width}.png'), full_page=True)
                manifest.append({'page': name, 'route': route, 'width': width, 'height': height,
                                 'status': response.status, 'overflow': page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'errors': errors,
                                 'screenshot': f'{name}-{width}.png'})
            context.close()
        browser.close()
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--widths', nargs='+', type=int, default=[390, 1366])
    args = parser.parse_args()
    capture(args.output, args.widths)
