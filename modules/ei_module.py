import re
import time
from pathlib import Path
from urllib.parse import quote

from modules.status_rules import matches_exact_status


CUSTOM_DELIVERED_STATUSES = ()


PDF_DIR = r"output\pdf\EI"

LANDING_URL = "https://go2expo.expeditors.com/landing"
LOGIN_URL = "https://go2expo.expeditors.com/landing"
DASHBOARD_URL = "https://go2expo.expeditors.com/dashboard"
LOGGED_IN_DETAIL_URL = "https://go2expo.expeditors.com/shipments/{tracking_number}/details"
ANONYMOUS_DETAIL_URL = "https://go2expo.expeditors.com/anonymous-track/shipments/{tracking_number}/details"

EXPO_EMAIL = ""
EXPO_PASSWORD = ""
EI_LOGIN_ENABLED = False

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
        page.wait_for_load_state("domcontentloaded", timeout=25000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass


def remove_overlays(page):
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass

    close_selectors = [
        "button[aria-label='Close']",
        "button[title='Close']",
        "button:has-text('×')",
        "button:has-text('X')",
        "button:has-text('Close')",
        "button:has-text('Got it')",
        "button:has-text('Got it!')",
    ]

    for selector in close_selectors:
        try:
            items = page.locator(selector)
            count = items.count()
            for i in range(count):
                try:
                    item = items.nth(i)
                    if item.is_visible(timeout=700):
                        item.click(timeout=1500)
                        time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass


def close_expo_welcome_popup_once(page):
    texts = ["Got it!", "Got it", "GOT IT", "Close"]
    for text in texts:
        try:
            btn = page.get_by_text(text, exact=False).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                time.sleep(1)
                return True
        except Exception:
            pass

    remove_overlays(page)
    return False


def parse_expeditors_date(date_text):
    if not date_text:
        return ""

    text = re.sub(r"\s+", " ", str(date_text)).strip()

    match = re.search(
        r"(\d{1,2})-([A-Za-z]{3,9})-(\d{4})(?:\s+\d{1,2}:\d{2}(?:\s+[A-Z]{2,4})?)?",
        text,
        re.IGNORECASE,
    )
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))
        month_num = MONTH_MAP.get(month_name)
        if month_num:
            return f"{year}/{month_num}/{day}"

    match = re.search(
        r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})(?:\s+\d{1,2}:\d{2}(?:\s+[A-Z]{2,4})?)?",
        text,
        re.IGNORECASE,
    )
    if match:
        month_name = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))
        month_num = MONTH_MAP.get(month_name)
        if month_num:
            return f"{year}/{month_num}/{day}"

    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        month_num = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year}/{month_num}/{day}"

    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year = int(match.group(1))
        month_num = int(match.group(2))
        day = int(match.group(3))
        return f"{year}/{month_num}/{day}"

    return text


def normalize_page_text(page_text):
    return re.sub(r"\s+", " ", page_text or "").strip()


def find_visible_input(page, selectors):
    for selector in selectors:
        try:
            items = page.locator(selector)
            count = items.count()
            for i in range(count):
                try:
                    item = items.nth(i)
                    if item.is_visible(timeout=1000):
                        box = item.bounding_box()
                        if box and box["width"] > 120 and box["height"] > 20:
                            return item
                except Exception:
                    pass
        except Exception:
            pass
    return None


def click_landing_sign_in(page):
    sign_in_selectors = [
        "a:has-text('SIGN IN')",
        "button:has-text('SIGN IN')",
        "text=SIGN IN",
        "a:has-text('Sign In')",
        "button:has-text('Sign In')",
        "text=Sign In",
    ]

    for selector in sign_in_selectors:
        try:
            item = page.locator(selector).first
            if item.is_visible(timeout=3000):
                item.click(timeout=5000)
                time.sleep(3)
                wait_page_ready(page)
                return True
        except Exception:
            pass

    return False


