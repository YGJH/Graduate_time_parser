import io
import unittest
from contextlib import redirect_stdout

import main


class FakeSystem:
    def __init__(self, school, name, sample_count, filter_count):
        self.result = [0, 1, 2, 3, 4]

    def Search(self):
        return {"王小明": [111, "2"]}

    def Show(self):
        return self.result


class UnavailableBrowserSystem(FakeSystem):
    def Search(self):
        raise main.lab_census_system.NycuBrowserUnavailableError(
            "找不到或無法啟動 Chrome，請先安裝 Google Chrome。"
        )


class MainFlowTest(unittest.TestCase):
    def test_prints_browser_error_and_stops_without_a_traceback(self):
        answers = iter(["1", "蔡淳仁", "10", "0"])
        output = io.StringIO()

        with redirect_stdout(output):
            main.run(
                input_fn=lambda prompt: next(answers),
                system_factory=UnavailableBrowserSystem,
            )

        self.assertEqual(
            "找不到或無法啟動 Chrome，請先安裝 Google Chrome。\n",
            output.getvalue(),
        )

    def test_prints_summary_without_running_detail_search(self):
        run = getattr(main, "run", None)
        answers = iter(["1", "蔡淳仁", "10", "0"])
        output = io.StringIO()

        self.assertIsNotNone(run, "main 流程尚未抽出為可測試函式")
        with redirect_stdout(output):
            run(input_fn=lambda prompt: next(answers), system_factory=FakeSystem)

        text = output.getvalue()
        self.assertIn("最近 10 筆碩士畢業生紀錄中", text)
        self.assertNotIn("Detail searching", text)
        self.assertNotIn("進行口試", text)


if __name__ == "__main__":
    unittest.main()
