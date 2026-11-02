import io
import unittest
from contextlib import redirect_stdout

from bs4 import BeautifulSoup
import mechanicalsoup
import requests

from controller import verbose
from tests.test_captcha import CaptchaSiteAdapter, NESTED_CAPTCHA_PAGE


SEARCH_FORM = """
<html><body><form name="main">
<input name="qs0"><input type="radio" name="dcf" value="au">
</form></body></html>
"""


class StudentSearchBrowser:
    def __init__(self, results, records):
        self.results = results
        self.records = records
        self.fields = {}
        self.url = "https://ndltd.example/search-form"
        self.page = BeautifulSoup(SEARCH_FORM, "html.parser")
        self.result_page = None
        self.queries = []

    def select_form(self, selector):
        if self.page.select_one(selector) is None:
            raise AssertionError(f"missing form: {selector}")

    def __setitem__(self, key, value):
        self.fields[key] = value

    def submit_selected(self):
        self.queries.append(dict(self.fields))
        links = "".join(
            f'<a href="/record/{record_id}">record</a>'
            for record_id in self.results.get(self.fields["qs0"], [])
        )
        self.url = "https://ndltd.example/results"
        self.page = BeautifulSoup(
            f'<html><body><form name="main"></form>{links}</body></html>',
            "html.parser",
        )
        self.result_page = self.page

    def get_current_page(self):
        return self.page

    def get_url(self):
        return self.url

    def open(self, url):
        self.url = url
        if url == "https://ndltd.example/results":
            self.page = self.result_page
            return
        record_id = url.rsplit("/", 1)[-1]
        self.page = BeautifulSoup(self.records[record_id], "html.parser")


def record_page(student, advisor, oral_defense=None):
    oral_row = (
        f"<tr><th>口試日期:</th><td>{oral_defense}</td></tr>"
        if oral_defense is not None
        else ""
    )
    return f"""
    <html><body><table>
      <tr><th>研究生:</th><td>{student}</td></tr>
      <tr><th>指導教授:</th><td>{advisor}</td></tr>
      {oral_row}
    </table></body></html>
    """