def login_expo(page):
    if not EXPO_EMAIL or not EXPO_PASSWORD:
        raise Exception("请先在 main_gui.py 中设置 EI_EMAIL 和 EI_PASSWORD。")

    page.goto(LANDING_URL, wait_until="domcontentloaded", timeout=60000)
    wait_page_ready(page)
    time.sleep(2)
    close_expo_welcome_popup_once(page)
    remove_overlays(page)

    if "dashboard" not in page.url.lower():
        click_landing_sign_in(page)

    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[id='email']",
        "input[placeholder='Email']",
        "input",
    ]
    email_box = find_visible_input(page, email_selectors)
    if email_box:
        email_box.click(timeout=3000)
        email_box.fill(EXPO_EMAIL)
        time.sleep(0.5)
        try:
            page.keyboard.press("Enter")
            time.sleep(3)
        except Exception:
            pass

    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[id='password']",
        "input[placeholder='Password']",
        "input",
    ]
    password_box = find_visible_input(page, password_selectors)
    if password_box:
        password_box.click(timeout=3000)
        password_box.fill(EXPO_PASSWORD)
        time.sleep(0.5)
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass

    wait_page_ready(page)
    time.sleep(6)
    close_expo_welcome_popup_once(page)
    remove_overlays(page)

    # 登录后热处理，进入 dashboard 并关闭可能出现的欢迎层。
    try:
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
        wait_page_ready(page)
        time.sleep(2)
        close_expo_welcome_popup_once(page)
        remove_overlays(page)
    except Exception:
        pass


def warm_up_ei(page):
    """EI 预热：登录后快速兜底清理弹窗/浮层。

    welcome 弹窗在 login_expo 中已处理，这里只做快速检查，
    避免重复调用慢速的按钮点击（is_visible 逐个等待）。
    """
    try:
        remove_overlays(page)
        try:
            btn = page.get_by_text("Got it!", exact=False).first
            if btn.is_visible(timeout=800):
                btn.click(timeout=2000)
                time.sleep(1)
        except Exception:
            pass
        remove_overlays(page)
    except Exception as e:
        print(f"EI预热失败，继续执行: {e}")


def build_detail_url(tracking_number):
    tracking_text = str(tracking_number).strip()
    if EI_LOGIN_ENABLED:
        return LOGGED_IN_DETAIL_URL.format(tracking_number=quote(tracking_text))
    return ANONYMOUS_DETAIL_URL.format(tracking_number=quote(tracking_text))


def wait_for_detail_page(page, tracking_number):
    tracking_text = str(tracking_number).strip().upper()

    for _ in range(45):
        try:
            current_url = page.url.lower()
            page_text = page.locator("body").inner_text(timeout=3000)
            page_text_upper = page_text.upper()

            loading_words = ["LOADING", "PLEASE WAIT", "SEARCHING"]
            has_loading = any(word in page_text_upper for word in loading_words)

            if "/shipments/" in current_url and "/details" in current_url and not has_loading:
                return True
            if tracking_text in page_text_upper and "STATUS:" in page_text_upper and not has_loading:
                return True
            if tracking_text in page_text_upper and "SHIPMENT:" in page_text_upper and not has_loading:
                return True
            if "NO RESULTS" in page_text_upper or "NO SHIPMENT" in page_text_upper:
                return True
        except Exception:
            pass

        time.sleep(1)

    return False


def find_dashboard_track_input(page):
    """
    只定位左侧 TRACK 卡片里的输入框，不使用右侧地图输入框。
    规则：
    1. input 必须可见；
    2. 坐标必须更接近页面左侧 TRACK 区域；
    3. 排除 placeholder 包含 Shipment Reference / city / ZIP / country / map 的输入框。
    """
    candidates = []

    try:
        inputs = page.locator("input")
        count = inputs.count()
        for i in range(count):
            try:
                item = inputs.nth(i)
                if not item.is_visible(timeout=1000):
                    continue

                box = item.bounding_box()
                if not box:
                    continue
                if box["width"] < 120 or box["height"] < 20:
                    continue

                placeholder = (item.get_attribute("placeholder") or "").strip().lower()
                aria_label = (item.get_attribute("aria-label") or "").strip().lower()
                name = (item.get_attribute("name") or "").strip().lower()
                input_id = (item.get_attribute("id") or "").strip().lower()
                attrs = " ".join([placeholder, aria_label, name, input_id])

                bad_words = [
                    "shipment reference",
                    "city",
                    "zip",
                    "country",
                    "location",
                    "map",
                ]
                if any(word in attrs for word in bad_words):
                    continue

                score = 0
                if box["x"] < 650:
                    score += 5
                if 150 < box["y"] < 520:
                    score += 3
                if 170 < box["width"] < 450:
                    score += 2

                candidates.append((score, i, item, box, attrs))
            except Exception:
                pass
    except Exception:
        pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0]
        print(f"EI TRACK输入框定位成功: index={best[1]}, box={best[3]}, attrs={best[4]}")
        return best[2]

    return None


