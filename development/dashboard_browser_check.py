"""Bounded browser validation of the local handoff page and its data boundaries."""
from pathlib import Path
import copy
import json

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8099/'


def main():
    original = json.loads((ROOT / 'dashboard_handoff/snapshot.json').read_text(encoding='utf-8'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1366, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(URL)
        page.locator('#development article').first.wait_for()
        assert '本地快照，非实时' in page.locator('#source-status').inner_text()
        assert page.locator('.tab').count() == 3
        for target in ('development', 'tests', 'comparisons'):
            page.locator(f'.tab[data-tab="{target}"]').click()
            assert page.locator(f'#{target}').is_visible()
            assert page.locator(f'#{target} article').count() > 0
        page.screenshot(path=str(ROOT / 'dashboard_preview.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'mobile horizontal overflow'
        page.goto(URL + '?source=api')
        page.wait_for_function("document.querySelector('#source-status').textContent.includes('失败')")
        assert page.locator('#development article').count() == 0, 'API errors must not fall back to snapshot'

        sample = copy.deepcopy(original)
        sample['mode'] = 'demo'
        sample['comparisons'][0]['baseline']['value'] = 0
        sample['comparisons'][0]['experiment']['value'] = 10
        sample['comparisons'][0]['delta_abs'] = 999
        sample['comparisons'][0]['delta_pct'] = 666
        sample['comparisons'][1]['comparable'] = True
        sample['comparisons'][1]['baseline']['value'] = 'missing'
        sample['comparisons'][1]['experiment']['value'] = 2
        sample['comparisons'][1]['delta_abs'] = 999
        sample['comparisons'][1]['delta_pct'] = 666
        page.route('**/api/devtest', lambda route: route.fulfill(json=sample))
        page.reload()
        page.wait_for_function("document.querySelector('#comparisons').textContent.includes('冷请求')")
        assert '演示' in page.locator('#source-status').inner_text(), 'demo must not claim live'
        text = page.locator('#comparisons article').first.inner_text()
        assert '不可计算' in text and '999' not in text and '666' not in text, text
        text = page.locator('#comparisons article').nth(1).inner_text()
        assert '不计算' in text and '999' not in text, text
        assert not errors, errors
        browser.close()
    print('DASHBOARD_BROWSER_CHECK PASS: 3 tabs, snapshot label, mobile layout, API failure, demo, zero and missing baseline')


if __name__ == '__main__':
    main()
