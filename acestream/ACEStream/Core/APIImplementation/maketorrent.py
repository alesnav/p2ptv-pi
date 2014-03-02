#Embedded file name: ACEStream\Core\APIImplementation\maketorrent.pyo
import sys
import os
from hashlib import md5
import zlib
from ACEStream.Core.Utilities.TSCrypto import sha
from copy import copy
from time import time
from types import LongType
from ACEStream.Core.BitTornado.bencode import bencode
from ACEStream.Core.BitTornado.BT1.btformats import check_info
from ACEStream.Core.Merkle.merkle import MerkleTree
from ACEStream.Core.Utilities.unicode import str2unicode, bin2unicode
from ACEStream.Core.APIImplementation.miscutils import parse_playtime_to_secs, offset2piece
from ACEStream.Core.osutils import fix_filebasename
from ACEStream.Core.defaults import tdefdictdefaults
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.odict import odict
ignore = []
DEBUG = False

def make_torrent_file(input, userabortflag = None, userprogresscallback = lambda x: None):
    info, piece_length = makeinfo(input, userabortflag, userprogresscallback)
    if userabortflag is not None and userabortflag.isSet():
        return (None, None)
    if info is None:
        return (None, None)
    check_info(info)
    metainfo = {'info': info,
     'encoding': input['encoding']}
    if input['nodes'] is None and input['announce'] is None:
        raise ValueError('No tracker set')
    for key in ['announce',
     'announce-list',
     'nodes',
     'comment',
     'created by',
     'httpseeds',
     'url-list',
     'authorized-peers']:
        if input.has_key(key) and input[key] is not None and len(input[key]) > 0:
            metainfo[key] = input[key]
            if key == 'comment':
                metainfo['comment.utf-8'] = uniconvert(input['comment'], 'utf-8')

    if input['torrentsigkeypairfilename'] is not None:
        from ACEStream.Core.Overlay.permid import create_torrent_signature
        create_torrent_signature(metainfo, input['torrentsigkeypairfilename'])
    if 'url-compat' in input:
        metainfo['info']['url-compat'] = input['url-compat']
    if 'x-ts-properties' in input:
        metainfo['x-ts-properties'] = input['x-ts-properties']
    if 'ogg-headers' in input:
        metainfo['ogg-headers'] = input['ogg-headers']
    infohash = sha(bencode(info)).digest()
    return (infohash, metainfo)


def uniconvertl(l, e):
    r = []
    try:
        for s in l:
            r.append(uniconvert(s, e))

    except UnicodeError:
        raise UnicodeError('bad filename: ' + os.path.join(l))

    return r


def uniconvert(s, enc):
    if not isinstance(s, unicode):
        try:
            s = bin2unicode(s, enc)
        except UnicodeError:
            raise UnicodeError('bad filename: ' + s)

    return s.encode(enc)


