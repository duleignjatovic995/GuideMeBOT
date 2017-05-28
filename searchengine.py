import neuralnet
import sqlite3.dbapi2 as sqlite
from nltk.stem import porter
import crawler
import gensim

DB = 'searchindex.db'
RET_SIZE = 10
default_page = 'http://www.unhcr.org/'

webpages = [
    'http://azil.rs/en/',
    'http://www.unhcr.org/non-governmental-organizations.html',
    'http://www.unhcr.org/pages/49c3646c296.html',
    'https://www.refugee.info/serbia/',
    'https://www.refugee.info/serbia/services/',
]

mynet = neuralnet.SearchNet('nn.db')
RETURN_URL_LENGTH = 10


class Searcher:
    def __init__(self, dbname):
        self.conn = sqlite.connect(dbname)

    def __del__(self):
        self.conn.close()

    def get_match_rows(self, query):
        """
        Based on the query returns list of tuples 

        This means the method will return all locations of words from query in one url,
        and all url's that contain every word from the query. Basically each urlid appears multiple times, 
        once for every combination of locations.

        rows e.g.[(urlID, word_locations...), ...]
        wordids e.g [wordid, ...]

        :param query: string containing sentence for searching
        :returns: rows -> list of tuples, wordids -> list of word id's
        """
        # Strings to build the query
        field_list = 'w0.urlid'  # URL ID from first word from query
        table_list = ''
        clause_list = ''
        wordids = []

        # Split the words by spaces
        stemmer = porter.PorterStemmer()
        words = [stemmer.stem(w) for w in query.split(' ')]  # todo izmena
        table_number = 0

        for word in words:
            # Get word ID, returns a tuple
            wordrow = self.conn.execute(
                "SELECT rowid FROM wordlist WHERE word = '%s'" % word
            ).fetchone()
            if wordrow is not None:
                wordid = wordrow[0]  # Extract word ID from tuple
                wordids.append(wordid)
                # We need to concat query if there are more tables
                if table_number > 0:
                    table_list += ','
                    clause_list += ' and '
                    clause_list += 'w%d.urlid=w%d.urlid and ' % (table_number - 1, table_number)
                field_list += ',w%d.location' % table_number  # From table wordlocation
                table_list += 'wordlocation w%d' % table_number
                # Extract wordid for every word in wordlocation table
                clause_list += 'w%d.wordid=%d' % (table_number, wordid)
                table_number += 1
        # Create the query from the separate parts
        # All url's(urlid) contain every word in the query
        full_query = 'SELECT %s FROM %s WHERE %s' % (field_list, table_list, clause_list)
        rows = []
        try:
            rows = self.conn.execute(full_query).fetchall()
        except Exception:
            return 'Error', wordids
        return rows, wordids

    def get_scored_list(self, rows, word_ids):
        """
        Scoring result (rows) with various algorithms.

        :param rows: list of tuples e.g. (urlid, w0.location, w1.location...)
        :param word_ids: list of word id's from query
        :return: dict e.g.{urlid: rank}
        """
        total_scores = dict([(row[0], 0) for row in rows])

        # Scoring functions
        weights = [
            (1.0, self.word_frequency_score(rows)),
            (2.0, self.location_score(rows)),
            (3.0, self.distance_score(rows)),
        ]

        for (weight, scores) in weights:
            for url in total_scores:
                total_scores[url] += weight * scores[url]

        return total_scores

    def get_url_name(self, id):
        """
        Method returns url name based on urlid.

        :param id: ID of url
        :return: url name
        """
        cursor = self.conn.execute(
            "SELECT url FROM urllist WHERE rowid=%d" % id
        )
        return cursor.fetchone()[0]

    def query(self, q):
        """
        Method for querying indexed web pages and printing
        best matched url's.

        :param q: query string for search
        """
        rows, word_ids = self.get_match_rows(q)  # Get list of tuples (urlid, wordlocations...)
        if rows == 'Error':
            return [(-1.0, default_page)]

        scores = self.get_scored_list(rows, word_ids)
        # Sort urls for query
        ranked_scores = sorted([(score, url) for (url, score) in scores.items()], reverse=True)
        # return ranked_scores[:10]
        # this
        return [(score, self.get_url_name(urlid)) for (score, urlid) in ranked_scores[:RET_SIZE]]
        # for (score, urlid) in ranked_scores[0:10]:
        #     print('%f\t%s' % (score, self.get_url_name(urlid)))
        # return word_ids, [r[1] for r in ranked_scores[0:10]]

    def normalize(self, scores, small_is_better=False):
        """
        Method takes a dictionary od IDs and scores and
        return a new dictionary with same IDs but with scores between 0 and 1

        :param scores: dict of ids and scores
        :param small_is_better: best type of value for scoring algorithm
        :return: dict of normalized scores
        """
        vsmall = 0.00001  # Avoid dividing by zero
        if small_is_better:
            minscore = min(scores.values())
            return dict([(u, float(minscore) / max(vsmall, l)) for (u, l) in scores.items()])
        else:
            maxscore = max(scores.values())
            if maxscore == 0:
                maxscore = vsmall
            return dict([(u, float(c) / maxscore) for (u, c) in scores.items()])

    def word_frequency_score(self, rows):
        """
        Returns score based on frequency of words in document.

        :param rows: list of tuples [(urlid, w0.location, ...), ...]
        :return: dict of scores
        """
        # Create dict {urlid: init_score}
        counts = dict([(row[0], 0) for row in rows])
        # Increment score for every occurrence of urlid in row tuple
        for row in rows:
            counts[row[0]] += 1
        return self.normalize(counts)

    def location_score(self, rows):
        """
        Returns score based on how early words from query occurred

        :param rows: list of tuples [(urlid, w0.location, ...), ...]
        :return: dict of scores
        """
        # Create dict {urlid: init_score}
        locations = dict([(row[0], 1000000) for row in rows])
        for row in rows:
            # Sum all word locations from row tuple
            loc = sum(row[1:])
            if loc < locations[row[0]]:
                locations[row[0]] = loc
        return self.normalize(locations, small_is_better=True)

    def distance_score(self, rows):
        """
        Returns score based on how close words in query appear
        to one another in document. Smallest distances are used
        for calculation.

        :param rows: list of tuples [(urlid, w0.location, ...), ...]
        :return: dict of scores
        """
        # If there's only one word everyone wins!
        if len(rows[0]) <= 2:
            return dict([(row[0], 1.0) for row in rows])

        # Initialize dictionary with large values
        min_distance = dict([(row[0], 1000000) for row in rows])

        for row in rows:
            # Calculating sum of distances between word locations in row tuple.
            dist = sum([abs(row[i] - row[i - 1]) for i in range(2, len(row))])
            if dist < min_distance[row[0]]:
                min_distance[row[0]] = dist
        return self.normalize(min_distance, small_is_better=True)

    def nn_score(self, rows, wordids):
        """
        Returns score based on user clicks.

        :param rows: list of tuples [(urlid, w0.location, ...), ...]
        :param wordids: word id's from query
        :return: dict of scores
        """
        # Get unique URL IDs as an ordered list
        urlids = [urlid for urlid in set([row[0] for row in rows])]
        nn_result = mynet.get_result(wordids, urlids)
        scores = dict([(urlids[i], nn_result[i]) for i in range(len(urlids))])
        return self.normalize(scores)

    def topic_score(self):
        pass

    def urlname_score(self):
        pass


if __name__ == '__main__':
    # krle = crawler.Crawler('bazulja.db')
    # krle.create_index_tables()
    # krle.crawl(webpages)
    # c = crawler.Crawler(DB)
    s = Searcher(DB)
    # c.create_index_tables()
    # c.crawl(webpages, pattern='https://www.refugee.info/serbia/')
    # c.crawl(webpages)
    print(s.query(''))
