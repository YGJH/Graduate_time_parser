import io
import unittest
from contextlib import redirect_stdout
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from controller import lab_census_system


CENTRAL_RECORD = """
<html><body><form><div><table><tbody><tr><td><table>
  <tr><th>作者:</th><td>王小明</td></tr>
  <tr><th>指導教授:</th><td><a>張貴雲</a></td></tr>
  <tr><th>學位類別:</th><td>碩士</td></tr>
  <tr><th>系所名稱:</th><td>資訊工程學系</td></tr>
  <tr><th>學號:</th><td>111522001</td></tr>
  <tr><th>畢業學年度:</th><td>113</td></tr>
</table></td></tr></tbody></table></div></form></body></html>
"""


class FakeLegacyBrowser:
    def __init__(self, pages):
        self.pages = pages
        self.page = None
        self.visited = []

    def open(self, url):
        self.visited.append(url)
        index = int(parse_qs(urlsplit(url).query)["r1"][0])
        html = self.pages.get(index, self.pages[max(self.pages)])
        self.page = BeautifulSoup(html, "html.parser")

    def get_current_page(self):
        return self.page


class LegacyRecordParserTest(unittest.TestCase):
    def test_parses_central_record_only_for_the_exact_advisor(self):
        parser = getattr(lab_census_system, "parse_legacy_thesis", None)

        self.assertIsNotNone(parser, "舊站論文逐篇驗證尚未實作")
        record = parser(
            CENTRAL_RECORD,
            "https://etd.lib.nycu.edu.tw/record?r1=1",
            "張貴雲",
            "2",
        )

        self.assertEqual("王小明", record.author)
        self.assertEqual("111522001", record.student_id)
        self.assertEqual(111, record.entry_year)
        self.assertEqual(113, record.graduation_year)
        self.assertEqual(2, record.year_difference)


class LegacyRecordCollectionTest(unittest.TestCase):
    def test_central_system_loads_verified_legacy_records_into_statistics(self):
        browser = FakeLegacyBrowser({1: CENTRAL_RECORD})
        system = lab_census_system.LabCensusSystem(
            "2", "張貴雲", 1, 0
        )
        search = getattr(system, "search_legacy_records", None)

        self.assertIsNotNone(search, "中央查詢尚未接上逐篇驗證流程")
        result = search(
            browser, "https://etd.lib.nycu.edu.tw/record"
        )

        self.assertEqual({"王小明": [111, "2_3"]}, result)
        self.assertEqual([0, 0, 1, 0, 0], system.Show())

    def test_skips_wrong_advisor_and_duplicate_ids_before_printing_urls(self):
        wrong_advisor = CENTRAL_RECORD.replace("張貴雲", "其他教授")
        duplicate = CENTRAL_RECORD
        second_student = (
            CENTRAL_RECORD.replace("王小明", "李小華")
            .replace("111522001", "111522002")
        )
        browser = FakeLegacyBrowser(
            {
                1: wrong_advisor,
                2: CENTRAL_RECORD,
                3: duplicate,
                4: second_student,
            }
        )
        collector = getattr(
            lab_census_system, "collect_legacy_theses", None
        )
        output = io.StringIO()

        self.assertIsNotNone(collector, "舊站論文收集流程尚未實作")
        with redirect_stdout(output):
            records = collector(
                browser,
                "https://etd.lib.nycu.edu.tw/record",
                advisor_name="張貴雲",
                school="2",
                sample_count=2,
                department_filters=[],
            )

        self.assertEqual(["王小明", "李小華"], [r.author for r in records])
        text = output.getvalue()
        self.assertNotIn("r1=1", text)
        self.assertIn("r1=2", text)
        self.assertNotIn("r1=3", text)
        self.assertIn("r1=4", text)


if __name__ == "__main__":
    unittest.main()
