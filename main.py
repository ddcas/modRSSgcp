import os
import os.path as path
import subprocess
import logging

import re
import ssl
import toml
import feedparser

from google.cloud import storage

# the main function run by the GCP Function
def main(data, context):
    # config params
    config = {
        'feed': {
            'max_articles': 10,
            'author': 'AUTHOR',
            'email': 'EMAIL'
        },
        'sources': {
            'list': ['https://WEBSITE']
        },
    'system': {
            'output_file_basename': 'XML_FILENAME',
            'bucket_outputs_name': 'GCP_BUCKET'
        }
    }

    # initial template string common to all XML-based RSS feeds
    feed_initial_str="""<?xml version="1.0" encoding="{_encoding}"?>\
        <rss xmlns:dc="{_namespaces_dc}" xmlns:content="{_namespaces_content}" \
        xmlns:atom="{_namespaces_}" version="2.0"><channel><title><![CDATA[{_feed_title}]]></title>\
        <description><![CDATA[{_feed_subtitle}]]></description><link>{_feed_link}</link>\
        <image><url>https://res.cloudinary.com/lesswrong-2-0/image/upload/v1497915096/favicon_lncumn.ico</url>\
        <title>{_feed_title}</title><link>{_feed_link}</link></image><generator>{_feed_generator}</generator>\
        <lastBuildDate>{_feed_updated}</lastBuildDate><atom:link \
        href="{_feed_titledetail_base}" \
        rel="self" type="application/rss+xml"/>"""

    # template string common to all feed items
    item_str="""<item><title><![CDATA[{item_title}. By {item_author}]]></title><description>\
        <![CDATA[{item_summary}]]></description>
        <link>{item_link}</link><guid isPermaLink="{item_guidislink}">{item_id}</guid><dc:creator><![CDATA[{item_author}]]></dc:creator><pubDate>{item_published}</pubDate></item>"""

    # suffix string that ends the feed
    feed_final_str = '</channel></rss>'


    class Feed(object):
        def __init__(self, sources_list, max_number, output_file_basename, bucket_outputs_name):
            # Obtain SSL certificate
            if hasattr(ssl, '_create_unverified_context'):
                ssl._create_default_https_context = ssl._create_unverified_context
            self.max_number = max_number
            self.sources_list = sources_list
            self.output_file_basename = output_file_basename
            self.bucket_outputs_name = bucket_outputs_name
            self.list_modified_sources = []


        def modify_feed(self):
            for i in range(len(self.sources_list)):
                if ('http' in self.sources_list[i]):
                    self.list_modified_sources.append(self.add_author(self.sources_list[i], i))



        def add_author(self, url, src_idx):
            news_feed = feedparser.parse(url)       
            reg = "(?<=%s).*?(?=%s)" % ('rss&','karma') # for feeds with karma threshold
            r = re.compile(reg,re.DOTALL)
            
            rss_feed = feed_initial_str.format(
                _encoding=news_feed['encoding'].upper(),
                _namespaces_dc=news_feed['namespaces']['dc'],
                _namespaces_content=news_feed['namespaces']['content'],
                _namespaces_=news_feed['namespaces'][''],
                _feed_title=news_feed['feed']['title'],
                _feed_subtitle=news_feed['feed']['subtitle'],
                _feed_link=news_feed['feed']['link'],
                _feed_generator=news_feed['feed']['generator'],
                _feed_updated=news_feed['feed']['updated'],
                _feed_titledetail_base=r.sub('amp;', news_feed['feed']['title_detail']['base'])
                )

            client = storage.Client()
            bucket = client.get_bucket(self.bucket_outputs_name)
            for i in range(self.max_number):
                item = news_feed.entries[i]
                # add author to feed title
                authors_str = ''
                for j, auth in enumerate(item['authors']):
                    authors_str += auth['name'].replace('_', ' ')
                    if j == (len(item['authors'])-2):
                        authors_str += ' and '
                    elif j == (len(item['authors'])-1):
                        pass
                    else:
                        authors_str += ', '
                rss_feed += item_str.format(
                    item_title=item['title'],
                    item_author=authors_str,
                    item_summary=item['summary'],
                    item_link=item['link'],
                    item_guidislink=str(item['guidislink']).lower(),
                    item_id=item['id'],
                    item_published=item['published']
                )
                item['title'] += '. By {}'.format(item['author_detail']['name'])
                
            logging.info('Writing the modified feed to an XML file')
            filename = '{}-{}.xml'.format(self.output_file_basename, src_idx)
            blob = bucket.blob(filename)
            blob.upload_from_string(rss_feed + feed_final_str)

            
            return news_feed

    # Run main() code   
    # instantiate Feed object
    feed = Feed(
        config['sources']['list'],
        config['feed']['max_articles'],
        config['system']['output_file_basename'],
        config['system']['bucket_outputs_name']
        )

    # perform modifications to Feed object
    list_modified_sources = feed.modify_feed()