def click_track_submit_button(page, input_box):
    try:
        box = input_box.bounding_box()
        if box:
            x = box["x"] + box["width"] + 25
            y = box["y"] + box["height"] / 2
            page.mouse.click(x, y)
            time.sleep(3)
            return True
    except Exception:
        pass

    try:
        page.keyboard.press("Enter")
        time.sleep(3)
        return True
    except Exception:
        pass

    return False


def search_from_dashboard(page, tracking_number):
    page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
    wait_page_ready(page)
    time.sleep(2)
    close_expo_welcome_popup_once(page)
    remove_overlays(page)

    try:
        track_tab = page.get_by_text("TRACK", exact=True).first
        if track_tab.is_visible(timeout=2000):
            track_tab.click(timeout=3000)
            time.sleep(1)
    except Exception:
        pass

    input_box = find_dashboard_track_input(page)
    if input_box is None:
        raise Exception("未找到 EI Dashboard 左侧 TRACK 输入框，已排除地图输入框。")

    input_box.click(timeout=3000)
    time.sleep(0.3)
    try:
        page.keyboard.press("Control+A")
        time.sleep(0.1)
        page.keyboard.press("Backspace")
    except Exception:
        pass

    input_box.fill(str(tracking_number).strip())
    time.sleep(0.5)
    click_track_submit_button(page, input_box)

    loaded = wait_for_detail_page(page, tracking_number)
    if not loaded:
        print(f"{tracking_number} -> Dashboard查询未进入详情页")

    return loaded


def open_expeditors_detail_page(page, tracking_number):
    tracking_text = str(tracking_number).strip()

    # S 开头必须从 Dashboard 左侧 TRACK 输入框查询，不能直接拼详情链接。
    if tracking_text.upper().startswith("S"):
        loaded = search_from_dashboard(page, tracking_text)
    else:
        url = build_detail_url(tracking_text)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        wait_page_ready(page)
        time.sleep(2)
        close_expo_welcome_popup_once(page)
        loaded = wait_for_detail_page(page, tracking_text)

        # 非 S 单号链接异常时，再用 Dashboard 输入框兜底一次。
        if not loaded and EI_LOGIN_ENABLED:
            print(f"{tracking_number} -> 直接链接未识别，改用 Dashboard TRACK 输入框查询")
            loaded = search_from_dashboard(page, tracking_text)

    if not loaded:
        print(f"{tracking_number} -> EI详情页未完全加载或未识别到单号")

    return loaded


# 兼容旧函数名，避免 main_gui 或其他地方仍然引用时报错。
def find_dashboard_search_input(page):
    return find_dashboard_track_input(page)


def human_input_tracking(page, input_box, tracking_number):
    if input_box is None:
        return False
    input_box.click(timeout=3000)
    input_box.fill(str(tracking_number).strip())
    time.sleep(0.5)
    return True


def click_search_after_input(page):
    try:
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def wait_for_ei_search_finished(page, tracking_number):
    return wait_for_detail_page(page, tracking_number)


def open_shipment_details_if_needed(page, tracking_number):
    return wait_for_detail_page(page, tracking_number)


def extract_status(page_text):
    if not page_text:
        return "Unknown"

    text = normalize_page_text(page_text)
    text_lower = text.lower()

    # 优先读取详情页头部的 Status: xxx。
    match = re.search(
        r"Status:\s*([A-Za-z ]+?)(?=\s+HONG\b|\s+MACAU\b|\s+Data as of\b|\s+Details\b|\s+Events\b|\s+References\b|\s+Shipment Timeline\b|$)",
        text,
        re.IGNORECASE,
    )
    if match:
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        if value:
            return value

    status_keywords = [
        "Completed",
        "Delivered",
        "On Time",
        "Arrived Final Port",
        "Arrived at Final Port",
        "Available",
        "In Transit",
        "Departed",
        "Booked",
        "Freight Received",
        "Exception",
        "Cancelled",
        "Canceled",
    ]

    for status in status_keywords:
        if status.lower() in text_lower:
            return status

    if "no results" in text_lower or "no shipment" in text_lower:
        return "No result"

    return "Unknown"


