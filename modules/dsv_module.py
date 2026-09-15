import re
import time
import random
from pathlib import Path
from urllib.parse import urljoin

from modules.status_rules import matches_exact_status


CUSTOM_DELIVERED_STATUSES = ()


def is_dsv_delivered(status):
    return matches_exact_status(
        status,
        default_statuses=("Completed", "Delivered"),
        custom_statuses=CUSTOM_DELIVERED_STATUSES,
    )


PDF_DIR = r"output\pdf\DSV"

BASE_URL = "https://mydsv.com/new/tracking/track-shipment"

MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def make_result(tracking_number):
    return {
        "tracking_number": tracking_number,
        "status": "",
        "is_delivered": False,
        "arrival_time": "",
        "pdf_file": "",
        "error": "",
    }


def wait_page_ready(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass


def accept_dsv_cookie(page):
    button_keywords = [
        "OK",
        "USE NECESSARY COOKIES ONLY",
        "ACCEPT",
        "ACCEPT ALL",
        "ALLOW ALL",
        "AGREE",
        "I ACCEPT",
    ]

    for frame in page.frames:
        try:
            buttons = frame.locator("button")
            count = buttons.count()

            for i in range(count):
                try:
                    btn = buttons.nth(i)

                    if not btn.is_visible(timeout=500):
                        continue

                    text = btn.inner_text(timeout=1000).strip()
                    text_upper = re.sub(r"\s+", " ", text).upper()

                    if text_upper in button_keywords:
                        btn.click(timeout=3000)
                        print(f"Cookie已关闭: {text}")
                        time.sleep(2)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    for frame in page.frames:
        for text in button_keywords:
            try:
                btn = frame.get_by_text(text, exact=True).first

                if btn.is_visible(timeout=1000):
                    btn.click(timeout=3000)
                    print(f"Cookie已关闭: {text}")
                    time.sleep(2)
                    return True
            except Exception:
                pass

    for frame in page.frames:
        try:
            clicked = frame.evaluate(
                """
                () => {
                    const keywords = [
                        'OK',
                        'USE NECESSARY COOKIES ONLY',
                        'ACCEPT',
                        'ACCEPT ALL',
                        'ALLOW ALL',
                        'AGREE',
                        'I ACCEPT'
                    ];

                    const tags = ['button', 'a', 'div', 'span'];

                    for (const tag of tags) {
                        const elements = Array.from(document.getElementsByTagName(tag));

                        for (const el of elements) {
                            const text = (el.innerText || '')
                                .replace(/\\s+/g, ' ')
                                .trim()
                                .toUpperCase();

                            if (keywords.includes(text)) {
                                el.click();
                                return text;
                            }
                        }
                    }

                    return '';
                }
                """
            )

            if clicked:
                print(f"Cookie已关闭JS: {clicked}")
                time.sleep(2)
                return True
        except Exception:
            pass

    return False


def remove_overlays(page):
    try:
        page.keyboard.press("Escape")
        time.sleep(0.2)
        page.keyboard.press("Escape")
        time.sleep(0.2)
    except Exception:
        pass

    close_selectors = [
        "button[aria-label='Close']",
        "button[title='Close']",
        "button:has-text('×')",
        "button:has-text('X')",
        "button:has-text('Close')",
    ]

    for selector in close_selectors:
        try:
            items = page.locator(selector)
            count = items.count()

            for i in range(count):
                try:
                    item = items.nth(i)

                    if item.is_visible(timeout=500):
                        item.click(timeout=1000)
                        time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass


def parse_dsv_date(date_text):
    if not date_text:
        return ""

    text = re.sub(r"\s+", " ", str(date_text)).strip()

    match = re.search(
        r"(\d{1,2})-([A-Za-z]{3,9})-(\d{4})(?:\s+(\d{1,2}:\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return text

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))
    time_part = match.group(4) or ""

    month_num = MONTH_MAP.get(month_name)

    if not month_num:
        return text

    result = f"{year}/{month_num}/{day}"

    if time_part:
        result = f"{result} {time_part}"

    return result


def extract_status_from_text(page_text):
    if not page_text:
        return "Unknown"

    text_lower = page_text.lower()

    if "no shipments found" in text_lower:
        return "No result"

    if "showing 0" in text_lower:
        return "No result"

    status_keywords = [
        "Completed",
        "Delivered",
        "In transit",
        "In Transit",
        "Booked",
        "Cargo received",
        "Port of loading",
        "Port of discharge",
        "Cancelled",
        "Canceled",
        "Exception",
    ]

    for status in status_keywords:
        if status.lower() in text_lower:
            return status

    return "Unknown"


