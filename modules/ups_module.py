import re
import time
from pathlib import Path
from urllib.parse import quote


PDF_DIR = r"output\pdf\UPS"

DEFAULT_YEAR = 2026

BASE_URL = (
    "https://www.ups.com/track"
    "?tracknum={tracking_number}&loc=en_US&requester=QUIC/trackdetails"
)

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


def close_cookie_popup(page):
    button_texts = [
        "Accept All",
        "Accept",
        "I Accept",
        "Agree",
    ]

    for text in button_texts:
        try:
            btn = page.get_by_text(text, exact=False).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=1000)
                time.sleep(0.5)
                return True
        except Exception:
            pass

    return False


def close_ups_assistant(page):
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
            item = page.locator(selector).last

            if item.is_visible(timeout=500):
                item.click(timeout=1000)
                time.sleep(0.5)
        except Exception:
            pass

    try:
        page.evaluate(
            """
            () => {
                const keywords = [
                    'UPS Assistant',
                    'Welcome to UPS',
                    'virtual assistant'
                ];

                const tags = ['div', 'section', 'aside', 'iframe'];

                for (const tag of tags) {
                    const elements = Array.from(document.getElementsByTagName(tag));

                    for (const el of elements) {
                        const text = el.innerText || '';
                        const style = window.getComputedStyle(el);

                        const hasKeyword = keywords.some(k => text.includes(k));
                        const isOverlay =
                            style.position === 'fixed' ||
                            style.position === 'absolute' ||
                            style.position === 'sticky';

                        if (hasKeyword || isOverlay && text.includes('UPS')) {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                            el.style.opacity = '0';
                            el.style.pointerEvents = 'none';
                        }
                    }
                }
            }
            """
        )
    except Exception:
        pass


def cleanup_before_pdf(page):
    close_ups_assistant(page)
    time.sleep(0.8)
    close_ups_assistant(page)
    time.sleep(0.8)
    close_ups_assistant(page)


def extract_status(page_text):
    if not page_text:
        return "Unknown"

    text_lower = page_text.lower()

    status_keywords = [
        "Delivered",
        "Out for Delivery",
        "On the Way",
        "In Transit",
        "Label Created",
        "Exception",
        "Returned",
        "Canceled",
    ]

    for status in status_keywords:
        if status.lower() in text_lower:
            return status

    return "Unknown"


def extract_arrival_time(page_text):
    if not page_text:
        return ""

    text = re.sub(r"\s+", " ", page_text)

    patterns = [
        r"Delivered\s+on\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,\s*(\d{4}))?(?:\s+at\s+(\d{1,2}:\d{2}\s*(?:A\.M\.|P\.M\.|AM|PM|am|pm)?))?",
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,\s*(\d{4}))?(?:\s+at\s+(\d{1,2}:\d{2}\s*(?:A\.M\.|P\.M\.|AM|PM|am|pm)?))?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else DEFAULT_YEAR
            time_part = match.group(4) or ""

            month_num = MONTH_MAP.get(month_name.lower())

            if not month_num:
                continue

            result = f"{year}/{month_num}/{day}"

            if time_part:
                result = f"{result} {time_part.strip()}"

            return result

    return ""


def expand_show_details(page):
    try:
        page.mouse.wheel(0, 800)
        time.sleep(1)
    except Exception:
        pass

    selectors = [
        "button:has-text('Show Details')",
        "a:has-text('Show Details')",
        "div:has-text('Show Details')",
        "span:has-text('Show Details')",
        "text=Show Details",
    ]

    for selector in selectors:
        try:
            items = page.locator(selector)
            count = items.count()

            for i in range(count):
                try:
                    item = items.nth(i)

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
            () => {
                const tags = ['button', 'a', 'div', 'span'];

                for (const tag of tags) {
                    const elements = Array.from(document.getElementsByTagName(tag));

                    for (const el of elements) {
                        const text = (el.innerText || '').trim();

                        if (text.includes('Show Details')) {
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
            """
        )

        if clicked:
            time.sleep(2)
            return True
    except Exception:
        pass

    return False


def install_ups_assistant_blocker(context):
    context.add_init_script(
        """
        () => {
            function removeUpsAssistant() {
                const keywords = [
                    'UPS Assistant',
                    'Welcome to UPS',
                    'virtual assistant'
                ];

                const tags = ['div', 'section', 'aside', 'iframe'];

                for (const tag of tags) {
                    const elements = Array.from(document.getElementsByTagName(tag));

                    for (const el of elements) {
                        const text = el.innerText || '';
                        const hasKeyword = keywords.some(k => text.includes(k));

                        if (hasKeyword) {
                            el.remove();
                        }
                    }
                }
            }

            window.addEventListener('DOMContentLoaded', () => {
                removeUpsAssistant();

                if (document.body) {
                    const observer = new MutationObserver(() => {
                        removeUpsAssistant();
                    });

                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                }
            });
        }
        """
    )


def save_ups_pdf(page, tracking_number):
    try:
        Path(PDF_DIR).mkdir(parents=True, exist_ok=True)

        close_ups_assistant(page)
        time.sleep(1)

        expanded = expand_show_details(page)

        if expanded:
            print(f"{tracking_number} -> Show Details 已展开")
        else:
            print(f"{tracking_number} -> 未找到或未能点击 Show Details")

        time.sleep(1)

        cleanup_before_pdf(page)

        try:
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
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
        print(f"{tracking_number} UPS PDF保存失败: {e}")
        return ""


def warm_up_ups(page):
    try:
        page.goto(
            "https://www.ups.com/us/en/Home.page",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        wait_page_ready(page)
        time.sleep(3)

        close_cookie_popup(page)
        close_ups_assistant(page)
        time.sleep(1)
        close_ups_assistant(page)

    except Exception as e:
        print(f"UPS预热失败，继续执行: {e}")


def query_ups_one(page, tracking_number):
    result = make_result(tracking_number)

    if not tracking_number:
        result["status"] = "Error"
        result["error"] = "Empty tracking number"
        return result

    url = BASE_URL.format(tracking_number=quote(tracking_number))

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)

        wait_page_ready(page)

        close_cookie_popup(page)
        time.sleep(1)

        close_ups_assistant(page)
        time.sleep(1)
        close_ups_assistant(page)

        page_text = page.locator("body").inner_text(timeout=10000)

        blocked_words = [
            "captcha",
            "verify you are human",
            "security check",
            "access denied",
        ]

        if any(word in page_text.lower() for word in blocked_words):
            result["status"] = "Blocked"
            result["error"] = "UPS blocked or captcha"
            return result

        status = extract_status(page_text)
        result["status"] = status

        if status.lower() == "delivered":
            result["is_delivered"] = True
            result["arrival_time"] = extract_arrival_time(page_text)
            result["pdf_file"] = save_ups_pdf(page, tracking_number)

        print(
            f"{tracking_number} -> {result['status']} "
            f"{result['arrival_time']} {result['pdf_file']}"
        )

        return result

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)
        print(f"{tracking_number} -> UPS ERROR: {e}")
        return result