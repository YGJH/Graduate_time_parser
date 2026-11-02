import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from controller import lab_census_system


THESIS_PAGE_WITH_XPATH_ONLY_FIELDS = """
<html><body><ds-untyped-item>
  <div>
    <ds-metadata-representation-list>
      <ds-metadata-field-wrapper><div><div>
        <ds-metadata-representation-loader>
          <ds-plain-text-metadata-list-element><div><span>王小明</span></div></ds-plain-text-metadata-list-element>
        </ds-metadata-representation-loader>
      </div></div></ds-metadata-field-wrapper>
    </ds-metadata-representation-list>
    <ds-generic-item-page-field><div><ds-metadata-values><span>論文題目</span></ds-metadata-values></div></ds-generic-item-page-field>
    <ds-generic-item-page-field><div><ds-metadata-values><ds-metadata-field-wrapper><div><div><span>113</span></div></div></ds-metadata-field-wrapper></ds-metadata-values></div></ds-generic-item-page-field>
    <ds-generic-item-page-field><div><ds-metadata-values><span>碩士</span></ds-metadata-values></div></ds-generic-item-page-field>
    <ds-generic-item-page-field><div><ds-metadata-values><ds-metadata-field-wrapper><div><div><span>311553053</span></div></div></ds-metadata-field-wrapper></ds-metadata-values></div></ds-generic-item-page-field>
  </div>
  <div>
    <ds-generic-item-page-field><div><ds-metadata-values><ds-metadata-field-wrapper><div><div><span>蔡淳仁</span></div></div></ds-metadata-field-wrapper></ds-metadata-values></div></ds-generic-item-page-field>
  </div>
</ds-untyped-item></body></html>
"""


THESIS_PAGE_WITH_REORDERED_FIELDS = """
<html><body><ds-untyped-item>
  <div>
    <ds-generic-item-page-field>
      <div><h5>學號</h5><div><span>311553053</span></div></div>
    </ds-generic-item-page-field>
    <ds-metadata-representation-list>
      <div><h5>作者</h5><div><span>王小明</span></div></div>
    </ds-metadata-representation-list>
    <ds-generic-item-page-field>
      <div><h5>畢業學年度</h5><div><span>113</span></div></div>
    </ds-generic-item-page-field>
  </div>
  <div>
    <ds-generic-item-page-field>
      <div><h5>指導教授</h5><div><span>蔡淳仁</span></div></div>
    </ds-generic-item-page-field>
  </div>
</ds-untyped-item></body></html>
"""


class NycuStudentIdTest(unittest.TestCase):
    def test_converts_new_nycu_student_id_to_entry_year(self):
        converter = getattr(lab_census_system, "nycu_entry_year", None)

        self.assertIsNotNone(converter, "新陽明交大學號轉換功能尚未實作")
        self.assertEqual(111, converter("311553053"))

    def test_keeps_legacy_nctu_entry_year_conversion_for_seven_digit_ids(self):
        self.assertEqual(105, lab_census_system.nycu_entry_year("0556055"))
        self.assertEqual(90, lab_census_system.nycu_entry_year("9017517"))

    def test_marks_entry_year_after_current_roc_year_as_unknown(self):
        validator = getattr(
            lab_census_system, "validated_nycu_entry_year", None
        )

        self.assertIsNotNone(validator, "入學年度上限檢查尚未實作")
        self.assertIsNone(validator("399553053", current_roc_year=115))


class NycuSearchResultParserTest(unittest.TestCase):
    def test_extracts_absolute_thesis_urls_only_from_list_objects(self):
        html = """
        <html><body>
          <li data-test="list-object">
            <a class="lead item-list-title" href="/items/first">第一篇</a>
          </li>
          <li data-test="list-object">
            <a class="lead item-list-title" href="https://thesis.lib.nycu.edu.tw/items/second">第二篇</a>
          </li>
          <a class="lead item-list-title" href="/items/not-a-result">忽略</a>
        </body></html>
        """
        extractor = getattr(lab_census_system, "extract_nycu_result_urls", None)

        self.assertIsNotNone(extractor, "陽明交大搜尋結果連結解析尚未實作")
        self.assertEqual(
            [
                "https://thesis.lib.nycu.edu.tw/items/first",
                "https://thesis.lib.nycu.edu.tw/items/second",
            ],
            extractor(html, "https://thesis.lib.nycu.edu.tw/search?query=蔡淳仁"),
        )


