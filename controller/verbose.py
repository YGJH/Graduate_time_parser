import re
from urllib.parse import urljoin

from controller.lab_census_system import solve_captcha
import ddddocr
import mechanicalsoup


NDLTD_SEARCH_URL = "https://ndltd.ncl.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"


def open_ndltd_search_page(browser, classifier):
    browser.open(NDLTD_SEARCH_URL)
    solve_captcha(browser, classifier, max_attempts=3)


def _field_text(page, label):
    heading = page.find("th", string=lambda text: text and text.strip() == label)
    if heading is None or heading.find_next_sibling() is None:
        return None
    return heading.find_next_sibling().get_text(" ", strip=True)


def _advisor_names(page):
    heading = page.find(
        "th", string=lambda text: text and text.strip() == "指導教授:"
    )
    if heading is None or heading.find_next_sibling() is None:
        return set()

    cell = heading.find_next_sibling()
    linked_names = {
        link.get_text(" ", strip=True) for link in cell.find_all("a")
    }
    if linked_names:
        return linked_names

    return {
        name
        for name in re.split(r"[\s、,，;/；]+", cell.get_text(" ", strip=True))
        if name
    }


def find_student_oral_defense(browser, student_name, advisor_name):
    browser.select_form('form[name="main"]')
    browser["qs0"] = student_name
    browser["dcf"] = "au"
    browser.submit_selected()

    result_url = browser.get_url()
    result_page = browser.get_current_page()
    record_urls = [
        urljoin(result_url, link["href"])
        for link in result_page.find_all("a", href=True)
        if "/record" in link["href"]
    ]

    found_student = False
    found_undated_thesis = False
    for record_url in record_urls:
        browser.open(record_url)
        record = browser.get_current_page()
        record_student = _field_text(record, "研究生:")
        if record_student != student_name:
            continue

        found_student = True
        if advisor_name not in _advisor_names(record):
            continue

        oral_defense = _field_text(record, "口試日期:")
        if oral_defense:
            browser.open(result_url)
            return "found", oral_defense
        found_undated_thesis = True

    browser.open(result_url)
    if found_undated_thesis:
        return "missing_date", None
    if found_student:
        return "advisor_mismatch", None
    return "not_found", None


class VerboseBooster:
    def __init__(self, name, sample_count, res, verbose_input):
        # data用來紀錄學生姓名、L串列紀錄各畢業時間的入學年與口試日期
        self.name = name
        self.sample_count = sample_count
        self.res = res
        self.students = verbose_input
        self.L1, self.L2, self.L3, self.L4, self.L5 = ([], [], [], [], [])
        self.not_found = []
        self.advisor_mismatch = []
        self.missing_date = []
        self.unreliable_details = []

    def search_student_details(self, browser):
        categories = {
            "1": self.L1,
            "2": self.L2,
            "2_3": self.L3,
            "3_4": self.L4,
            "4_beyond": self.L5,
        }
        for student_name, (enter_year, graduation_group) in self.students.items():
            status, oral_defense = find_student_oral_defense(
                browser, student_name, self.name
            )
            if status == "not_found":
                self.not_found.append(student_name)
                continue
            if status == "advisor_mismatch":
                self.advisor_mismatch.append(student_name)
                continue
            if status == "missing_date":
                self.missing_date.append(student_name)
                continue

            try:
                western_enter_year_number = int(enter_year) + 1911
                oral_defense_year = int(oral_defense.split("-", 1)[0])
            except (AttributeError, TypeError, ValueError):
                self.unreliable_details.append(student_name)
                continue

            study_years = oral_defense_year - western_enter_year_number
            if study_years < 0 or study_years > 5:
                self.unreliable_details.append(student_name)
                continue

            western_enter_year = f"{western_enter_year_number} 年"
            categories[graduation_group].append(
                [western_enter_year, oral_defense]
            )

    def show_unavailable_details(self):
        unavailable = (
            self.not_found
            or self.advisor_mismatch
            or self.missing_date
            or self.unreliable_details
        )
        if unavailable:
            print("部分學生的詳細資料無法確認，可能是休學、退學，或資料解析錯誤。")

    def show(self):
        print("--------------Detail searching...-------------")

        # 通過國圖網站可能出現的驗證碼後開啟查詢頁面
        browser = mechanicalsoup.StatefulBrowser()
        ocr = ddddocr.DdddOcr(show_ad=False)
        open_ndltd_search_page(browser, ocr.classification)
        self.search_student_details(browser)

        # 輸出結果
        print(f"第一年畢業的 {self.res[0]} 位學生中：")
        if(self.L1 != []):
            for time in self.L1:
                print(f"曾有人於 {time[0]} 入學，於 {time[1]} 進行口試")
        else:
            print("無資料")

        print(f"第二年畢業的 {self.res[1]} 位學生中：")
        if(self.L2 != []):
            for time in self.L2:
                print(f"曾有人於 {time[0]} 入學，於 {time[1]} 進行口試")
        else:
            print("無資料")
        print(f"第三年畢業的 {self.res[2]} 位學生中：")
        if(self.L3 != []):
            for time in self.L3:
                print(f"曾有人於 {time[0]} 入學，於 {time[1]} 進行口試")
        else:
            print("無資料")
        print(f"第四年畢業的 {self.res[3]} 位學生中：")
        if(self.L4 != []):
            for time in self.L4:
                print(f"曾有人於 {time[0]} 入學，於 {time[1]} 進行口試")
        else:
            print("無資料")
        print(f"第五年以上畢業的 {self.res[4]} 位學生中：")
        if(self.L5 != []):
            for time in self.L5:
                print(f"曾有人於 {time[0]} 入學，於 {time[1]} 進行口試")
        else:
            print("無資料")

        self.show_unavailable_details()