def extract_arrival_from_search_result(page_text):
    if not page_text:
        return ""

    text = re.sub(r"\s+", " ", page_text)

    patterns = [
        r"Actual delivery\s+(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
        r"Actual delivered\s+(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
        r"Delivery\s+(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return parse_dsv_date(match.group(1))

    return ""


def extract_arrival_from_details(page_text):
    if not page_text:
        return ""

    text = re.sub(r"\s+", " ", page_text)

    patterns = [
        r"DELIVERED\s+.*?(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
        r"Delivered\s+.*?(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
        r"Actual delivery\s+(\d{1,2}-[A-Za-z]{3,9}-\d{4}\s+\d{1,2}:\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return parse_dsv_date(match.group(1))

    return ""


def find_search_input(page):
    selectors = [
        "input",
        "input[type='text']",
        "input[type='search']",
        "textarea",
    ]

    for selector in selectors:
        try:
            items = page.locator(selector)
            count = items.count()

            for i in range(count):
                try:
                    item = items.nth(i)

                    if item.is_visible(timeout=1000):
                        box = item.bounding_box()

                        if box and box["width"] > 250 and box["height"] > 20:
                            return item
                except Exception:
                    pass
        except Exception:
            pass

    return None


def human_type_tracking_number(page, search_box, tracking_number):
    search_box.click(timeout=3000)
    time.sleep(0.5)

    try:
        page.keyboard.press("Control+A")
        time.sleep(0.2)
        page.keyboard.press("Backspace")
        time.sleep(0.5)
    except Exception:
        pass

    for ch in tracking_number:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.04, 0.10))

    time.sleep(1)

    try:
        page.evaluate(
            """
            () => {
                const inputs = Array.from(document.getElementsByTagName('input'));

                for (const input of inputs) {
                    if (input.offsetParent !== null) {
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            }
            """
        )
    except Exception:
        pass

    time.sleep(1)

    try:
        page.keyboard.press("Enter")
    except Exception:
        pass


def wait_for_search_result(page, tracking_number):
    tracking_upper = tracking_number.upper()

    possible_texts = [
        tracking_upper,
        f"S{tracking_upper}",
    ]

    if tracking_upper.startswith("HKG"):
        possible_texts.append(f"SHKG{tracking_upper.replace('HKG', '')}")

    for _ in range(25):
        try:
            page_text = page.locator("body").inner_text(timeout=3000)
            page_text_upper = page_text.upper()

            if "SHOWING" in page_text_upper and "RESULT" in page_text_upper:
                return True

            for text in possible_texts:
                if text in page_text_upper:
                    return True

            if "NO SHIPMENTS FOUND" in page_text_upper:
                return True

        except Exception:
            pass

        time.sleep(1)

    return False


def search_dsv_tracking(page, tracking_number):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)

    wait_page_ready(page)
    time.sleep(3)

    accept_dsv_cookie(page)
    remove_overlays(page)
    time.sleep(1)

    search_box = find_search_input(page)

    if search_box is None:
        accept_dsv_cookie(page)
        remove_overlays(page)
        time.sleep(1)
        search_box = find_search_input(page)

    if search_box is None:
        raise Exception("未找到 DSV 搜索输入框")

    human_type_tracking_number(page, search_box, tracking_number)

    time.sleep(3)
    wait_page_ready(page)

    result_loaded = wait_for_search_result(page, tracking_number)

    if not result_loaded:
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass

        time.sleep(5)
        result_loaded = wait_for_search_result(page, tracking_number)

    if not result_loaded:
        print(f"{tracking_number} -> 查询后未检测到结果区域")


def is_dsv_detail_page(page):
    if "shipment-details-public" in str(page.url).casefold():
        return True
    try:
        text = page.locator("body").inner_text(timeout=5000).casefold()
    except Exception:
        return False
    return "shipment progress" in text and "summary" in text


def navigate_dsv_details_by_link(page):
    """Open the first result URL directly; this does not depend on displayed ID text."""
    try:
        links = page.locator("a[href*='shipment-details-public']")
        for index in range(min(links.count(), 10)):
            link = links.nth(index)
            href = str(link.get_attribute("href") or "").strip()
            if not href:
                continue
            page.goto(urljoin(str(page.url), href), wait_until="domcontentloaded", timeout=45000)
            wait_page_ready(page)
            if is_dsv_detail_page(page):
                return True
    except Exception:
        pass
    return False


def click_dsv_result_by_position(page):
    """Click the visible result card/row center when link or displayed ID changes."""
    selectors = (
        "a[href*='shipment-details-public']",
        "[data-testid*='shipment']",
        "[class*='shipment'][class*='result']",
        "[class*='result-card']",
        "article",
    )
    for selector in selectors:
        try:
            items = page.locator(selector)
            for index in range(min(items.count(), 12)):
                item = items.nth(index)
                if not item.is_visible(timeout=800):
                    continue
                box = item.bounding_box()
                if not box or box["width"] < 120 or box["height"] < 35:
                    continue
                item.scroll_into_view_if_needed(timeout=2000)
                page.mouse.click(
                    box["x"] + min(box["width"] * 0.35, 180),
                    box["y"] + box["height"] * 0.5,
                )
                time.sleep(2)
                wait_page_ready(page)
                if is_dsv_detail_page(page):
                    return True
        except Exception:
            pass
    return False


