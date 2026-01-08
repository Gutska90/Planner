import scrapy


class ProductItem(scrapy.Item):
    category_url = scrapy.Field()
    name = scrapy.Field()
    price = scrapy.Field()
    discount_price = scrapy.Field()
    product_url = scrapy.Field()
    raw_text = scrapy.Field()

