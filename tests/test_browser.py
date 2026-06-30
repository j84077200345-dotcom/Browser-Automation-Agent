"""瀏覽器控制器的離線整合測試。

不需網路:以 page.set_content 載入內嵌 HTML,驗證「帶編號互動元素快照」這個
核心可靠性機制是否正確標記可見元素、忽略隱藏元素,並能以編號操作元素。
"""
from __future__ import annotations

from app.agent.browser import BrowserController

_HTML = """
<html><body>
  <h1>Hello world</h1>
  <p>一些可見的內文文字,用來驗證 read_page。</p>
  <a href="/page2">Go to page 2</a>
  <button id="b">Click me</button>
  <input type="text" placeholder="search box">
  <div style="display:none"><a href="/hidden">hidden link</a></div>
</body></html>
"""


async def test_snapshot_indexes_visible_elements():
    b = BrowserController(headless=True)
    await b.start()
    try:
        await b.page.set_content(_HTML)
        snap = await b.snapshot()
        texts = [e["text"] for e in snap["elements"]]

        # 應抓到可見的連結、按鈕、輸入框。
        assert any("Go to page 2" in t for t in texts)
        assert any("Click me" in t for t in texts)
        # 隱藏元素(display:none)不應被列入。
        assert not any("hidden link" in t for t in texts)
        # index 應為從 0 開始的連續整數。
        indices = [e["index"] for e in snap["elements"]]
        assert indices == list(range(len(indices)))
        # 可見文字應被擷取。
        assert "可見的內文文字" in snap["text"]
    finally:
        await b.close()


async def test_type_text_by_index():
    b = BrowserController(headless=True)
    await b.start()
    try:
        await b.page.set_content(_HTML)
        snap = await b.snapshot()
        input_idx = next(e["index"] for e in snap["elements"] if e["tag"] == "input")

        msg = await b.type_text(input_idx, "hello world")
        assert "輸入文字" in msg

        value = await b.page.locator(f"[data-agent-id='{input_idx}']").input_value()
        assert value == "hello world"
    finally:
        await b.close()


async def test_click_failure_is_graceful():
    """點擊不存在的編號應回傳錯誤字串,而非拋出例外。"""
    b = BrowserController(headless=True)
    await b.start()
    try:
        await b.page.set_content(_HTML)
        await b.snapshot()
        msg = await b.click(999)
        assert "失敗" in msg
    finally:
        await b.close()
