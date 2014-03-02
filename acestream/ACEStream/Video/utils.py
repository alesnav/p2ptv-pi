#Embedded file name: ACEStream\Video\utils.pyo
import os
import sys
from ACEStream.Core.Utilities.unicode import unicode2str
if sys.platform == 'win32':
    from ACEStream.Core.Utilities.win32regchecker import Win32RegChecker, HKLM
videoextdefaults = ['3gp',
 'aac',
 'ape',
 'asf',
 'avi',
 'dv',
 'divx',
 'flac',
 'flc',
 'flv',
 'm2ts',
 'm4a',
 'mka',
 'mkv',
 'mpeg',
 'mpeg4',
 'mpegts',
 'mpg4',
 'mp3',
 'mp4',
 'mpg',
 'mov',
 'm4v',
 'ogg',
 'ogm',
 'ogv',
 'oga',
 'ogx',
 'qt',
 'rm',
 'swf',
 'ts',
 'vob',
 'wmv',
 'wav',
 'webm']
svcextdefaults = []
DEBUG = False

def win32_retrieve_video_play_command(ext, videourl):
    registry = Win32RegChecker()
    if DEBUG:
        print >> sys.stderr, 'videoplay: Looking for player for', unicode2str(videourl)
    if ext == '':
        return [None, None]
    contenttype = registry.readRootKey(ext, value_name='Content Type', ignore_errors=True)
    return [contenttype, '']


def win32_retrieve_playcmd_from_mimetype(mimetype, videourl):
    registry = Win32RegChecker()
    if DEBUG:
        print >> sys.stderr, 'videoplay: Looking for player for', unicode2str(videourl)
    if mimetype == '' or mimetype is None:
        return [None, None]
    keyname = '\\SOFTWARE\\Classes\\MIME\\Database\\Content Type\\' + mimetype
    valuename = 'Extension'
    ext = registry.readKeyRecursively(HKLM, keyname, value_name=valuename)
    if DEBUG:
        print >> sys.stderr, 'videoplay: ext winfiletype is', ext
    if ext is None or ext == '':
        return [None, None]
    if DEBUG:
        print >> sys.stderr, 'videoplay: Looking for player for mime', mimetype, 'which is ext', ext
    return win32_retrieve_video_play_command(ext, videourl)


def quote_program_path(progpath):
    idx = progpath.find(' ')
    if idx != -1:
        if not os.access(progpath, os.R_OK):
            if DEBUG:
                print >> sys.stderr, 'videoplay: Could not find assumed progpath', progpath
            return None
        return '"' + progpath + '"'
    else:
        return progpath
