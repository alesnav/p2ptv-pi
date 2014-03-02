#Embedded file name: ACEStream\Core\Search\SearchManager.pyo
import re
import sys
DEBUG = False
re_keywordsplit = re.compile('[\\W_]', re.UNICODE)

def split_into_keywords(string):
    return [ keyword for keyword in re_keywordsplit.split(string.lower()) if len(keyword) > 0 ]


class SearchManager:

    def __init__(self, dbhandler):
        self.dbhandler = dbhandler

    def search(self, kws, maxhits = None):
        if DEBUG:
            print >> sys.stderr, 'SearchManager: search', kws
        hits = self.dbhandler.searchNames(kws)
        if maxhits is None:
            return hits
        else:
            return hits[:maxhits]

    def searchLibrary(self):
        return self.dbhandler.getTorrents(sort='name', library=True)

    def searchChannels(self, query):
        data = self.dbhandler.searchChannels(query)
        return data