class FakeSearchInput:
    def __init__(self, driver):
        self.driver = driver

    def clear(self):
        self.driver.query = ""

    def send_keys(self, value):
        self.driver.query = value


class FakeSearchButton:
    def __init__(self, driver):
        self.driver = driver

    def click(self):
        self.driver.current_url = (
            "https://thesis.lib.nycu.edu.tw/search?query=蔡淳仁"
        )
        self.driver.page_source = self.driver.search_html


class FakeNycuDriver:
    def __init__(self, search_html, detail_pages):
        self.search_html = search_html
        self.detail_pages = detail_pages
        self.page_source = ""
        self.current_url = ""
        self.query = ""
        self.visited = []

    def get(self, url):
        self.visited.append(url)
        self.current_url = url
        if url.startswith("https://thesis.lib.nycu.edu.tw/search?"):
            self.page_source = self.search_html
        else:
            self.page_source = self.detail_pages.get(
                url, "<html><body></body></html>"
            )


def fake_wait_for_css(driver, selector):
    if selector == "ds-search-form input":
        return FakeSearchInput(driver)
    if selector == "ds-search-form button":
        return FakeSearchButton(driver)
    if selector == 'li[data-test="list-object"] a.item-list-title':
        return object()
    if selector == "ds-untyped-item":
        return object()
    raise AssertionError(f"unexpected selector: {selector}")


class NycuChromeConfigurationTest(unittest.TestCase):
    def test_reports_a_clear_error_when_chrome_cannot_start(self):
        from selenium.common.exceptions import WebDriverException

        creator = getattr(lab_census_system, "create_nycu_driver", None)
        error_type = getattr(
            lab_census_system, "NycuBrowserUnavailableError", None
        )

        self.assertIsNotNone(creator, "Chrome 建立流程尚未實作")
        self.assertIsNotNone(error_type, "Chrome 缺失錯誤類型尚未實作")

        def unavailable_chrome(**kwargs):
            raise WebDriverException("Unable to obtain driver for chrome")

        with self.assertRaisesRegex(error_type, "找不到或無法啟動 Chrome"):
            creator(chrome_factory=unavailable_chrome)

    def test_runs_chrome_in_headless_mode(self):
        builder = getattr(lab_census_system, "nycu_chrome_options", None)

        self.assertIsNotNone(builder, "Chrome headless 設定尚未實作")
        options = builder()

        self.assertIn("--headless=new", options.arguments)


