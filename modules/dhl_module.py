import re
import time
import random
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright

PDF_DIR = r"C:\Users\pengj8\OneDrive - kochind.com\Desktop\jiangpeng\test"
INPUT_FILE = r"C:\Users\pengj8\OneDrive - kochind.com\Desktop\jiangpeng\dhl_list.xlsx"
OUTPUT_FILE = r"C:\Users\pengj8\OneDrive - kochind.com\Desktop\jiangpeng\dhl_tracking_result.xlsx"
TRACKING_COL = "tracking_number"

BASE_URL = "https://www.dhl.com/hk-en/home/tracking.html?tracking-id={tracking_number}&submit=1&inputsource=marketingstage"

MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# DHL 常见主状态。注意：Delivered 必须严格等于 Delivered 才算送达。
# 例如：Shipment is out with courier for delivery / Out for Delivery / Delivery
# 都不算 Delivered。
DHL_STATUS_EXACT_LIST = [
    "Delivered",
    "Shipment is out with courier for delivery",
    "Out for Delivery",
    "In Transit",
    "Shipment picked up",
    "Processed",
    "Departed Facility",
    "Arrived at Facility",
    "On Hold",
    "Exception",
    "Returned",
]


def normalize_tracking_number(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def normalize_status_text(text):
    """
    标准化状态文本，用于严格比较。
    只压缩空格和去掉首尾标点，不做 delivered / delivery 之类的模糊判断。
    """
    if not text:
        return ""
    text = str(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" .:：-—|\t\r\n")
    return text


def is_dhl_strict_delivered(status):
    """
    严格送达判断：只有状态文本严格等于 Delivered 才返回 True。
    不允许：
    - Out for Delivery
    - Shipment is out with courier for delivery
    - Delivery
    - delivered to service point 等扩展文本
    """
    return normalize_status_text(status).casefold() == "delivered"


def close_cookie_popup(page):
    """
    关闭 DHL cookie 弹窗。
    """
    button_texts = [
        "Accept All",
        "Accept all",
        "Accept",
        "I Accept",
        "Agree",
        "Allow all",
        "Allow All",
        "Got it",
        "USE NECESSARY COOKIES ONLY",
    ]
    for btn_text in button_texts:
        try:
            btn = page.get_by_text(btn_text, exact=False).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=2000)
                time.sleep(1)
                return True
        except Exception:
            pass
    return False


def remove_overlays(page):
    """
    删除或隐藏可能遮挡 PDF 的弹窗、浮层。
    不绕过 DHL 的认证，只处理普通弹窗和 cookie 浮层。
    """
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass

    close_selectors = [
        "button[aria-label='Close']",
        "button[aria-label*='close']",
        "button[title='Close']",
        "button[title*='close']",
        "button:has-text('×')",
        "button:has-text('X')",
        "button:has-text('Close')",
    ]
    for selector in close_selectors:
        try:
            locators = page.locator(selector)
            count = locators.count()
            for i in range(count):
                item = locators.nth(i)
                try:
                    if item.is_visible(timeout=500):
                        item.click(timeout=1000)
                        time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        page.evaluate(
            """
            (() => {
                const keywords = [
                    'cookie',
                    'cookies',
                    'privacy',
                    'consent',
                    'chat',
                    'feedback'
                ];
                const elements = Array.from(document.querySelectorAll('body *'));
                for (const el of elements) {
                    const text = (el.innerText || '').toLowerCase();
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    const isOverlay =
                        style.position === 'fixed' ||
                        style.position === 'absolute' ||
                        style.position === 'sticky';
                    const hasKeyword = keywords.some(k => text.includes(k));
                    if (
                        isOverlay &&
                        hasKeyword &&
                        rect.width > 200 &&
                        rect.height > 80 &&
                        el !== document.body &&
                        el !== document.documentElement
                    ) {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                        el.style.opacity = '0';
                        el.style.pointerEvents = 'none';
                    }
                }
            })();
            """
        )
    except Exception:
        pass


def extract_status_from_dom(page):
    """
    优先从页面主标题/醒目区域提取 DHL 主状态。
    这样可以避免 body 全文里出现 Delivered 这个词时被误判。
    """
    selectors = [
        "h1",
        "h2",
        "h3",
        "[data-testid*='status']",
        "[class*='status']",
        "[class*='headline']",
        "[class*='summary'] h1",
        "[class*='summary'] h2",
        "[class*='summary'] h3",
    ]

    candidates = []
    for selector in selectors:
        try:
            locators = page.locator(selector)
            count = min(locators.count(), 20)
            for i in range(count):
                try:
                    text = normalize_status_text(locators.nth(i).inner_text(timeout=1000))
                    if text:
                        candidates.append(text)
                except Exception:
                    pass
        except Exception:
            pass

    # 第一优先级：严格等于 Delivered
    for text in candidates:
        if is_dhl_strict_delivered(text):
            return "Delivered"

    # 第二优先级：匹配已知完整状态文本，不能用 delivered 子串判断
    for text in candidates:
        text_cf = text.casefold()
        for status in DHL_STATUS_EXACT_LIST:
            if text_cf == status.casefold():
                return status

    return ""


