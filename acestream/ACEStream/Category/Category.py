#Embedded file name: ACEStream\Category\Category.pyo
import os, re
from ACEStream.Category.init_category import getCategoryInfo
from FamilyFilter import XXXFilter
from traceback import print_exc
import sys
DEBUG = False
category_file = 'category.conf'

class Category():
    __single = None
    __size_change = 1048576

    def __init__(self, install_dir = '.'):
        if Category.__single:
            raise RuntimeError, 'Category is singleton'
        filename = os.path.join(install_dir, 'data', 'category', category_file)
        Category.__single = self
        self.utility = None
        try:
            self.category_info = getCategoryInfo(filename)
            self.category_info.sort(rankcmp)
        except:
            self.category_info = []
            if DEBUG:
                print_exc()

        self.xxx_filter = XXXFilter(install_dir)
        if DEBUG:
            print >> sys.stderr, 'category: Categories defined by user', self.getCategoryNames()

    def getInstance(*args, **kw):
        if Category.__single is None:
            Category(*args, **kw)
        return Category.__single

    getInstance = staticmethod(getInstance)

    def register(self, metadata_handler):
        self.metadata_handler = metadata_handler

    def init_from_main(self, utility):
        self.utility = utility
        self.set_family_filter(None)

    def getCategoryKeys(self):
        if self.category_info is None:
            return []
        keys = []
        keys.append('All')
        keys.append('other')
        for category in self.category_info:
            keys.append(category['name'])

        keys.sort()
        return keys

    def getCategoryNames(self):
        if self.category_info is None:
            return []
        keys = []
        for category in self.category_info:
            rank = category['rank']
            if rank == -1:
                break
            keys.append((category['name'], category['displayname']))

        return keys

    def hasActiveCategory(self, torrent):
        try:
            name = torrent['category'][0]
        except:
            print >> sys.stderr, 'Torrent: %s has no valid category' % `(torrent['content_name'])`
            return False

        for category in [{'name': 'other',
          'rank': 1}] + self.category_info:
            rank = category['rank']
            if rank == -1:
                break
            if name.lower() == category['name'].lower():
                return True

        return False

    def getCategoryRank(self, cat):
        for category in self.category_info:
            if category['name'] == cat:
                return category['rank']

    def calculateCategory(self, torrent_dict, display_name):
        torrent_category = None
        files_list = []
        try:
            for ifiles in torrent_dict['info']['files']:
                files_list.append((ifiles['path'][-1], ifiles['length'] / float(self.__size_change)))

        except KeyError:
            files_list.append((torrent_dict['info']['name'], torrent_dict['info']['length'] / float(self.__size_change)))

        try:
            tracker = torrent_dict.get('announce')
            if not tracker:
                tracker = torrent_dict.get('announce-list', [['']])[0][0]
            if self.xxx_filter.isXXXTorrent(files_list, display_name, torrent_dict.get('announce'), torrent_dict.get('comment')):
                return ['xxx']
        except:
            print >> sys.stderr, 'Category: Exception in explicit terms filter in torrent: %s' % torrent_dict
            print_exc()

        strongest_cat = 0.0
        for category in self.category_info:
            decision, strength = self.judge(category, files_list, display_name)
            if decision and strength > strongest_cat:
                torrent_category = [category['name']]
                strongest_cat = strength

        if torrent_category == None:
            torrent_category = ['other']
        return torrent_category

    def judge(self, category, files_list, display_name = ''):
        display_name = display_name.lower()
        factor = 1.0
        fileKeywords = self._getWords(display_name)
        for ikeywords in category['keywords'].keys():
            try:
                fileKeywords.index(ikeywords)
                factor *= 1 - category['keywords'][ikeywords]
            except:
                pass

        if 1 - factor > 0.5:
            if 'strength' in category:
                return (True, category['strength'])
            else:
                return (True, 1 - factor)
        matchSize = 0
        totalSize = 1e-19
        for name, length in files_list:
            totalSize += length
            if length < category['minfilesize'] or category['maxfilesize'] > 0 and length > category['maxfilesize']:
                continue
            OK = False
            for isuffix in category['suffix']:
                if name.lower().endswith(isuffix):
                    OK = True
                    break

            if OK:
                matchSize += length
                continue
            factor = 1.0
            fileKeywords = self._getWords(name.lower())
            for ikeywords in category['keywords'].keys():
                try:
                    fileKeywords.index(ikeywords)
                    factor *= 1 - category['keywords'][ikeywords]
                except:
                    pass

            if factor < 0.5:
                matchSize += length

        if matchSize / totalSize >= category['matchpercentage']:
            if 'strength' in category:
                return (True, category['strength'])
            else:
                return (True, matchSize / totalSize)
        return (False, 0)

    WORDS_REGEXP = re.compile('[a-zA-Z0-9]+')

    def _getWords(self, string):
        return self.WORDS_REGEXP.findall(string)

    def family_filter_enabled(self):
        if self.utility is None:
            return False
        else:
            state = self.utility.config.Read('family_filter')
            if state in ('1', '0'):
                return state == '1'
            self.utility.config.Write('family_filter', '1')
            self.utility.config.Flush()
            return True

    def set_family_filter(self, b = None):
        old = self.family_filter_enabled()
        if b != old or b is None:
            if b is None:
                b = old
            if self.utility is None:
                return
            if b:
                self.utility.config.Write('family_filter', '1')
            else:
                self.utility.config.Write('family_filter', '0')
            self.utility.config.Flush()
            for category in self.category_info:
                if category['name'] == 'xxx':
                    if b:
                        category['old-rank'] = category['rank']
                        category['rank'] = -1
                    elif category['rank'] == -1:
                        category['rank'] = category['old-rank']
                    break

    def get_family_filter_sql(self, _getCategoryID, table_name = ''):
        if self.family_filter_enabled():
            forbiddencats = [ cat['name'] for cat in self.category_info if cat['rank'] == -1 ]
            if table_name:
                table_name += '.'
            if forbiddencats:
                return ' and %scategory_id not in (%s)' % (table_name, ','.join([ str(_getCategoryID([cat])) for cat in forbiddencats ]))
        return ''


def rankcmp(a, b):
    if 'rank' not in a:
        return 1
    elif 'rank' not in b:
        return -1
    elif a['rank'] == -1:
        return 1
    elif b['rank'] == -1:
        return -1
    elif a['rank'] == b['rank']:
        return 0
    elif a['rank'] < b['rank']:
        return -1
    else:
        return 1
