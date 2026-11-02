import unittest

import mechanicalsoup
import requests

from controller import verbose
from tests.test_captcha import CaptchaSiteAdapter, NESTED_CAPTCHA_PAGE


class VerboseSearchTest(unittest.TestCase):
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
