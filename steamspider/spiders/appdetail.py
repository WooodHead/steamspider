from scrapy import Spider, Request
from utils import log
from steamspider.items import AppDetailItem
import math
import re
import time
import ast


class AppDetailSpider(Spider):
    name = 'appdetail'
    allowed_domains = ['store.steampowered.com']
    handle_httpstatus_list = [301, 302]

    def __init__(self, *args, **kwargs):
        super(AppDetailSpider, self).__init__(*args, **kwargs)

        self.page_url = 'https://store.steampowered.com/search/results?search/&l=schinese&category1=10,998,21'
        self.current_pagenum = 1
        self.total_apps = 0
        self.total_pagenum = 0
        self.search_url = '{url}&page={pagenum}'
        self.media_path = 'https://media.st.dl.bscstorage.net/steam/{type}/{appid}/header_292x136.jpg'
        self.parse_switch = {'app':self.parse_app,'subs':self.parse_sub}

    def start_requests(self):
        yield Request(url=self.search_url.format(url=self.page_url, pagenum=self.current_pagenum),
                      callback=self.parse_page)

    def parse_page(self, response):
        total_pagestr = response.xpath('//div[@class="search_pagination_left"]/text()').extract_first().strip()
        self.total_apps = int(total_pagestr[total_pagestr.rfind('共') + 1:total_pagestr.rfind('个')].strip())
        self.total_pagenum = math.ceil(self.total_apps / 25)

        print('=======parse_page=====', self.total_apps, self.total_pagenum, self.current_pagenum)

        applist = response.xpath('//a[contains(@class,"search_result_row")]')

        for app_item in applist:

            detail_url = app_item.xpath('@href').extract_first() + '&l=schinese'
            app_id, app_type = self.get_id(detail_url)

            if app_id and app_type is not 'error':

                xpath_tag = app_item.xpath('@data-ds-tagids')
                tagids = ''
                if len(xpath_tag) > 0:
                    tagids = xpath_tag.extract_first().strip('[').strip(']')

                thumb_url = self.media_path.format(type=app_type,appid=app_id)

                yield Request(url=detail_url,
                              callback=self.parse_switch[app_type],
                              errback=self.parse_error,
                              cookies={'wants_mature_content': '1',
                                       "birthtime": "725817601",
                                       "lastagecheckage": "1-January-1993"},
                              meta={'app_id': app_id,
                                    'app_type': app_type,
                                    'tagids': tagids,
                                    'thumb_url': thumb_url})

        self.current_pagenum += 1
        if (self.current_pagenum < self.total_pagenum):
            yield Request(url=self.search_url.format(url=self.page_url, pagenum=self.current_pagenum),
                          callback=self.parse_page,errback=self.parse_error)

    # 解析普通的app
    def parse_app(self,response):
        if response.status in (200,):
            item = AppDetailItem()
            # 强行设置一堆默认空字符串
            item.set_defalut('')

            item['app_id'] = response.meta['app_id']
            item['app_type'] = response.meta['app_type']
            item['name'] = response.xpath('//div[@class="apphub_AppName"]/text()').extract_first()
            # 发行日期
            release = response.xpath('//div[@class="release_date"]')
            if len(release) > 0:
                item['released'] = release.xpath('.//div[@class="date"]/text()').extract_first()

            # 获取预售大节点
            xpath_purchase = response.xpath('//div[@id="game_area_purchase"]')
            # 获取不是dlc的节点
            xpath_game_wrapper = xpath_purchase.xpath('.//div[@class="game_area_purchase_game_wrapper"]')


            # 支持平台
            if len(xpath_game_wrapper.xpath('.//div[@class="game_area_purchase_platform"]')) > 0:
                xpath_platform_list = xpath_game_wrapper.xpath('.//div[@class="game_area_purchase_platform"]')[0].xpath('.//span/@class').extract()
                platforms = []
                for platform_item in xpath_platform_list:
                    platforms.append(platform_item.split(' ')[1])

                item['platforms'] = ','.join(platforms)

            # 原始价格
            xpath_original_price = xpath_game_wrapper.xpath('.//div[@class="discount_original_price"]')
            if len(xpath_original_price) > 0:
                origin_price = xpath_original_price[0].xpath('text()').extract_first().split(' ')[1]
                item['origin_price'] = str(int(origin_price) * 100)

            # 折扣 现在有可能
            xpath_discount_pct = xpath_game_wrapper.xpath('.//div[@class="discount_pct"]')
            if len(xpath_discount_pct) > 0:
                item['discount']=xpath_discount_pct[0].xpath('text()').extract_first().strip('%')

            # 折扣截至
            xpath_discount_countdown = xpath_game_wrapper.xpath('.//p[@class="game_purchase_discount_countdown"]')
            if len(xpath_discount_countdown) > 0:
                str_countdown = xpath_discount_countdown[0].xpath('text()').extract_first()

                if re.search('(\d+)月(\d+)日',str_countdown):
                    # item['discount_countdown'] = time.mktime(time.strptime(re.search('(\d+)月(\d+)日',str_countdown).group(),'%m月%d日'))
                    item['discount_countdown'] = re.search('(\d+)月(\d+)日',str_countdown).group()
                else:
                    # 这里需要获取js的时间戳可能存在风险
                    scriptstr = xpath_discount_countdown[0].xpath('../script/text()').extract_first()
                    timeArray = time.localtime(int(re.search('\d{10}',scriptstr).group()))  # 秒数
                    converTime = time.strftime("%m月%d日", timeArray)
                    item['discount_countdown'] = converTime


            # 现价
            xpath_final_price = xpath_game_wrapper.xpath('.//@data-price-final')
            if len(xpath_final_price) > 0:
                item['final_price'] = xpath_final_price[0].extract()

            # metascore评分
            xpath_metascore = response.xpath('//div[@id="game_area_metascore"]')
            if len(xpath_metascore) > 0:
                item['metascore'] = xpath_metascore[0].xpath('.//div[contains(@class,"score")]/text()').extract_first().strip()

            # tagids
            item['tagids'] = response.meta['tagids']

            # 热门标签
            xpath_popular_tags = response.xpath('//div[contains(@class,"popular_tags_ctn")]')
            if len(xpath_popular_tags) > 0:
                xpath_taglist = xpath_popular_tags[0].xpath('.//div[contains(@class,"popular_tags")]/a/text()').extract()

                popular_taglist = []
                for poular_tag_item in xpath_taglist:
                    popular_taglist.append(poular_tag_item.strip())

                item['popular_tags'] = ','.join(popular_taglist)

            # 开发者
            xpath_devlopers = response.xpath('//div[contains(@id,"developers_list")]')
            if len(xpath_devlopers) > 0:
                item['developers'] = xpath_devlopers[0].xpath('.//a/text()').extract_first()

            # 封面
            item['thumb_url'] = response.meta['thumb_url']
            # 源路径
            item['origin_url'] = response.url
            # 简介
            item['short_des'] = response.xpath('//div[@class="game_description_snippet"]/text()').extract_first().strip()

            # 详细介绍
            xpath_full_des = response.xpath('//div[@id="game_area_description"]')
            if len(xpath_full_des) > 0:
                full_html = ''.join(response.xpath('//div[@id="game_area_description"]/node()').extract()).strip()
                del_title_html = re.sub(r'<h2>关于这款游戏*</h2>','',full_html)
                item['full_des'] = del_title_html.strip()

            # 焦点图视频
            xpath_highlight_movie = response.xpath('//div[contains(@id,"highlight_movie_")]')
            if len(xpath_highlight_movie) > 0:
                # 轮播视频
                item['highlight_movie'] = response.xpath('//div[contains(@id,"highlight_movie_")]')[0].xpath(
                    '@data-mp4-source').extract_first()

            # 轮播图
            screen_path_list = response.xpath('//div[contains(@class,"highlight_screenshot")]/@id').extract()
            screen_list = []

            for sitem in screen_path_list:
                conver_url = self.screenshot_path.format(appid=response.meta['app_id']) + sitem[
                                                                                          len(
                                                                                              'thumb_screenshot_'):len(
                                                                                              sitem)]
                screen_list.append(conver_url)
            item['screenshot'] = ','.join(screen_list)

            yield item

    # 解析礼品包
    def parse_sub(self,response):
        pass

    def parse_error(self, error):
        request = error.request
        log('error_parse url:%s meta:%s' % (request.url, request.meta))

    def get_id(self, url):
        app_type = ''
        if '/sub/' in url:
            # 礼包
            pattern = re.compile('/sub/(\d+)/',re.S)
            app_type = 'subs'
        elif '/app/' in url:
            # app
            pattern = re.compile('/app/(\d+)/', re.S)
            app_type = 'app'
        elif '/bundle/' in url:
            # 捆绑包
            pattern = re.compile('/bundle/(\d+)/', re.S)
            app_type = 'bundle'
        else:
            pattern = re.compile('/(\d+)/', re.S)
            app_type = 'other'
            log('get_id other url:%s' % url)

        id = re.search(pattern, url)
        if id:
            id = id.group(1)
            return id, app_type

        log('get_id error url:%s' % url)
        return 0, 'error'