def makeinfo(input, userabortflag, userprogresscallback):
    encoding = input['encoding']
    pieces = []
    sh = sha()
    done = 0L
    fs = []
    totalsize = 0L
    totalhashed = 0L
    subs = []
    for file in input['files']:
        inpath = file['inpath']
        outpath = file['outpath']
        if DEBUG:
            print >> sys.stderr, 'makeinfo: inpath', inpath, 'outpath', outpath
        if os.path.isdir(inpath):
            dirsubs = subfiles(inpath)
            subs.extend(dirsubs)
        elif outpath is None:
            subs.append(([os.path.basename(inpath)], inpath))
        else:
            subs.append((filename2pathlist(outpath, skipfirst=True), inpath))

    subs.sort()
    newsubs = []
    for p, f in subs:
        if 'live' in input:
            size = input['files'][0]['length']
        else:
            size = os.path.getsize(f)
        totalsize += size
        newsubs.append((p, f, size))

    subs = newsubs
    if input['piece length'] == 0:
        if input['createmerkletorrent']:
            piece_len_exp = 18
        elif totalsize > 8589934592L:
            piece_len_exp = 21
        elif totalsize > 2147483648L:
            piece_len_exp = 20
        elif totalsize > 536870912:
            piece_len_exp = 19
        elif totalsize > 67108864:
            piece_len_exp = 18
        elif totalsize > 16777216:
            piece_len_exp = 17
        elif totalsize > 4194304:
            piece_len_exp = 16
        else:
            piece_len_exp = 15
        piece_length = 2 ** piece_len_exp
    else:
        piece_length = input['piece length']
    if 'live' not in input:
        for p, f, size in subs:
            pos = 0L
            h = open(f, 'rb')
            if input['makehash_md5']:
                hash_md5 = md5.new()
            if input['makehash_sha1']:
                hash_sha1 = sha()
            if input['makehash_crc32']:
                hash_crc32 = zlib.crc32('')
            while pos < size:
                a = min(size - pos, piece_length - done)
                if userabortflag is not None and userabortflag.isSet():
                    return (None, None)
                readpiece = h.read(a)
                if userabortflag is not None and userabortflag.isSet():
                    return (None, None)
                sh.update(readpiece)
                if input['makehash_md5']:
                    hash_md5.update(readpiece)
                if input['makehash_crc32']:
                    hash_crc32 = zlib.crc32(readpiece, hash_crc32)
                if input['makehash_sha1']:
                    hash_sha1.update(readpiece)
                done += a
                pos += a
                totalhashed += a
                if done == piece_length:
                    pieces.append(sh.digest())
                    done = 0
                    sh = sha()
                if userprogresscallback is not None:
                    userprogresscallback(float(totalhashed) / float(totalsize))

            newdict = odict()
            newdict['length'] = num2num(size)
            newdict['path'] = uniconvertl(p, encoding)
            newdict['path.utf-8'] = uniconvertl(p, 'utf-8')
            for file in input['files']:
                if file['inpath'] == f:
                    if file['playtime'] is not None:
                        newdict['playtime'] = file['playtime']
                    break

            if input['makehash_md5']:
                newdict['md5sum'] = hash_md5.hexdigest()
            if input['makehash_crc32']:
                newdict['crc32'] = '%08X' % hash_crc32
            if input['makehash_sha1']:
                newdict['sha1'] = hash_sha1.digest()
            fs.append(newdict)
            h.close()

        if done > 0:
            pieces.append(sh.digest())
    if len(subs) == 1:
        flkey = 'length'
        flval = num2num(totalsize)
        name = subs[0][0][0]
    else:
        flkey = 'files'
        flval = fs
        outpath = input['files'][0]['outpath']
        l = filename2pathlist(outpath)
        name = l[0]
    infodict = odict()
    infodict['piece length'] = num2num(piece_length)
    infodict[flkey] = flval
    infodict['name'] = uniconvert(name, encoding)
    infodict['name.utf-8'] = uniconvert(name, 'utf-8')
    if 'live' not in input:
        if input['createmerkletorrent']:
            merkletree = MerkleTree(piece_length, totalsize, None, pieces)
            root_hash = merkletree.get_root_hash()
            infodict['root hash'] = root_hash
        else:
            infodict['pieces'] = ''.join(pieces)
    else:
        infodict['live'] = input['live']
    if input.has_key('provider'):
        infodict['provider'] = input['provider']
    if input.has_key('content_id'):
        infodict['content_id'] = input['content_id']
    if input.has_key('premium'):
        infodict['premium'] = input['premium']
    if input.has_key('license'):
        infodict['license'] = input['license']
    if input.has_key('tns'):
        infodict['tns'] = input['tns']
    if 'cs_keys' in input:
        infodict['cs_keys'] = input['cs_keys']
    if 'private' in input:
        infodict['private'] = input['private']
    if 'sharing' in input:
        infodict['sharing'] = input['sharing']
    if 'ns-metadata' in input:
        infodict['ns-metadata'] = input['ns-metadata']
    if len(subs) == 1:
        for file in input['files']:
            if file['inpath'] == f:
                if file['playtime'] is not None:
                    infodict['playtime'] = file['playtime']

    infodict.sort()
    return (infodict, piece_length)