class NycuBrowserFlowTest(unittest.TestCase):
    def test_shows_progress_and_never_checks_more_than_one_hundred_results(self):
        search_html = "".join(
            f'<li data-test="list-object"><a class="item-list-title" href="/items/{index}">item</a></li>'
            for index in range(1, 102)
        )
        wrong_page = THESIS_PAGE_WITH_REORDERED_FIELDS.replace(
            "蔡淳仁", "其他教授"
        )
        driver = FakeNycuDriver(
            search_html,
            {
                f"https://thesis.lib.nycu.edu.tw/items/{index}": wrong_page
                for index in range(1, 102)
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            records = lab_census_system.search_nycu_theses(
                driver, "蔡淳仁", 1, wait_for_css=fake_wait_for_css
            )

        checked_urls = [url for url in driver.visited if "/items/" in url]
        self.assertEqual([], records)
        self.assertEqual(100, len(checked_urls))
        self.assertNotIn(
            "https://thesis.lib.nycu.edu.tw/items/101", checked_urls
        )
        self.assertIn("100/100", output.getvalue())

    def test_prints_unknown_for_a_future_entry_year(self):
        search_html = """
        <li data-test="list-object"><a class="item-list-title" href="/items/future">future</a></li>
        """
        future_page = THESIS_PAGE_WITH_REORDERED_FIELDS.replace(
            "311553053", "399553053"
        )
        driver = FakeNycuDriver(
            search_html,
            {
                "https://thesis.lib.nycu.edu.tw/items/future": future_page,
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            records = lab_census_system.search_nycu_theses(
                driver, "蔡淳仁", 1, wait_for_css=fake_wait_for_css
            )

        self.assertEqual(1, len(records))
        self.assertIn("入學年度：年限未知", output.getvalue())
        self.assertIn("畢業年度 - 入學年度：年限未知", output.getvalue())

    def test_searches_advisor_and_continues_until_requested_matching_count(self):
        search_html = """
        <li data-test="list-object"><a class="item-list-title" href="/items/wrong">wrong</a></li>
        <li data-test="list-object"><a class="item-list-title" href="/items/right">right</a></li>
        """
        wrong = THESIS_PAGE_WITH_REORDERED_FIELDS.replace("蔡淳仁", "其他教授")
        driver = FakeNycuDriver(
            search_html,
            {
                "https://thesis.lib.nycu.edu.tw/items/wrong": wrong,
                "https://thesis.lib.nycu.edu.tw/items/right": THESIS_PAGE_WITH_REORDERED_FIELDS,
            },
        )
        search = getattr(lab_census_system, "search_nycu_theses", None)

        self.assertIsNotNone(search, "陽明交大 Selenium 搜尋流程尚未實作")
        output = io.StringIO()
        with redirect_stdout(output):
            records = search(
                driver, "蔡淳仁", 1, wait_for_css=fake_wait_for_css
            )

        self.assertNotIn("items/wrong", output.getvalue())
        self.assertIn("items/right", output.getvalue())
        self.assertEqual("蔡淳仁", driver.query)
        self.assertEqual(1, len(records))
        self.assertEqual("王小明", records[0].author)
        self.assertEqual(
            [
                "https://thesis.lib.nycu.edu.tw/home",
                "https://thesis.lib.nycu.edu.tw/search?query=%E8%94%A1%E6%B7%B3%E4%BB%81&spc.page=1&spc.sf=dc.date.issued&spc.sd=DESC&spc.rpp=100",
                "https://thesis.lib.nycu.edu.tw/items/wrong",
                "https://thesis.lib.nycu.edu.tw/items/right",
            ],
            driver.visited,
        )


class NycuStatisticsTest(unittest.TestCase):
    def test_new_nycu_system_search_uses_browser_results_for_existing_output(self):
        search_html = """
        <li data-test="list-object"><a class="item-list-title" href="/items/right">right</a></li>
        """
        driver = FakeNycuDriver(
            search_html,
            {
                "https://thesis.lib.nycu.edu.tw/items/right": THESIS_PAGE_WITH_REORDERED_FIELDS,
            },
        )
        system = lab_census_system.LabCensusSystem("1", "蔡淳仁", 10, 0)
        search = getattr(system, "search_new_nycu", None)

        self.assertIsNotNone(search, "LabCensusSystem 尚未使用陽明交大新站")
        result = search(driver=driver, wait_for_css=fake_wait_for_css)

        self.assertEqual({"王小明": [111, "2_3"]}, result)
        self.assertEqual([0, 0, 1, 0, 0], system.Show())

    def test_adds_new_site_records_to_existing_statistics_and_verbose_input(self):
        system = lab_census_system.LabCensusSystem("1", "蔡淳仁", 10, 0)
        record = lab_census_system.parse_nycu_thesis(
            THESIS_PAGE_WITH_REORDERED_FIELDS,
            "https://thesis.lib.nycu.edu.tw/items/123",
            "蔡淳仁",
        )
        loader = getattr(system, "load_nycu_records", None)

        self.assertIsNotNone(loader, "新站資料尚未接入既有統計")
        result = loader([record])

        self.assertEqual({"王小明": [111, "2_3"]}, result)
        self.assertEqual([0, 0, 1, 0, 0], system.Show())

    def test_does_not_count_a_record_with_unknown_entry_year(self):
        system = lab_census_system.LabCensusSystem("1", "蔡淳仁", 10, 0)
        record = lab_census_system.NycuThesis(
            url="https://thesis.lib.nycu.edu.tw/items/future",
            author="王小明 Wang, Xiao-Ming",
            graduation_year=115,
            student_id="399553053",
            entry_year=None,
            year_difference=None,
        )

        result = system.load_nycu_records([record])

        self.assertEqual({}, result)
        self.assertEqual([0, 0, 0, 0, 0], system.Show())

    def test_uses_chinese_author_name_for_the_existing_oral_defense_search(self):
        system = lab_census_system.LabCensusSystem("1", "蔡淳仁", 10, 0)
        record = lab_census_system.NycuThesis(
            url="https://thesis.lib.nycu.edu.tw/items/123",
            author="吳雅就 Wu, Ya-Chiu",
            graduation_year=106,
            student_id="0556055",
            entry_year=105,
            year_difference=1,
        )

        result = system.load_nycu_records([record])

        self.assertEqual({"吳雅就": [105, "2"]}, result)


class NycuDebugHtmlTest(unittest.TestCase):
    def test_saves_failed_html_and_reports_metadata_labels_found_in_it(self):
        saver = getattr(lab_census_system, "save_nycu_debug_html", None)
        html = "<html><body><h5>畢業學年度</h5><h5>學號</h5></body></html>"

        self.assertIsNotNone(saver, "失敗頁面 HTML 除錯功能尚未實作")
        with tempfile.TemporaryDirectory() as directory:
            path, labels = saver(html, "thesis", directory)

            self.assertEqual(html, Path(path).read_text(encoding="utf-8"))
            self.assertEqual(["畢業學年度", "學號"], labels)


class NycuThesisParserTest(unittest.TestCase):
    def test_finds_thesis_metadata_by_chinese_labels_when_fields_are_reordered(self):
        parser = getattr(lab_census_system, "parse_nycu_thesis", None)

        self.assertIsNotNone(parser, "陽明交大論文頁解析功能尚未實作")
        record = parser(
            THESIS_PAGE_WITH_REORDERED_FIELDS,
            "https://thesis.lib.nycu.edu.tw/items/123",
            "蔡淳仁",
        )

        self.assertEqual("王小明", record.author)
        self.assertEqual(113, record.graduation_year)
        self.assertEqual("311553053", record.student_id)
        self.assertEqual(111, record.entry_year)
        self.assertEqual(2, record.year_difference)
        self.assertEqual(
            "https://thesis.lib.nycu.edu.tw/items/123", record.url
        )

    def test_keeps_thesis_but_marks_duration_unknown_for_future_entry_year(self):
        future_page = THESIS_PAGE_WITH_REORDERED_FIELDS.replace(
            "311553053", "399553053"
        )
        try:
            record = lab_census_system.parse_nycu_thesis(
                future_page,
                "https://thesis.lib.nycu.edu.tw/items/future",
                "蔡淳仁",
                current_roc_year=115,
            )
        except TypeError:
            self.fail("論文解析尚未支援動態民國年度上限")

        self.assertEqual("王小明", record.author)
        self.assertIsNone(record.entry_year)
        self.assertIsNone(record.year_difference)

    def test_uses_supplied_xpath_structure_when_page_has_no_visible_labels(self):
        record = lab_census_system.parse_nycu_thesis(
            THESIS_PAGE_WITH_XPATH_ONLY_FIELDS,
            "https://thesis.lib.nycu.edu.tw/items/456",
            "蔡淳仁",
        )

        self.assertIsNotNone(record)
        self.assertEqual("王小明", record.author)
        self.assertEqual(113, record.graduation_year)
        self.assertEqual("311553053", record.student_id)


if __name__ == "__main__":
    unittest.main()