def extract_status_from_text(page_text):
    """
    从 body 文本中提取 DHL 主状态。
    核心原则：Delivered 必须严格作为独立主状态出现，不能因为出现 delivery/delivered 字样就算送达。
    """
    if not page_text:
        return "Unknown"

    lines = []
    for line in str(page_text).splitlines():
        line = normalize_status_text(line)
        if line:
            lines.append(line)

    # 1) 逐行严格匹配 Delivered
    for line in lines:
        if is_dhl_strict_delivered(line):
            return "Delivered"

    # 2) 逐行匹配 DHL 常见完整状态，包括截图中的状态
    for line in lines:
        line_cf = line.casefold()
        for status in DHL_STATUS_EXACT_LIST:
            if line_cf == status.casefold():
                return status

    # 3) 兼容主状态可能与其它文字在同一行的情况。
    #    只允许匹配完整状态短语，不允许把 delivery 当成 delivered。
    #    关键：Delivered 绝不走全文模糊匹配——页面任何角落出现
    #    "Delivered" 独立词（历史事件、提示文案等）都不能算送达，
    #    只能由上面的逐行严格匹配（step 1）判定。
    text = re.sub(r"\s+", " ", str(page_text))
    for status in DHL_STATUS_EXACT_LIST:
        if status == "Delivered":
            continue
        pattern = re.escape(status)
        if re.search(pattern, text, re.IGNORECASE):
            return status

    return "Unknown"


def extract_status(page, page_text):
    """
    DHL 状态提取总入口。
    先看 DOM 主标题，再看页面文本。
    """
    status = extract_status_from_dom(page)
    if status:
        return status
    return extract_status_from_text(page_text)


def extract_last_update_date(page_text):
    """
    从 DHL 页面提取 Last Update 日期。
    例如：
    Last Update: Monday, 3 August 2026 at 9:21 am (UTC +07:00)
    返回：
    raw_date = 3 August 2026
    formatted_date = 2026/8/3
    """
    if not page_text:
        return "", ""

    text = re.sub(r"\s+", " ", str(page_text))
    patterns = [
        r"Last Update\s*[:：]?\s*[A-Za-z]+,\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        r"Last updated\s*[:：]?\s*[A-Za-z]+,\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        r"[A-Za-z]+,\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+at\s+\d{1,2}:\d{2}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            year = int(match.group(3))
            month_num = MONTH_MAP.get(month_name.lower())
            if not month_num:
                continue
            raw_date = f"{day} {month_name} {year}"
            formatted_date = f"{year}/{month_num}/{day}"
            return raw_date, formatted_date

    return "", ""


def click_shipment_timeline(page):
    """
    点击 DHL 的 Shipment Timeline 标签。
    """
    selectors = [
        "button:has-text('Shipment Timeline')",
        "a:has-text('Shipment Timeline')",
        "div:has-text('Shipment Timeline')",
        "span:has-text('Shipment Timeline')",
        "text=Shipment Timeline",
    ]
    for selector in selectors:
        try:
            locators = page.locator(selector)
            count = locators.count()
            for i in range(count):
                item = locators.nth(i)
                try:
                    if item.is_visible(timeout=1000):
                        item.scroll_into_view_if_needed(timeout=2000)
                        time.sleep(0.5)
                        try:
                            item.click(timeout=3000)
                        except Exception:
                            item.click(timeout=3000, force=True)
                        time.sleep(2)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    try:
        clicked = page.evaluate(
            """
            (() => {
                const elements = Array.from(
                    document.querySelectorAll('button, a, div, span')
                );
                for (const el of elements) {
                    const text = (el.innerText || '').trim();
                    if (text.includes('Shipment Timeline')) {
                        el.scrollIntoView({
                            behavior: 'auto',
                            block: 'center'
                        });
                        el.click();
                        return true;
                    }
                }
                return false;
            })();
            """
        )
        if clicked:
            time.sleep(2)
            return True
    except Exception:
        pass

    return False


def save_dhl_pdf(page, tracking_number):
    """
    保存 DHL 当前页面为 PDF。
    文件名为运单号。
    """
    try:
        remove_overlays(page)
        time.sleep(1)

        try:
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)
        except Exception:
            pass

        pdf_file = Path(PDF_DIR) / f"{tracking_number}.pdf"
        page.pdf(
            path=str(pdf_file),
            format="A4",
            print_background=True,
            margin={
                "top": "10mm",
                "right": "10mm",
                "bottom": "10mm",
                "left": "10mm",
            },
        )
        return str(pdf_file)
    except Exception as e:
        print(f"PDF保存失败: {tracking_number}")
        print(str(e))
        return ""


