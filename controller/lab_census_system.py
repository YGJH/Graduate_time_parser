import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from controller import id_converter
import ddddocr
import mechanicalsoup


NYCU_BASE_URL = "https://etd.lib.nycu.edu.tw/"
NYCU_NEW_HOME_URL = "https://thesis.lib.nycu.edu.tw/home"
NYCU_SEARCH_URL = urljoin(
    NYCU_BASE_URL, "cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
)
CAPTCHA_FORM_SELECTOR = "body > div:nth-of-type(1) > form"
CAPTCHA_BLOCK_SELECTOR = f"{CAPTCHA_FORM_SELECTOR} > div:nth-of-type(1)"


def nycu_entry_year(student_id):
    digits = re.sub(r"\D", "", student_id)
    if len(digits) >= 9:
        return int(f"1{digits[1:3]}")
    return int(id_converter.NCTU(digits))


def validated_nycu_entry_year(student_id, current_roc_year=None):
    current_roc_year = current_roc_year or datetime.now().year - 1911
    entry_year = nycu_entry_year(student_id)
    return entry_year if entry_year <= current_roc_year else None


@dataclass(frozen=True)
class NycuThesis:
    url: str
    author: str
    graduation_year: int
    student_id: str
    entry_year: int | None
    year_difference: int | None


