import unittest
from urllib.parse import parse_qs

from bs4 import BeautifulSoup
import mechanicalsoup
import requests
from requests.adapters import BaseAdapter
from requests.models import Response

from controller import lab_census_system


CAPTCHA_PAGE = """
<html><body><div><form method="post" action="/verify">
<div><img src="/captcha.png"><input name="captcha"><input type="submit" name="send" value="送出"></div>
</form></div></body></html>
"""
NESTED_CAPTCHA_PAGE = """
<html><body><div><form method="post" action="/verify"><div>
<img src="/captcha.png"><label><input name="validinput" type="text"></label>
<input type="submit" name="check" value="確定">
</div></form></div></body></html>
"""
EMPTY_PAGE = "<html><body></body></html>"
SEARCH_PAGE = '<html><body><form name="main"></form></body></html>'


class CaptchaSiteAdapter(BaseAdapter):
    def __init__(self, accepted_code, captcha_page=CAPTCHA_PAGE):
        self.accepted_code = accepted_code
        self.captcha_page = captcha_page
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        response = Response()
        response.request = request
        response.url = request.url
        response.status_code = 200

        if request.path_url == "/captcha.png":
            response.headers["Content-Type"] = "image/png"
            response._content = b"captcha-image"
        elif request.method == "POST" and request.path_url == "/verify":
            fields = parse_qs(request.body)
            submitted = fields.get("captcha", fields.get("validinput"))[0]
            response.headers["Content-Type"] = "text/html"
            response._content = (
                SEARCH_PAGE if submitted == self.accepted_code else self.captcha_page
            ).encode()
        elif request.path_url.startswith("/cgi-bin/gs32/gsweb.cgi/login"):
            response.headers["Content-Type"] = "text/html"
            response._content = self.captcha_page.encode()
        else:
            response.headers["Content-Type"] = "text/html"
            response._content = EMPTY_PAGE.encode()
        return response

    def close(self):
        pass


class CaptchaTest(unittest.TestCase):
    def test_retries_with_a_new_image_until_verification_succeeds(self):
        adapter = CaptchaSiteAdapter(accepted_code="RIGHT")
        session = requests.Session()
        session.mount("https://etd.lib.nycu.edu.tw", adapter)
        browser = mechanicalsoup.StatefulBrowser(session=session)
        browser.open(
            "https://etd.lib.nycu.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
        )
        recognized_codes = iter(["WRONG", "RIGHT"])
        seen_images = []

        def classify(image):
            seen_images.append(image)
            return next(recognized_codes)

        solve_captcha = getattr(
            lab_census_system,
            "solve_captcha",
            lambda browser, classifier, max_attempts=3: None,
        )
        solve_captcha(browser, classify, max_attempts=3)

        posts = [request for request in adapter.requests if request.method == "POST"]
        self.assertEqual(2, len(posts))
        self.assertEqual([b"captcha-image", b"captcha-image"], seen_images)
        self.assertIsNone(browser.get_current_page().select_one("form img"))

    def test_solves_captcha_when_text_input_is_nested_in_a_label(self):
        adapter = CaptchaSiteAdapter(
            accepted_code="RIGHT", captcha_page=NESTED_CAPTCHA_PAGE
        )
        session = requests.Session()
        session.mount("https://ndltd.ncl.edu.tw", adapter)
        browser = mechanicalsoup.StatefulBrowser(session=session)
        browser.open(
            "https://ndltd.ncl.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
        )

        try:
            lab_census_system.solve_captcha(browser, lambda image: "RIGHT")
        except IndexError:
            self.fail("巢狀的驗證碼輸入框未被找到")

        self.assertIsNotNone(browser.get_current_page().select_one('form[name="main"]'))

    def test_raises_after_three_failed_attempts(self):
        adapter = CaptchaSiteAdapter(accepted_code="RIGHT")
        session = requests.Session()
        session.mount("https://etd.lib.nycu.edu.tw", adapter)
        browser = mechanicalsoup.StatefulBrowser(session=session)
        browser.open(
            "https://etd.lib.nycu.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dwebmge"
        )

        with self.assertRaisesRegex(RuntimeError, "驗證碼辨識失敗"):
            lab_census_system.solve_captcha(
                browser, lambda image: "WRONG", max_attempts=3
            )

        posts = [request for request in adapter.requests if request.method == "POST"]
        self.assertEqual(3, len(posts))

    def test_builds_record_url_base_from_search_result_link(self):
        page = BeautifulSoup(
            '<a href="/cgi-bin/gs32/gsweb.cgi/ccd=sdJsPF/record?r1=1&h1=0">第一筆</a>',
            "html.parser",
        )
        find_record_url_base = getattr(
            lab_census_system,
            "find_record_url_base",
            lambda page, current_url: "",
        )

        result = find_record_url_base(
            page,
            "https://etd.lib.nycu.edu.tw/cgi-bin/gs32/gsweb.cgi/ccd=sdJsPF/search",
        )

        self.assertEqual(
            "https://etd.lib.nycu.edu.tw/cgi-bin/gs32/gsweb.cgi/ccd=sdJsPF/record",
            result,
        )

    def test_opens_https_search_page_after_solving_captcha(self):
        adapter = CaptchaSiteAdapter(accepted_code="RIGHT")
        session = requests.Session()
        session.mount("https://etd.lib.nycu.edu.tw", adapter)
        browser = mechanicalsoup.StatefulBrowser(session=session)
        open_search_page = getattr(
            lab_census_system,
            "open_nycu_search_page",
            lambda browser, classifier: browser.open("https://etd.lib.nycu.edu.tw/"),
        )

        open_search_page(browser, lambda image: "RIGHT")

        self.assertIsNotNone(browser.get_current_page().select_one('form[name="main"]'))
        self.assertIsNone(browser.get_current_page().select_one("form img"))


if __name__ == "__main__":
    unittest.main()