def query_dhl_one(page, tracking_number):
    result = {
        "tracking_number": tracking_number,
        "status": "",
        "is_delivered": "",
        "delivery_date_raw": "",
        "delivery_date": "",
        "shipment_timeline_clicked": "",
        "pdf_file": "",
        "query_url": "",
        "error": "",
        "arrival_time": "",
    }

    if not tracking_number:
        result["error"] = "Empty tracking number"
        return result

    url = BASE_URL.format(tracking_number=quote(tracking_number))
    result["query_url"] = url

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        time.sleep(3)
        close_cookie_popup(page)
        remove_overlays(page)
        time.sleep(2)

        page_text = page.locator("body").inner_text(timeout=10000)

        blocked_words = [
            "captcha",
            "verify you are human",
            "security check",
            "access denied",
        ]
        if any(word in page_text.lower() for word in blocked_words):
            result["status"] = "Blocked"
            result["is_delivered"] = "No"
            result["error"] = "DHL blocked or captcha"
            print(f"{tracking_number} -> Blocked or captcha")
            return result

        status = extract_status(page, page_text)
        result["status"] = status

        strict_delivered = is_dhl_strict_delivered(status)
        result["is_delivered"] = "Yes" if strict_delivered else "No"

        # 重点：只有严格 Delivered 才提取送达日期、点击 timeline、保存 PDF。
        # 例如截图中的 Shipment is out with courier for delivery 不会下载 PDF，不会写送达日期。
        if strict_delivered:
            raw_date, formatted_date = extract_last_update_date(page_text)
            result["delivery_date_raw"] = raw_date
            result["delivery_date"] = formatted_date
            result["arrival_time"] = formatted_date
            timeline_clicked = click_shipment_timeline(page)
            result["shipment_timeline_clicked"] = "Yes" if timeline_clicked else "No"
            time.sleep(2)

            pdf_file = save_dhl_pdf(page, tracking_number)
            result["pdf_file"] = pdf_file
        else:
            result["delivery_date_raw"] = ""
            result["delivery_date"] = ""
            result["shipment_timeline_clicked"] = "No"
            result["pdf_file"] = ""

        print(
            f"{tracking_number} -> "
            f"status={status}, "
            f"strict_delivered={result['is_delivered']}, "
            f"date={result['delivery_date']}, "
            f"pdf={result['pdf_file']}"
        )
        return result

    except Exception as e:
        result["status"] = "Error"
        result["is_delivered"] = "No"
        result["error"] = str(e)
        print(f"{tracking_number} -> ERROR: {e}")
        return result


def warm_up_dhl(page):
    """
    预热 DHL 页面，先处理 cookie。
    """
    try:
        page.goto(
            "https://www.dhl.com/hk-en/home.html",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        time.sleep(3)
        close_cookie_popup(page)
        remove_overlays(page)
    except Exception as e:
        print(f"DHL预热失败，继续执行: {e}")


def main():
    input_path = Path(INPUT_FILE)
    Path(PDF_DIR).mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {INPUT_FILE}")

    df = pd.read_excel(INPUT_FILE, engine="openpyxl")

    if TRACKING_COL not in df.columns:
        raise ValueError(f"Excel中找不到列: {TRACKING_COL}")

    tracking_numbers = [normalize_tracking_number(x) for x in df[TRACKING_COL]]
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="en-US",
            viewport={
                "width": 1366,
                "height": 900,
            },
        )
        page = context.new_page()

        warm_up_dhl(page)

        total = len(tracking_numbers)
        for idx, tracking_number in enumerate(tracking_numbers, start=1):
            print(f"[{idx}/{total}] {tracking_number}")
            result = query_dhl_one(page, tracking_number)
            results.append(result)
            time.sleep(random.uniform(1.5, 3))

        browser.close()

    result_df = pd.DataFrame(results)

    final_df = df.copy()
    final_df["_tracking_number_clean"] = tracking_numbers
    final_df = final_df.merge(
        result_df,
        left_on="_tracking_number_clean",
        right_on="tracking_number",
        how="left",
    )

    final_df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")

    print()
    print("=" * 60)
    print("完成")
    print(OUTPUT_FILE)
    print("=" * 60)


if __name__ == "__main__":
    main()