def click_dsv_shipment_result(page, tracking_number):
    # Method 1: use the actual result link. It remains valid when the visible
    # Shipment ID differs from the user's reference number.
    if navigate_dsv_details_by_link(page):
        return True

    tracking_upper = tracking_number.upper()

    possible_texts = [
        tracking_number,
        tracking_upper,
        f"S{tracking_number}",
        f"S{tracking_upper}",
    ]

    if tracking_upper.startswith("HKG"):
        possible_texts.append(f"SHKG{tracking_upper.replace('HKG', '')}")

    possible_texts = list(dict.fromkeys([x for x in possible_texts if x]))

    for text in possible_texts:
        try:
            locator = page.get_by_text(text, exact=False).first

            if locator.is_visible(timeout=2000):
                locator.scroll_into_view_if_needed(timeout=2000)
                time.sleep(0.5)

                try:
                    locator.click(timeout=5000)
                except Exception:
                    locator.click(timeout=5000, force=True)

                time.sleep(3)
                wait_page_ready(page)
                if is_dsv_detail_page(page):
                    return True
        except Exception:
            pass

    try:
        clicked = page.evaluate(
            """
            trackingNumber => {
                const upper = trackingNumber.toUpperCase();

                const candidates = [
                    trackingNumber,
                    upper,
                    'S' + trackingNumber,
                    'S' + upper
                ];

                if (upper.startsWith('HKG')) {
                    candidates.push('SHKG' + upper.replace('HKG', ''));
                }

                const tags = ['a', 'button', 'div', 'span'];

                for (const tag of tags) {
                    const elements = Array.from(document.getElementsByTagName(tag));

                    for (const el of elements) {
                        const text = (el.innerText || '').trim();

                        if (candidates.some(x => x && text.includes(x))) {
                            el.scrollIntoView({
                                behavior: 'auto',
                                block: 'center'
                            });
                            el.click();
                            return true;
                        }
                    }
                }

                return false;
            }
            """,
            tracking_number,
        )

        if clicked:
            time.sleep(3)
            wait_page_ready(page)
            if is_dsv_detail_page(page):
                return True
    except Exception:
        pass

    # Method 2: coordinate click inside the one visible result card. This is
    # deliberately independent from Shipment ID text and survives label drift.
    return click_dsv_result_by_position(page)


def save_dsv_pdf(page, tracking_number):
    try:
        Path(PDF_DIR).mkdir(parents=True, exist_ok=True)

        remove_overlays(page)
        time.sleep(1)

        current_url = page.url

        if "shipment-details-public" not in current_url and not is_dsv_detail_page(page):
            print(f"{tracking_number} -> 当前不是详情页，不保存PDF: {current_url}")
            return ""

        try:
            page.wait_for_selector("text=Shipment Progress", timeout=15000)
        except Exception:
            pass

        try:
            page.wait_for_selector("text=Summary", timeout=10000)
        except Exception:
            pass

        try:
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
        except Exception:
            pass

        try:
            page.emulate_media(media="screen")
        except Exception:
            pass

        try:
            page.set_viewport_size(
                {
                    "width": 1366,
                    "height": 900,
                }
            )
            time.sleep(1)
        except Exception:
            pass

        pdf_file = Path(PDF_DIR) / f"{tracking_number}.pdf"

        page.pdf(
            path=str(pdf_file),
            width="1366px",
            height="900px",
            print_background=True,
            margin={
                "top": "0px",
                "right": "0px",
                "bottom": "0px",
                "left": "0px",
            },
        )

        print(f"{tracking_number} -> PDF已保存: {pdf_file}")
        return str(pdf_file)

    except Exception as e:
        print(f"{tracking_number} DSV PDF保存失败: {e}")
        return ""


def warm_up_dsv(page):
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)

        wait_page_ready(page)
        time.sleep(3)

        accept_dsv_cookie(page)
        remove_overlays(page)

    except Exception as e:
        print(f"DSV预热失败，继续执行: {e}")


def query_dsv_one(page, tracking_number, save_pdf=True):
    result = make_result(tracking_number)

    if not tracking_number:
        result["status"] = "Error"
        result["error"] = "Empty tracking number"
        return result

    try:
        search_dsv_tracking(page, tracking_number)

        page_text = page.locator("body").inner_text(timeout=10000)

        blocked_words = [
            "captcha",
            "verify you are human",
            "security check",
            "access denied",
        ]

        if any(word in page_text.lower() for word in blocked_words):
            result["status"] = "Blocked"
            result["error"] = "DSV blocked or captcha"
            return result

        status = extract_status_from_text(page_text)
        result["status"] = status

        arrival_time = extract_arrival_from_search_result(page_text)

        if is_dsv_delivered(status):
            result["is_delivered"] = True

            clicked = click_dsv_shipment_result(page, tracking_number)

            if clicked:
                details_text = page.locator("body").inner_text(timeout=10000)
                detail_arrival_time = extract_arrival_from_details(details_text)

                if detail_arrival_time:
                    arrival_time = detail_arrival_time

                if save_pdf:
                    result["pdf_file"] = save_dsv_pdf(page, tracking_number)

            result["arrival_time"] = arrival_time

        print(
            f"{tracking_number} -> {result['status']} "
            f"{result['arrival_time']} {result['pdf_file']}"
        )

        return result

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)
        print(f"{tracking_number} -> DSV ERROR: {e}")
        return result
