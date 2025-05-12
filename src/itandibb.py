from itandibb_rental import ItandiBBRentalScraper
from itandibb_sales import ItandiBBSalesScraper


class ItandiBBScraper:
    def __init__(self, credentials):
        self.credentials = credentials

    def scrape(self):
        # 賃貸スクレイパー
        ItandiBBRentalScraper(self.credentials).scrape()
        # 売買スクレイパー
        ItandiBBSalesScraper(self.credentials).scrape()
