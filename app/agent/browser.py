"""瀏覽器控制器(BrowserController)。

以 Playwright(headless Chromium)封裝出一組高階動作供 agent 使用。

可靠性關鍵:每次擷取頁面狀態時,會用一段 JavaScript 掃描所有「可見的互動元素」,
並在每個元素上標記 data-agent-id 屬性(從 0 開始編號),回傳一份帶編號的清單。
agent 只需用「元素編號」來指定要操作的目標,而不必處理脆弱的 CSS selector,
大幅降低因頁面結構/樣式改版而失效的風險。
"""
from __future__ import annotations

from typing import Any

from playwright.async_api import Page, async_playwright

# 觀察內容中,頁面可見文字的截斷長度(避免 token 暴增)。
_OBSERVATION_TEXT_LIMIT = 3000
# read_page 動作回傳的較完整文字長度上限。
_READ_PAGE_TEXT_LIMIT = 8000
# 單次快照最多列出的互動元素數量。
_MAX_ELEMENTS = 80

# 掃描並標記可見互動元素的 JavaScript。
# 回傳:[{index, tag, type, text, placeholder, value, href, role}, ...]
_SNAPSHOT_JS = """
(maxElements) => {
  // 先清除上一輪的標記,避免編號殘留。
  document.querySelectorAll('[data-agent-id]').forEach(
    (el) => el.removeAttribute('data-agent-id')
  );

  const SELECTOR = [
    'a[href]', 'button', 'input', 'textarea', 'select',
    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',
    '[onclick]', '[contenteditable=true]'
  ].join(',');

  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    if (parseFloat(style.opacity) === 0) return false;
    return true;
  };

  const clip = (s, n) => {
    if (!s) return '';
    s = s.replace(/\\s+/g, ' ').trim();
    return s.length > n ? s.slice(0, n) + '…' : s;
  };

  const out = [];
  let idx = 0;
  for (const el of document.querySelectorAll(SELECTOR)) {
    if (idx >= maxElements) break;
    if (!isVisible(el)) continue;
    el.setAttribute('data-agent-id', String(idx));
    const tag = el.tagName.toLowerCase();
    out.push({
      index: idx,
      tag,
      type: el.getAttribute('type') || '',
      text: clip(el.innerText || el.value || el.getAttribute('aria-label') || '', 120),
      placeholder: el.getAttribute('placeholder') || '',
      value: tag === 'input' || tag === 'textarea' ? clip(el.value || '', 80) : '',
      href: el.getAttribute('href') || '',
      role: el.getAttribute('role') || '',
    });
    idx += 1;
  }
  return out;
}
"""


