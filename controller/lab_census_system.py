from urllib.parse import urljoin, urlsplit, urlunsplit

from controller import id_converter
import ddddocr
import mechanicalsoup


NYCU_BASE_URL = "https://etd.lib.nycu.edu.tw/"
NYCU_SEARCH_URL = urljoin(
    NYCU_BASE_URL, "cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
)
CAPTCHA_FORM_SELECTOR = "body > div:nth-of-type(1) > form"
CAPTCHA_BLOCK_SELECTOR = f"{CAPTCHA_FORM_SELECTOR} > div:nth-of-type(1)"


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

    def Search(self):
        print("-----------------Searching...-----------------")

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
                new = {student_name:[int(enter_year),"1"]}
            elif calculate == 1:
                self.result[1] += 1
                new = {student_name:[int(enter_year),"2"]}
            elif calculate == 2:
                self.result[2] += 1
                new = {student_name:[int(enter_year),"2_3"]}
            elif calculate == 3:
                self.result[3] += 1
                new = {student_name:[int(enter_year),"3_4"]}
            else:
                self.result[4] += 1
                new = {student_name:[int(enter_year),"4_beyond"]}

            # dict(data) = { key(學生名字):value[入學年, 畢業時間] }
            self.verbose_input.update(new)
        return self.verbose_input

    def Show(self):
        return self.result
