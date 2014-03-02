#Embedded file name: ACEStream\Core\BitTornado\torrentlistparse.pyo
from binascii import unhexlify
try:
    True
except:
    True = 1
    False = 0

def parsetorrentlist(filename, parsed):
    new_parsed = {}
    added = {}
    removed = parsed
    f = open(filename, 'r')
    while 1:
        l = f.readline()
        if not l:
            break
        l = l.strip()
        try:
            if len(l) != 40:
                raise ValueError, 'bad line'
            h = unhexlify(l)
        except:
            print '*** WARNING *** could not parse line in torrent list: ' + l

        if parsed.has_key(h):
            del removed[h]
        else:
            added[h] = True
        new_parsed[h] = True

    f.close()
    return (new_parsed, added, removed)
