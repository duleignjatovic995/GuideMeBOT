import urllib.request as urllib2
import sqlite3.dbapi2 as sqlite
import bs4 as bs
import re
from urllib.parse import urljoin
from nltk.stem import porter


ignorewords = set(['the', 'of', 'to', 'and', 'a', 'in', 'is', 'it'])


class Crawler:
    # Initialize the crawler with the name of database
    def __init__(self, dbname):
        self.conn = sqlite.connect(dbname)

    def __del__(self):
        self.conn.close()

    def dbcommit(self):
        self.conn.commit()

    def get_entry_id(self, table, field, value, createnew=True):
        """
        Auxiliary function for getting an entry ID and adding it
        if it's not present.

        :param table: table in database
        :param field: field in table
        :param value: value to check
        :param createnew: (default True) -> create new row if not found
        :return: found row in database or newly created
        """
        cursor = self.conn.execute(
            "SELECT rowid FROM %s WHERE %s = '%s'" % (table, field, value)
        )
        result_set = cursor.fetchone()
        if result_set is None and createnew is True:
            cursor = self.conn.execute(
                "INSERT INTO %s (%s) VALUES ('%s')" % (table, field, value)
            )
            return cursor.lastrowid
        else:
            return result_set[0]

    def add_to_index(self, url, soup):
        """
        Indexing an individual page

        :param url: Web page url
        :param soup: BeautifulSoup object of a web page
        """
        if self.is_indexed(url):
            return
        print('Indexing:', url)

        # Get individual words
        text = self.get_text(soup)
        words = self.separate_words(text)

        # Get URL id
        urlid = self.get_entry_id('urllist', 'url', url)

        # Link each word to this url
        # todo make it more efficient
        for i in range(len(words)):
            word = words[i]
            if word in ignorewords:
                continue
            wordid = self.get_entry_id('wordlist', 'word', word)
            self.conn.execute(
                'INSERT INTO wordlocation(urlid, wordid, location) VALUES (%d, %d, %d)' % (urlid, wordid, i)
            )

    def get_text(self, soup):
        """
        Extract the text from an HTML page with no tags

        :param soup: BeautifulSoup object of a web page.
        :return: Plain text from HTML
        """
        text = soup.string
        if text is None:
            contents = soup.contents
            resulttext = ''
            for cont in contents:
                subtext = self.get_text(cont)
                resulttext += subtext + '\n'
            return resulttext
        else:
            return text.strip()

    def separate_words(self, text):
        """
        Returning list of words by separating non-whitespace character

        :param text: plain text from HTML page
        :return: list of words
        """
        splitter = re.compile('\\W*')
        stemmer = porter.PorterStemmer()
        word_list = [stemmer.stem(s) for s in splitter.split(text) if s != '']
        return word_list

    def is_indexed(self, url):
        """
        Return True if url is alredy indexed

        :param url: url name
        :return: Boolean
        """
        u = self.conn.execute(
            "SELECT rowid FROM urllist WHERE url = '%s'" % url
        ).fetchone()
        if u is not None:
            # Check if it has actually been crawled
            v = self.conn.execute(
                'SELECT * FROM wordlocation WHERE urlid = %d' % u[0]
            ).fetchone()
            if v is not None:
                return True
        return False

    def crawl(self, pages, depth=2, pattern='http'):
        """
        Starting with a list of pages do a breadth
        first search to the given depth, indexing pages as we go

        :param pages: list of pages to start crawling from
        :param depth: maximum depth for crawling pages
        :param pattern: pattern for starting url
        """
        for i in range(depth):
            new_pages = set()
            for page in pages:
                try:
                    c = urllib2.urlopen(page)
                    print('Prosao', page)
                except:
                    print('Usrao ga bajo hua', page)
                    # print(traceback.format_exc(), page)
                    continue
                soup = bs.BeautifulSoup(c.read(), 'html.parser')
                self.add_to_index(page, soup)

                links = soup('a')
                for link in links:
                    if 'href' in dict(link.attrs):
                        url = urljoin(page, link['href'])
                        if url.find("'") != -1:
                            # example: javascript:printOrder('http://www.serbianrailways.com/active/.../print.html')
                            continue
                        url = url.split('#')[0]  # remove location portion
                        if url[0:4] == pattern and not self.is_indexed(url):
                            new_pages.add(url)
                self.dbcommit()
            pages = new_pages

    def create_index_tables(self):
        """
        Toxic method to create db schema and database tables
        """
        self.conn.execute('CREATE TABLE urllist(url)')
        self.conn.execute('CREATE TABLE wordlist(word)')
        self.conn.execute('CREATE TABLE wordlocation(urlid, wordid, location)')
        self.conn.execute('CREATE TABLE link(fromid INTEGER, toid INTEGER )')
        self.conn.execute('CREATE TABLE linkwords(wordid, linkid)')
        self.conn.execute('CREATE INDEX wordidx ON wordlist(word)')
        self.conn.execute('CREATE INDEX urlidx ON urllist(url)')
        self.conn.execute('CREATE INDEX wordurlidx ON wordlocation(wordid)')
        self.conn.execute('CREATE INDEX urltoidx ON link(toid)')
        self.conn.execute('CREATE INDEX urlfromidx ON link(fromid)')
        self.dbcommit()