def subfiles(d):
    r = []
    stack = [([], d)]
    while stack:
        p, n = stack.pop()
        if os.path.isdir(n):
            for s in os.listdir(n):
                if s not in ignore and s[:1] != '.':
                    stack.append((copy(p) + [s], os.path.join(n, s)))

        else:
            r.append((p, n))

    return r


def filename2pathlist(path, skipfirst = False):
    h = path
    l = []
    while True:
        h, t = os.path.split(h)
        if h == '' and t == '':
            break
        if h == '' and skipfirst:
            continue
        if t != '':
            l.append(t)

    l.reverse()
    return l


def pathlist2filename(pathlist):
    fullpath = ''
    for elem in pathlist:
        fullpath = os.path.join(fullpath, elem)

    return fullpath


def pathlist2savefilename(pathlist, encoding):
    fullpath = u''
    for elem in pathlist:
        u = bin2unicode(elem, encoding)
        b = fix_filebasename(u)
        fullpath = os.path.join(fullpath, b)

    return fullpath


def torrentfilerec2savefilename(filerec, length = None):
    if length is None:
        length = len(filerec['path'])
    if 'path.utf-8' in filerec:
        key = 'path.utf-8'
        encoding = 'utf-8'
    else:
        key = 'path'
        encoding = 'utf-8'
    return pathlist2savefilename(filerec[key][:length], encoding)


def savefilenames2finaldest(fn1, fn2):
    j = os.path.join(fn1, fn2)
    if sys.platform == 'win32':
        j = j[:259]
    return j


def num2num(num):
    if type(num) == LongType and num < sys.maxint:
        return int(num)
    else:
        return num


def get_torrentfilerec_from_metainfo(filename, metainfo):
    info = metainfo['info']
    if filename is None:
        return info
    if filename is not None and 'files' in info:
        for i in range(len(info['files'])):
            x = info['files'][i]
            intorrentpath = pathlist2filename(x['path'])
            if intorrentpath == filename:
                return x

        raise ValueError('File not found in torrent')
    else:
        raise ValueError('File not found in single-file torrent')


def get_bitrate_from_metainfo(file, metainfo):
    info = metainfo['info']
    if file is None:
        bitrate = None
        try:
            playtime = None
            if info.has_key('playtime'):
                playtime = parse_playtime_to_secs(info['playtime'])
            elif 'playtime' in metainfo:
                playtime = parse_playtime_to_secs(metainfo['playtime'])
            elif 'azureus_properties' in metainfo:
                azprop = metainfo['azureus_properties']
                if 'Content' in azprop:
                    content = metainfo['azureus_properties']['Content']
                    if 'Speed Bps' in content:
                        bitrate = float(content['Speed Bps'])
            if playtime is not None:
                bitrate = info['length'] / playtime
                if DEBUG:
                    print >> sys.stderr, 'TorrentDef: get_bitrate: Found bitrate', bitrate
        except:
            log_exc()

        return bitrate
    if file is not None and 'files' in info:
        for i in range(len(info['files'])):
            x = info['files'][i]
            intorrentpath = ''
            for elem in x['path']:
                intorrentpath = os.path.join(intorrentpath, elem)

            bitrate = None
            try:
                playtime = None
                if x.has_key('playtime'):
                    playtime = parse_playtime_to_secs(x['playtime'])
                elif 'playtime' in metainfo:
                    playtime = parse_playtime_to_secs(metainfo['playtime'])
                elif 'azureus_properties' in metainfo:
                    azprop = metainfo['azureus_properties']
                    if 'Content' in azprop:
                        content = metainfo['azureus_properties']['Content']
                        if 'Speed Bps' in content:
                            bitrate = float(content['Speed Bps'])
                if playtime is not None:
                    bitrate = x['length'] / playtime
            except:
                log_exc()

            if intorrentpath == file:
                return bitrate

        raise ValueError('File not found in torrent')
    else:
        raise ValueError('File not found in single-file torrent: ' + file)