def save_nycu_debug_html(html, page_name, debug_dir="debug_html"):
    directory = Path(debug_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", page_name).strip("-")
    path = directory / f"nycu-{safe_name or 'page'}-{timestamp}.html"
    path.write_text(html, encoding="utf-8")

    wanted = {"作者", "作者(中文)", "指導教授", "畢業學年度", "學號"}
    page = BeautifulSoup(html, "html.parser")
    labels = []
    for text in page.stripped_strings:
        label = text.rstrip(":：").strip()
        if label in wanted and label not in labels:
            labels.append(label)
    return path, labels


def nycu_sorted_results_url(current_url):
    url = urlsplit(current_url)
    query = dict(parse_qsl(url.query))
    query.update(
        {
            "spc.page": "1",
            "spc.sf": "dc.date.issued",
            "spc.sd": "DESC",
            "spc.rpp": "100",
        }
    )
    return urlunsplit(
        (url.scheme, url.netloc, url.path, urlencode(query), url.fragment)
    )


def extract_nycu_result_urls(html, current_url):
    page = BeautifulSoup(html, "html.parser")
    return [
        urljoin(current_url, link["href"])
        for link in page.select(
            'li[data-test="list-object"] a.item-list-title[href]'
        )
    ]


class NycuBrowserUnavailableError(RuntimeError):
    pass


def nycu_chrome_options():
    from selenium.webdriver import ChromeOptions

    options = ChromeOptions()
    options.add_argument("--headless=new")
    return options


def create_nycu_driver(chrome_factory=None):
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException

    chrome_factory = chrome_factory or webdriver.Chrome
    try:
        return chrome_factory(options=nycu_chrome_options())
    except WebDriverException as error:
        raise NycuBrowserUnavailableError(
            "找不到或無法啟動 Chrome，請先安裝 Google Chrome。"
        ) from error


def _wait_for_nycu_css(driver, selector):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as conditions
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver, 20).until(
        conditions.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


def _report_nycu_debug(html, page_name, debug_dir):
    path, labels = save_nycu_debug_html(html, page_name, debug_dir)
    found = "、".join(labels) if labels else "找不到已知欄位標籤"
    print(f"解析失敗，HTML 已儲存至：{path}")
    print(f"HTML 中找到的欄位標籤：{found}")


def search_nycu_theses(
    driver,
    advisor_name,
    sample_count,
    wait_for_css=None,
    debug_dir="debug_html",
):
    wait_for_css = wait_for_css or _wait_for_nycu_css
    driver.get(NYCU_NEW_HOME_URL)
    search_input = wait_for_css(driver, "ds-search-form input")
    search_input.clear()
    search_input.send_keys(advisor_name)
    wait_for_css(driver, "ds-search-form button").click()

    try:
        wait_for_css(
            driver, 'li[data-test="list-object"] a.item-list-title'
        )
    except Exception:
        _report_nycu_debug(driver.page_source, "search-results", debug_dir)
        raise

    driver.get(nycu_sorted_results_url(driver.current_url))
    try:
        wait_for_css(
            driver, 'li[data-test="list-object"] a.item-list-title'
        )
    except Exception:
        _report_nycu_debug(
            driver.page_source, "sorted-search-results", debug_dir
        )
        raise

    result_urls = extract_nycu_result_urls(
        driver.page_source, driver.current_url
    )[:100]
    total_attempts = len(result_urls)
    records = []
    progress_line_open = False
    for index, url in enumerate(result_urls, start=1):
        if len(records) >= int(sample_count):
            break
        completed = int(20 * index / total_attempts) if total_attempts else 20
        bar = "█" * completed + "░" * (20 - completed)
        print(
            f"\r檢查進度：[{bar}] {index}/{total_attempts}",
            end="",
            flush=True,
        )
        progress_line_open = True
        driver.get(url)
        try:
            wait_for_css(driver, "ds-untyped-item")
            record = parse_nycu_thesis(
                driver.page_source, url, advisor_name
            )
        except Exception as error:
            _report_nycu_debug(
                driver.page_source, f"thesis-{index}", debug_dir
            )
            print(f"解析錯誤：{error}")
            continue
        if record is None:
            continue

        print()
        progress_line_open = False
        print(f"論文連結：{url}")
        entry_year = (
            record.entry_year if record.entry_year is not None else "年限未知"
        )
        year_difference = (
            record.year_difference
            if record.year_difference is not None
            else "年限未知"
        )
        print(f"作者：{record.author}")
        print(f"畢業年度：{record.graduation_year}")
        print(f"學號：{record.student_id}")
        print(f"入學年度：{entry_year}")
        print(f"畢業年度 - 入學年度：{year_difference}")
        records.append(record)
    if progress_line_open:
        print()
    return records


def _nycu_metadata_value(page, *labels):
    normalized_labels = {label.rstrip(":：").strip() for label in labels}
    label_node = page.find(
        string=lambda text: text
        and text.rstrip(":：").strip() in normalized_labels
    )
    if label_node is None:
        return None

    field = label_node.find_parent(
        [
            "ds-generic-item-page-field",
            "ds-metadata-representation-list",
            "ds-metadata-field-wrapper",
        ]
    )
    if field is None:
        field = label_node.parent
    values = [span.get_text(" ", strip=True) for span in field.find_all("span")]
    return " ".join(value for value in values if value).strip() or None


def _nycu_positional_metadata(page):
    root = page.find("ds-untyped-item")
    columns = root.find_all("div", recursive=False) if root else []
    if len(columns) < 2:
        return {}

    main_fields = columns[0].find_all(
        "ds-generic-item-page-field", recursive=False
    )
    advisor_field = columns[1].find(
        "ds-generic-item-page-field", recursive=False
    )
    author_field = columns[0].find(
        "ds-metadata-representation-list", recursive=False
    )

    def text(field):
        span = field.find("span") if field else None
        return span.get_text(" ", strip=True) if span else None

    return {
        "advisor": text(advisor_field),
        "author": text(author_field),
        "graduation_year": text(main_fields[1]) if len(main_fields) > 1 else None,
        "student_id": text(main_fields[3]) if len(main_fields) > 3 else None,
    }


def parse_nycu_thesis(html, url, advisor_name, current_roc_year=None):
    page = BeautifulSoup(html, "html.parser")
    positional = _nycu_positional_metadata(page)
    advisor = (
        _nycu_metadata_value(page, "指導教授", "指導教授：")
        or positional.get("advisor")
    )
    if advisor_name not in re.split(r"[\s、,，;/；]+", advisor or ""):
        return None

    author = (
        _nycu_metadata_value(page, "作者", "作者：", "作者(中文)")
        or positional.get("author")
    )
    graduation_year_text = (
        _nycu_metadata_value(page, "畢業學年度", "畢業學年度：")
        or positional.get("graduation_year")
    )
    student_id = (
        _nycu_metadata_value(page, "學號", "學號：")
        or positional.get("student_id")
    )
    if not all((author, graduation_year_text, student_id)):
        raise ValueError("論文頁缺少作者、畢業學年度或學號")

    graduation_year = int(re.search(r"\d+", graduation_year_text).group())
    entry_year = validated_nycu_entry_year(student_id, current_roc_year)
    return NycuThesis(
        url=url,
        author=author,
        graduation_year=graduation_year,
        student_id=student_id,
        entry_year=entry_year,
        year_difference=(
            graduation_year - entry_year if entry_year is not None else None
        ),
    )


def _legacy_field_text(page, *labels):
    normalized = {label.rstrip(":：") for label in labels}
    heading = page.find(
        "th",
        string=lambda text: text
        and text.strip().rstrip(":：") in normalized,
    )
    if heading is None or heading.find_next_sibling() is None:
        return None
    return heading.find_next_sibling().get_text(" ", strip=True)


def _legacy_advisor_names(page):
    text = _legacy_field_text(page, "指導教授") or ""
    return {
        name
        for name in re.split(r"[\s、,，;/；]+", text)
        if name
    }


def parse_legacy_thesis(html, url, advisor_name, school):
    page = BeautifulSoup(html, "html.parser")
    if advisor_name not in _legacy_advisor_names(page):
        return None

    author = _legacy_field_text(page, "作者", "作者(中文)")
    student_id = _legacy_field_text(page, "學號")
    graduation_year_text = _legacy_field_text(page, "畢業學年度")
    if not all((author, student_id, graduation_year_text)):
        raise ValueError("論文頁缺少作者、學號或畢業學年度")

    converters = {
        "1": id_converter.NCTU,
        "2": id_converter.NCU,
        "3": id_converter.NTHU,
        "4": id_converter.NYMU,
    }
    entry_year = int(converters[school](student_id))
    graduation_year = int(re.search(r"\d+", graduation_year_text).group())
    return NycuThesis(
        url=url,
        author=author,
        graduation_year=graduation_year,
        student_id=student_id,
        entry_year=entry_year,
        year_difference=graduation_year - entry_year,
    )


def collect_legacy_theses(
    browser,
    record_url_base,
    advisor_name,
    school,
    sample_count,
    department_filters,
    max_attempts=None,
):
    max_attempts = max_attempts or int(sample_count) + 100
    records = []
    seen_student_ids = set()
    duplicate_streak = 0

    for index in range(1, max_attempts + 1):
        if len(records) >= int(sample_count):
            break
        url = f"{record_url_base}?r1={index}"
        browser.open(url)
        page = browser.get_current_page()

        degree = _legacy_field_text(page, "學位類別")
        department = _legacy_field_text(page, "系所名稱")
        student_id = _legacy_field_text(page, "學號")
        if student_id is None:
            break
        if degree == "博士" or department in department_filters:
            continue

        record = parse_legacy_thesis(
            str(page), url, advisor_name, school
        )
        if record is None:
            continue
        if student_id in seen_student_ids:
            duplicate_streak += 1
            if duplicate_streak >= 3:
                break
            continue

        duplicate_streak = 0
        seen_student_ids.add(student_id)
        print(f"論文連結：{record.url}")
        print(f"作者：{record.author}")
        print(f"畢業年度：{record.graduation_year}")
        print(f"學號：{record.student_id}")
        print(f"入學年度：{record.entry_year}")
        print(f"畢業年度 - 入學年度：{record.year_difference}")
        records.append(record)
    return records


def solve_captcha(browser, classifier, max_attempts=3):
    for _ in range(max_attempts):
        page = browser.get_current_page()
        captcha_block = page.select_one(CAPTCHA_BLOCK_SELECTOR)
        if captcha_block is None or captcha_block.find("img", recursive=False) is None:
            return

        image = captcha_block.find("img", recursive=False)
        image_url = urljoin(browser.get_url(), image["src"])
        image_response = browser.session.get(image_url)
        image_response.raise_for_status()

        inputs = captcha_block.find_all("input")
        inputs[0]["value"] = classifier(image_response.content)
        form = browser.select_form(CAPTCHA_FORM_SELECTOR)
        form.choose_submit(inputs[1])
        browser.submit_selected()

        if browser.get_current_page().select_one(CAPTCHA_BLOCK_SELECTOR) is None:
            return

    raise RuntimeError(f"驗證碼辨識失敗，已重試 {max_attempts} 次")


def open_nycu_search_page(browser, classifier):
    browser.open(NYCU_SEARCH_URL)
    solve_captcha(browser, classifier, max_attempts=3)


def find_record_url_base(page, current_url):
    record_link = page.find(
        "a", href=lambda href: href is not None and "/record?" in href
    )
    if record_link is None:
        raise RuntimeError("搜尋結果中找不到論文紀錄連結")

    record_url = urlsplit(urljoin(current_url, record_link["href"]))
    return urlunsplit((record_url.scheme, record_url.netloc, record_url.path, "", ""))


class LabCensusSystem:
    def __init__(self, school, name, sample_count, filter_cnt):
        self.school = school
        self.name = name
        self.sample_count = int(sample_count)
        self.filter = []
        filter_cnt = int(filter_cnt) if filter_cnt!='' else 0
        while filter_cnt:
            self.filter.append(input('過濾系所：'))
            filter_cnt -= 1

        self.verbose_input = {}
        self.result = [0,0,0,0,0]

    def load_nycu_records(self, records):
        groups = ["1", "2", "2_3", "3_4", "4_beyond"]
        for record in records:
            if record.year_difference is None:
                continue
            result_index = min(max(record.year_difference, 0), 4)
            self.result[result_index] += 1
            chinese_name = re.search(r"[\u3400-\u9fff·]+", record.author)
            student_name = chinese_name.group() if chinese_name else record.author
            self.verbose_input[student_name] = [
                record.entry_year,
                groups[result_index],
            ]
        return self.verbose_input

    def search_legacy_records(self, browser, record_url_base):
        records = collect_legacy_theses(
            browser,
            record_url_base,
            advisor_name=self.name,
            school=self.school,
            sample_count=self.sample_count,
            department_filters=self.filter,
        )
        return self.load_nycu_records(records)

    def search_new_nycu(self, driver=None, wait_for_css=None):
        owns_driver = driver is None
        if owns_driver:
            driver = create_nycu_driver()
        try:
            records = search_nycu_theses(
                driver,
                self.name,
                self.sample_count,
                wait_for_css=wait_for_css,
            )
            return self.load_nycu_records(records)
        finally:
            if owns_driver:
                driver.quit()

    def Search(self):
        print("-----------------Searching...-----------------")

        if self.school == "1":
            return self.search_new_nycu()

        # 通過新版網站驗證碼後開啟查詢頁面
        browser = mechanicalsoup.StatefulBrowser()
        ocr = ddddocr.DdddOcr(show_ad=False)
        open_nycu_search_page(browser, ocr.classification)
        browser.select_form('form[name="main"]')

        # 填入資料並開始搜尋
        browser["qs0"] = self.name
        browser["dcf"] = "ad"
        browser["limitdb"] = int(self.school)-1
        browser.submit_selected()

        # 從搜尋結果中的實際連結取得紀錄網址，避免依賴網址字元位置
        record_url_base = find_record_url_base(
            browser.get_current_page(), browser.get_url()
        )

        # 根據畢業年遞減排序
        browser.select_form('form[name="main"]')
        browser["sortby"] = "-yr"
        # browser["SubmitChangePage"] = "1"

        if self.school == "2":
            return self.search_legacy_records(browser, record_url_base)

        # Y2：兩年畢業、Y2_3：兩年以上三年以下畢業，以此類推；previous_number用來紀錄前一筆的學號
        previous_number, i = 0, 0

        # 檢查無窮迴圈用的變數
        diff_odd, diff_even, check = (0, 0, 0)

        # 迴圈依序進入每一筆資料
        cnt = self.sample_count
        while i < cnt:
            i += 1
            now = f"{record_url_base}?r1={i}"
            browser.open(now)
            access = browser.get_current_page()

            # 避免過度過濾導致無窮迴圈

            if(i%2==1):
                diff_odd = cnt - i
            else:
                diff_even = cnt - i
            if(diff_odd == diff_even):
                check += 1
            else:
                check = 0
            if(check == 30):
                i -= 30
                break

            # 過濾博士生資料
            degree = access.body.form.div.table.tbody.tr.td.table.find("th",text="學位類別:").find_next_sibling().get_text()
            if (degree == "博士"):
                cnt += 1
                continue

            # 過濾系所
            Department = access.body.form.div.table.tbody.tr.td.table.find("th",text="系所名稱:").find_next_sibling().get_text()
            if(Department in self.filter):
                cnt += 1
                continue

            # 取得學號，並偵測第 i 筆資料是否已超過教授收過的學生量
            number = access.body.form.div.table.tbody.tr.td.table.find("th",text="學號:").find_next_sibling().get_text()
            if(previous_number == number):
                break
            else:
                previous_number = number

            # 取得畢業學年度
            grad_year = access.body.form.div.table.tbody.tr.td.table.find("th",text="畢業學年度:").find_next_sibling().get_text()

            # 過濾出學號中的入學年資訊
            if(self.school == "1"):
                enter_year = id_converter.NCTU(number)
            elif(self.school == "2"):
                enter_year = id_converter.NCU(number)
            elif(self.school == "3"):
                enter_year = id_converter.NTHU(number)
            elif(self.school == "4"):
                enter_year = id_converter.NYMU(number)

            # 畢業生名字
            try:
                student_name = access.body.form.div.table.tbody.tr.td.table.find("th",text="作者:").find_next_sibling().get_text()
            except AttributeError:
                student_name = access.body.form.div.table.tbody.tr.td.table.find("th",text="作者(中文):").find_next_sibling().get_text()
            # 畢業年 - 入學年
            calculate = int(grad_year) - int(enter_year)
            if calculate == 0:
                self.result[0] += 1
                new = {student_name:[int(enter_year),str(calculate)]}
            elif calculate == 1:
                self.result[1] += 1
                new = {student_name:[int(enter_year),str(calculate)]}
            elif calculate == 2:
                self.result[2] += 1
                new = {student_name:[int(enter_year),str(calculate)]}
            elif calculate == 3:
                self.result[3] += 1
                new = {student_name:[int(enter_year),str(calculate)]}
            else:
                self.result[4] += 1
                new = {student_name:[int(enter_year),"4_beyond"]}

            # dict(data) = { key(學生名字):value[入學年, 畢業時間] }
            self.verbose_input.update(new)
        return self.verbose_input

    def Show(self):
        return self.result