class VerboseSearchTest(unittest.TestCase):
    def test_searches_by_student_and_uses_the_record_for_the_requested_advisor(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["wrong", "right"]},
            records={
                "wrong": record_page("王小明", "其他教授", "2024-01-01"),
                "right": record_page("王小明", "蔡淳仁", "2024-06-30"),
            },
        )
        finder = getattr(verbose, "find_student_oral_defense", None)

        self.assertIsNotNone(finder, "逐位學生查詢功能尚未實作")
        status, oral_defense = finder(browser, "王小明", "蔡淳仁")

        self.assertEqual(("found", "2024-06-30"), (status, oral_defense))
        self.assertEqual({"qs0": "王小明", "dcf": "au"}, browser.queries[0])

    def test_requires_a_complete_advisor_name_match(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={
                "record": record_page("王小明", "蔡淳仁傑", "2024-06-30")
            },
        )

        result = verbose.find_student_oral_defense(browser, "王小明", "蔡淳仁")

        self.assertEqual(("advisor_mismatch", None), result)

    def test_reports_a_matching_thesis_without_an_oral_defense_date(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "蔡淳仁")},
        )

        result = verbose.find_student_oral_defense(browser, "王小明", "蔡淳仁")

        self.assertEqual(("missing_date", None), result)

    def test_treats_a_blank_oral_defense_date_as_missing(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "蔡淳仁", "")},
        )

        result = verbose.find_student_oral_defense(browser, "王小明", "蔡淳仁")

        self.assertEqual(("missing_date", None), result)

    def test_uses_a_later_dated_thesis_after_a_matching_thesis_without_a_date(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["undated", "dated"]},
            records={
                "undated": record_page("王小明", "蔡淳仁"),
                "dated": record_page("王小明", "蔡淳仁", "2024-06-30"),
            },
        )

        result = verbose.find_student_oral_defense(browser, "王小明", "蔡淳仁")

        self.assertEqual(("found", "2024-06-30"), result)

    def test_filters_a_detail_when_oral_defense_is_more_than_five_years_after_entry(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "蔡淳仁", "2022-07-21")},
        )
        booster = verbose.VerboseBooster(
            "蔡淳仁", 1, [0, 0, 0, 0, 1], {"王小明": [30, "4_beyond"]}
        )

        booster.search_student_details(browser)

        self.assertEqual([], booster.L5)
        self.assertEqual(["王小明"], getattr(booster, "unreliable_details", None))

    def test_keeps_a_detail_exactly_five_years_after_entry(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "蔡淳仁", "2024-06-30")},
        )
        booster = verbose.VerboseBooster(
            "蔡淳仁", 1, [0, 0, 0, 0, 1], {"王小明": [108, "4_beyond"]}
        )

        booster.search_student_details(browser)

        self.assertEqual([["2019 年", "2024-06-30"]], booster.L5)
        self.assertEqual([], booster.unreliable_details)

    def test_filters_a_detail_with_an_unparseable_oral_defense_year(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "蔡淳仁", "日期不明")},
        )
        booster = verbose.VerboseBooster(
            "蔡淳仁", 1, [0, 1, 0, 0, 0], {"王小明": [112, "2"]}
        )

        try:
            booster.search_student_details(browser)
        except ValueError:
            self.fail("無法解析口試年份時不應中斷整批查詢")

        self.assertEqual([], booster.L2)
        self.assertEqual(["王小明"], booster.unreliable_details)

    def test_collects_details_with_one_author_search_per_student(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["wang"], "李小華": []},
            records={"wang": record_page("王小明", "蔡淳仁", "2024-06-30")},
        )
        booster = verbose.VerboseBooster(
            "蔡淳仁",
            2,
            [0, 1, 1, 0, 0],
            {"王小明": [112, "2"], "李小華": [111, "2_3"]},
        )
        collector = getattr(booster, "search_student_details", None)

        self.assertIsNotNone(collector, "逐位收集學生詳細資料尚未實作")
        collector(browser)

        self.assertEqual(
            [
                {"qs0": "王小明", "dcf": "au"},
                {"qs0": "李小華", "dcf": "au"},
            ],
            browser.queries,
        )
        self.assertEqual([["2023 年", "2024-06-30"]], booster.L2)
        self.assertEqual(["李小華"], booster.not_found)

    def test_tracks_students_whose_theses_have_another_advisor(self):
        browser = StudentSearchBrowser(
            results={"王小明": ["record"]},
            records={"record": record_page("王小明", "其他教授", "2024-06-30")},
        )
        booster = verbose.VerboseBooster(
            "蔡淳仁", 1, [0, 1, 0, 0, 0], {"王小明": [112, "2"]}
        )

        booster.search_student_details(browser)

        self.assertEqual(["王小明"], getattr(booster, "advisor_mismatch", None))
        self.assertEqual([], booster.L2)

    def test_summarizes_unavailable_details_without_listing_students(self):
        booster = verbose.VerboseBooster("蔡淳仁", 4, [0, 0, 0, 0, 0], {})
        booster.not_found = ["王小明"]
        booster.advisor_mismatch = ["陳大文"]
        booster.missing_date = ["李小華"]
        booster.unreliable_details = ["林小美"]
        output = io.StringIO()

        with redirect_stdout(output):
            booster.show_unavailable_details()

        self.assertEqual(
            "部分學生的詳細資料無法確認，可能是休學、退學，或資料解析錯誤。\n",
            output.getvalue(),
        )

    def test_opens_ndltd_search_page_after_solving_captcha(self):
        adapter = CaptchaSiteAdapter(
            accepted_code="RIGHT", captcha_page=NESTED_CAPTCHA_PAGE
        )
        session = requests.Session()
        session.mount("https://ndltd.ncl.edu.tw", adapter)
        browser = mechanicalsoup.StatefulBrowser(session=session)
        open_search_page = getattr(
            verbose,
            "open_ndltd_search_page",
            lambda browser, classifier: browser.open(
                "https://ndltd.ncl.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
            ),
        )

        open_search_page(browser, lambda image: "RIGHT")

        self.assertIsNotNone(browser.get_current_page().select_one('form[name="main"]'))
        self.assertIsNone(browser.get_current_page().select_one("form img"))


if __name__ == "__main__":
    unittest.main()
