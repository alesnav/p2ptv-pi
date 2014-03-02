#Embedded file name: ACEStream\Video\Ogg.pyo
import sys
import os
from cStringIO import StringIO
DEBUG = False

def is_ogg(name):
    return name.endswith('.ogg') or name.endswith('.ogv') or name.endswith('ogm') or name.endswith('oga') or name.endswith('ogx')


def ogg_grab_page(input, checkcrc = False):
    capture_pattern = input.read(4)
    stream_structure_version = input.read(1)
    header_type_flag = input.read(1)
    granule_position = input.read(8)
    bitstream_serial_number = input.read(4)
    page_sequence_number = input.read(4)
    CRC_checksum = input.read(4)
    number_page_segments = input.read(1)
    segment_table = input.read(ord(number_page_segments))
    header_size = ord(number_page_segments) + 27
    segment_size = 0
    for i in range(0, ord(number_page_segments)):
        segment_size += ord(segment_table[i])

    page_size = header_size + segment_size
    if capture_pattern != 'OggS':
        raise ValueError('Header does not start with OggS')
    if page_size > 65307:
        raise ValueError('Page too big')
    if DEBUG:
        print >> sys.stderr, 'ogg: type', ord(header_type_flag)
    header = capture_pattern + stream_structure_version + header_type_flag + granule_position + bitstream_serial_number + page_sequence_number + CRC_checksum + number_page_segments + segment_table
    body = input.read(page_size - header_size)
    if checkcrc:
        import binascii
        import socket
        crcheader = capture_pattern + stream_structure_version + header_type_flag + granule_position + bitstream_serial_number + page_sequence_number + '\x00\x00\x00\x00' + number_page_segments + segment_table
        crcpage = crcheader + body
        newcrc = ogg_crc(crcpage)
        newcrcnbo = socket.htonl(newcrc) & 4294967295L
        newcrcstr = '%08x' % newcrcnbo
        oldcrcstr = binascii.hexlify(CRC_checksum)
        if DEBUG:
            print >> sys.stderr, 'ogg: CRC exp', oldcrcstr, 'got', newcrcstr
        if oldcrcstr != newcrcstr:
            raise ValueError('Page fails CRC check')
    header_type = body[0]
    isheader = False
    if header_type == '\x01' or header_type == '\x03' or header_type == '\x05':
        isheader = True
        vorbis_grab_header(StringIO(body))
    elif header_type == '\x80' or header_type == '\x81' or header_type == '\x82':
        isheader = True
        theora_grab_header(StringIO(body))
    elif header_type == '\x7f':
        isheader = True
        flac_grab_header(StringIO(body))
    return (isheader, header, body)


def vorbis_grab_header(input):
    if DEBUG:
        header_type = input.read(1)
        if header_type == '\x01':
            codec = input.read(6)
            print >> sys.stderr, 'ogg: Got vorbis ident header', codec
        elif header_type == '\x03':
            print >> sys.stderr, 'ogg: Got vorbis comment header'
        elif header_type == '\x05':
            print >> sys.stderr, 'ogg: Got vorbis setup header'


def theora_grab_header(input):
    if DEBUG:
        header_type = input.read(1)
        if header_type == '\x80':
            codec = input.read(6)
            print >> sys.stderr, 'ogg: Got theora ident header', codec
        elif header_type == '\x81':
            print >> sys.stderr, 'ogg: Got theora comment header'
        elif header_type == '\x82':
            print >> sys.stderr, 'ogg: Got theora setup header'


def flac_grab_header(input):
    if DEBUG:
        header_type = input.read(1)
        if header_type == '\x7f':
            codec = input.read(4)
            print >> sys.stderr, 'ogg: Got flac ident header', codec


def makeCRCTable(idx):
    r = idx << 24
    for i in range(8):
        if r & 2147483648L != 0:
            r = (r & 2147483647) << 1 ^ 79764919
        else:
            r = (r & 2147483647) << 1

    return r


CRCTable = [ makeCRCTable(i) for i in range(256) ]