class BrowserController:
    """封裝 Playwright,提供 agent 可呼叫的高階瀏覽器動作。"""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self.page: Page | None = None

    async def start(self) -> None:
        """啟動 Playwright 與瀏覽器分頁。"""
        self._pw = await async_playwright().start()
        # 在容器中以 headless 執行;加上常見旗標以提升在受限環境的穩定性。
        self._browser = await self._pw.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        )
        self._context.set_default_timeout(15000)
        self.page = await self._context.new_page()

    async def close(self) -> None:
        """關閉瀏覽器並釋放資源(容忍關閉過程中的例外)。"""
        for closer in (self._context, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

    # --- 高階動作:皆回傳一段給人/agent 看的結果字串,並盡量不拋出例外 ---

    async def navigate(self, url: str) -> str:
        """前往指定 URL。"""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await self._settle()
            return f"已開啟 {url}"
        except Exception as exc:  # noqa: BLE001 - 將錯誤轉為觀察結果回傳
            return f"開啟 {url} 失敗:{exc}"

    async def click(self, index: int) -> str:
        """點擊編號為 index 的互動元素。"""
        locator = self.page.locator(f"[data-agent-id='{index}']")
        try:
            await locator.click(timeout=8000)
            await self._settle()
            return f"已點擊元素 [{index}]"
        except Exception as exc:  # noqa: BLE001
            return f"點擊元素 [{index}] 失敗:{exc}"

    async def type_text(self, index: int, text: str, submit: bool = False) -> str:
        """在編號為 index 的輸入元素中填入文字;submit 為 true 時於最後按下 Enter。"""
        locator = self.page.locator(f"[data-agent-id='{index}']")
        try:
            await locator.fill(text, timeout=8000)
            if submit:
                await locator.press("Enter")
                await self._settle()
            return f"已在元素 [{index}] 輸入文字" + ("(並送出)" if submit else "")
        except Exception as exc:  # noqa: BLE001
            return f"在元素 [{index}] 輸入文字失敗:{exc}"

    async def scroll(self, direction: str = "down") -> str:
        """以一個視窗高度向上或向下捲動。"""
        dy = 800 if direction != "up" else -800
        try:
            await self.page.evaluate("(dy) => window.scrollBy(0, dy)", dy)
            await self.page.wait_for_timeout(300)
            return f"已向{'下' if dy > 0 else '上'}捲動"
        except Exception as exc:  # noqa: BLE001
            return f"捲動失敗:{exc}"

    async def go_back(self) -> str:
        """回到瀏覽器上一頁。"""
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=15000)
            await self._settle()
            return "已返回上一頁"
        except Exception as exc:  # noqa: BLE001
            return f"返回上一頁失敗:{exc}"

    async def read_page(self) -> str:
        """回傳目前頁面較完整的可見文字,供資料擷取使用。"""
        try:
            text = await self.page.inner_text("body")
        except Exception:
            text = ""
        return _clip(text, _READ_PAGE_TEXT_LIMIT)

    async def screenshot(self, path) -> None:
        """將目前頁面截圖存到指定路徑(失敗時略過,不中斷流程)。"""
        try:
            await self.page.screenshot(path=str(path), full_page=False)
        except Exception:
            pass

    # --- 頁面狀態擷取 ---

    async def snapshot(self) -> dict[str, Any]:
        """擷取目前頁面狀態:URL、標題、可見文字、帶編號的互動元素清單。"""
        url = self.page.url
        try:
            title = await self.page.title()
        except Exception:
            title = ""
        try:
            elements = await self.page.evaluate(_SNAPSHOT_JS, _MAX_ELEMENTS)
        except Exception:
            elements = []
        try:
            text = await self.page.inner_text("body")
        except Exception:
            text = ""
        return {
            "url": url,
            "title": title,
            "text": _clip(text, _OBSERVATION_TEXT_LIMIT),
            "elements": elements,
        }

    async def observation(self, step_no: int, max_steps: int) -> str:
        """將目前頁面狀態整理成適合餵給 Claude 的觀察字串。"""
        snap = await self.snapshot()
        lines = [
            f"STEP: {step_no}/{max_steps}",
            f"URL: {snap['url']}",
            f"TITLE: {snap['title']}",
            "",
            "VISIBLE TEXT(可見文字,已截斷):",
            snap["text"] or "(無)",
            "",
            "INTERACTIVE ELEMENTS(可操作元素,以編號指定):",
        ]
        if snap["elements"]:
            for el in snap["elements"]:
                lines.append(_format_element(el))
        else:
            lines.append("(此頁面未偵測到可操作元素)")
        return "\n".join(lines)

    async def _settle(self) -> None:
        """動作後稍作等待,讓頁面有時間完成載入/重繪。"""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            # networkidle 逾時屬正常(如持續輪詢的頁面),改以短暫固定等待。
            await self.page.wait_for_timeout(400)


def _format_element(el: dict[str, Any]) -> str:
    """將單一元素描述格式化為一行,例如:[3] <a> "comments" -> item?id=1"""
    parts = [f"[{el['index']}] <{el['tag']}"]
    if el.get("type"):
        parts.append(f" type={el['type']}")
    parts.append(">")
    label = el.get("text") or el.get("placeholder") or el.get("value") or ""
    if label:
        parts.append(f' "{label}"')
    if el.get("placeholder") and not el.get("text"):
        parts.append(f" (placeholder: {el['placeholder']})")
    if el.get("href"):
        parts.append(f" -> {_clip(el['href'], 60)}")
    return "".join(parts)


def _clip(text: str, limit: int) -> str:
    """截斷字串並保留長度資訊。"""
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"… [已截斷,共 {len(text)} 字]"