def get_length_filepieceranges_from_metainfo(metainfo, selectedfiles):
    if 'files' not in metainfo['info']:
        return (metainfo['info']['length'], None)
    else:
        files = metainfo['info']['files']
        piecesize = metainfo['info']['piece length']
        total = 0L
        filepieceranges = []
        for i in xrange(len(files)):
            path = files[i]['path']
            length = files[i]['length']
            filename = pathlist2filename(path)
            if length > 0 and (not selectedfiles or selectedfiles and filename in selectedfiles):
                range = (offset2piece(total, piecesize), offset2piece(total + length, piecesize), filename)
                filepieceranges.append(range)
                total += length

        return (total, filepieceranges)


def copy_metainfo_to_input(metainfo, input):
    keys = tdefdictdefaults.keys()
    keys.append('initial peers')
    keys.append('authorized-peers')
    for key in keys:
        if key in metainfo:
            input[key] = metainfo[key]

    infokeys = ['name',
     'piece length',
     'live',
     'url-compat',
     'provider',
     'access',
     'private',
     'content_id',
     'premium',
     'sharing',
     'license',
     'tns']
    for key in infokeys:
        if key in metainfo['info']:
            input[key] = metainfo['info'][key]

    if 'length' in metainfo['info']:
        outpath = metainfo['info']['name']
        if 'playtime' in metainfo['info']:
            playtime = metainfo['info']['playtime']
        else:
            playtime = None
        length = metainfo['info']['length']
        d = {'inpath': outpath,
         'outpath': outpath,
         'playtime': playtime,
         'length': length}
        input['files'].append(d)
    else:
        files = metainfo['info']['files']
        for file in files:
            outpath = pathlist2filename(file['path'])
            if 'playtime' in file:
                playtime = file['playtime']
            else:
                playtime = None
            length = file['length']
            d = {'inpath': outpath,
             'outpath': outpath,
             'playtime': playtime,
             'length': length}
            input['files'].append(d)

    if 'azureus_properties' in metainfo:
        azprop = metainfo['azureus_properties']
        if 'Content' in azprop:
            content = metainfo['azureus_properties']['Content']
            if 'Thumbnail' in content:
                input['thumb'] = content['Thumbnail']
    if 'live' in metainfo['info']:
        input['live'] = metainfo['info']['live']
    if 'cs_keys' in metainfo['info']:
        input['cs_keys'] = metainfo['info']['cs_keys']
    if 'url-compat' in metainfo['info']:
        input['url-compat'] = metainfo['info']['url-compat']
    if 'ogg-headers' in metainfo:
        input['ogg-headers'] = metainfo['ogg-headers']
    if 'ns-metadata' in metainfo['info']:
        input['ns-metadata'] = metainfo['info']['ns-metadata']
    if 'x-ts-properties' in metainfo:
        input['x-ts-properties'] = metainfo['x-ts-properties']
    if 'url-list' in metainfo:
        input['url-list'] = metainfo['url-list']
    if 'httpseeds' in metainfo:
        input['httpseeds'] = metainfo['httpseeds']


def get_files(metainfo, exts):
    videofiles = []
    if 'files' in metainfo['info']:
        fileindex = 0
        files = metainfo['info']['files']
        for file in files:
            p = file['path']
            filename = ''
            for elem in p:
                filename = os.path.join(filename, elem)

            prefix, ext = os.path.splitext(filename)
            if ext != '' and ext[0] == '.':
                ext = ext[1:]
            if exts is None or ext.lower() in exts:
                videofiles.append((filename, file['length'], fileindex))
            fileindex += 1

    else:
        filename = metainfo['info']['name']
        prefix, ext = os.path.splitext(filename)
        if ext != '' and ext[0] == '.':
            ext = ext[1:]
        if exts is None or ext.lower() in exts:
            videofiles.append((filename, metainfo['info']['length'], 0))
    return videofiles
