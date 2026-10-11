"""Render the changed paper section at desktop and mobile sizes."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    html = ROOT / 'paper/FreeToken_MultiGPU_CoExec_v5.2.html'
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width in [('desktop', 1280), ('mobile', 390)]:
            page = browser.new_page(viewport={'width': width, 'height': 900})
            page.goto(html.as_uri(), wait_until='networkidle')
            page.locator('#s8').scroll_into_view_if_needed()
            info = page.evaluate('''() => ({width: innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
                svg: document.querySelectorAll('svg').length,
                tables: document.querySelectorAll('table').length,
                mathErrors: document.querySelectorAll('.katex-error').length,
                badAnchors: [...document.querySelectorAll('a[href^="#"]')].filter(a => !document.getElementById(a.hash.slice(1))).map(a => a.hash),
                s8Text: document.querySelector('#s8').innerText})''')
            assert info['scrollWidth'] <= width
            assert not info['mathErrors'] and not info['badAnchors']
            assert '22.03–22.53' in info.pop('s8Text')
            page.screenshot(path=str(HERE / f'{label}_s8.png'), full_page=False)
            info['label'] = label
            results.append(info)
            page.close()
        browser.close()
    receipt = {'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'html_sha256': hashlib.sha256(html.read_bytes()).hexdigest(), 'viewports': results, 'passed': True}
    (HERE / 'RENDER_CHECK.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