def ogg_crc(src):
    crc = 0
    for c in src:
        crc = (crc & 16777215) << 8 ^ CRCTable[crc >> 24 ^ ord(c)]

    return crc


OGGMAGIC_TDEF = 0
OGGMAGIC_FIRSTPAGE = 1
OGGMAGIC_REST_OF_INPUT = 2

class OggMagicLiveStream:

    def __init__(self, tdef, input):
        self.tdef = tdef
        self.input = input
        self.firstpagestream = None
        self.mode = OGGMAGIC_TDEF
        self.find_first_page()

    def find_first_page(self):
        nwant = 65311
        firstpagedata = ''
        while len(firstpagedata) < nwant:
            print >> sys.stderr, 'OggMagicLiveStream: Reading first page, avail', self.input.available()
            data = self.input.read(nwant)
            firstpagedata += data
            if len(data) == 0 and len(firstpagedata < nwant):
                raise ValueError('OggMagicLiveStream: Could not get max. page bytes')

        self.firstpagestream = StringIO(firstpagedata)
        while True:
            char = self.firstpagestream.read(1)
            if len(char) == 0:
                break
            if char == 'O':
                rest = self.firstpagestream.read(3)
                if rest == 'ggS':
                    print >> sys.stderr, 'OggMagicLiveStream: Found page'
                    self.firstpagestream.seek(-4, os.SEEK_CUR)
                    break
                else:
                    self.firstpagestream.seek(-3, os.SEEK_CUR)

        if len(char) == 0:
            raise ValueError('OggMagicLiveStream: could not find start-of-page in P2P-stream')

    def read(self, numbytes = None):
        if numbytes is None:
            raise ValueError("OggMagicLiveStream: don't support read all")
        if self.mode == OGGMAGIC_TDEF:
            data = self.tdef.get_live_ogg_headers()
            if DEBUG:
                print >> sys.stderr, 'OggMagicLiveStream: Writing TDEF', len(data)
            if len(data) > numbytes:
                raise ValueError('OggMagicLiveStream: Not implemented, Ogg headers too big, need more code')
            self.mode = OGGMAGIC_FIRSTPAGE
            return data
        if self.mode == OGGMAGIC_FIRSTPAGE:
            data = self.firstpagestream.read(numbytes)
            if DEBUG:
                print >> sys.stderr, 'OggMagicLiveStream: Writing 1st remain', len(data)
            if len(data) == 0:
                self.mode = OGGMAGIC_REST_OF_INPUT
                return self.input.read(numbytes)
            else:
                return data
        elif self.mode == OGGMAGIC_REST_OF_INPUT:
            data = self.input.read(numbytes)
            return data

    def seek(self, offset, whence = None):
        print >> sys.stderr, 'OggMagicLiveStream: SEEK CALLED', offset, whence
        if offset == 0:
            if self.mode != OGGMAGIC_TDEF:
                self.mode = OGGMAGIC_TDEF
                self.find_first_page()
        else:
            raise ValueError("OggMagicLiveStream doens't support seeking other than to beginning")

    def close(self):
        self.input.close()

    def available(self):
        return -1


if __name__ == '__main__':
    header_pages = []
    f = open('libre.ogg', 'rb')
    while True:
        isheader, header, body = ogg_grab_page(f)
        if not isheader:
            break
        else:
            header_pages.append((header, body))

    f.close()
    g = open('stroom.ogg', 'rb')
    while True:
        char = g.read(1)
        if len(char) == 0:
            break
        if char == 'O':
            rest = g.read(3)
            if rest == 'ggS':
                print >> sys.stderr, 'Found page'
                g.seek(-4, os.SEEK_CUR)
                isheader, pheader, pbody = ogg_grab_page(g)
                break
            else:
                g.seek(-3, os.SEEK_CUR)

    if len(char) > 0:
        h = open('new.ogg', 'wb')
        for header, body in header_pages:
            h.write(header)
            h.write(body)

        h.write(pheader)
        h.write(pbody)
        while True:
            data = g.read(65536)
            if len(data) == 0:
                break
            else:
                h.write(data)

        h.close()
    g.close()