def extract_timeline_date(page_text, event_name):
    if not page_text:
        return ""

    text = normalize_page_text(page_text)
    event = re.escape(event_name)

    patterns = [
        rf"{event}\s+(\d{{1,2}}-[A-Za-z]{{3,9}}-\d{{4}}(?:\s+\d{{1,2}}:\d{{2}}(?:\s+[A-Z]{{2,4}})?)?)",
        rf"{event}\s+([A-Za-z]{{3,9}}\s+\d{{1,2}},?\s+\d{{4}}(?:\s+\d{{1,2}}:\d{{2}}(?:\s+[A-Z]{{2,4}})?)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_expeditors_date(match.group(1))

    return ""


def extract_services_completed_date(page_text):
    if not page_text:
        return ""

    # 只认 Services Completed 后面直接带日期的情况。
    completed = extract_timeline_date(page_text, "Services Completed")
    if completed:
        return completed

    text = normalize_page_text(page_text)
    patterns = [
        r"Services Completed\s*[:\-]?\s*(\d{1,2}-[A-Za-z]{3,9}-\d{4}(?:\s+\d{1,2}:\d{2}(?:\s+[A-Z]{2,4})?)?)",
        r"Services Completed\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}(?:\s+[A-Z]{2,4})?)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_expeditors_date(match.group(1))

    return ""


def is_expeditors_delivered(status, page_text):
    # 你的新规则：只看 status，必须是 Completed 才算抵达。
    # On Time / Services Completed 空字段，不再算抵达，也不会下载 PDF。
    return matches_exact_status(
        status,
        default_statuses=("Completed",),
        custom_statuses=CUSTOM_DELIVERED_STATUSES,
    )


def get_arrival_time(page_text):
    # 抵达时间仍优先取 Services Completed 的日期。
    # 如果 Status=Completed 但 Services Completed 日期没有被提取到，就返回空，结果仍可按 Completed 保存 PDF。
    return extract_services_completed_date(page_text)


def save_expeditors_pdf(page, tracking_number):
    try:
        Path(PDF_DIR).mkdir(parents=True, exist_ok=True)
        remove_overlays(page)
        time.sleep(1)

        try:
            page.set_viewport_size({"width": 1900, "height": 900})
            time.sleep(0.5)
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

        pdf_file = Path(PDF_DIR) / f"{tracking_number}.pdf"
        page.pdf(
            path=str(pdf_file),
            width="1900px",
            height="900px",
            print_background=True,
            margin={
                "top": "0px",
                "right": "0px",
                "bottom": "0px",
                "left": "0px",
            },
        )

        return str(pdf_file)

    except Exception as e:
        print(f"{tracking_number} Expeditors PDF保存失败: {e}")
        return ""


def query_expeditors_one(page, tracking_number, save_pdf=True):
    result = make_result(tracking_number)

    if not tracking_number:
        result["status"] = "Error"
        result["error"] = "Empty tracking number"
        return result

    tracking_text = str(tracking_number).strip()

    if not EI_LOGIN_ENABLED and tracking_text.upper().startswith("S"):
        result["status"] = "Skipped"
        result["error"] = "EI未登录，S开头运单号必须登录后通过 Dashboard TRACK 输入框查询"
        print(f"{tracking_number} -> EI未登录，S开头跳过")
        return result

    try:
        open_expeditors_detail_page(page, tracking_text)
        close_expo_welcome_popup_once(page)
        remove_overlays(page)

        page_text = page.locator("body").inner_text(timeout=15000)

        blocked_words = [
            "captcha",
            "verify you are human",
            "security check",
            "access denied",
        ]
        if any(word in page_text.lower() for word in blocked_words):
            result["status"] = "Blocked"
            result["error"] = "Expeditors blocked or captcha"
            return result

        status = extract_status(page_text)
        result["status"] = status

        arrival_time = get_arrival_time(page_text)

        if is_expeditors_delivered(status, page_text):
            result["is_delivered"] = True
            result["arrival_time"] = arrival_time
            if save_pdf:
                result["pdf_file"] = save_expeditors_pdf(page, tracking_text)

        print(
            f"{tracking_number} -> {result['status']} "
            f"{result['arrival_time']} {result['pdf_file']}"
        )

        return result

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)
        print(f"{tracking_number} -> Expeditors ERROR: {e}")
        return result
