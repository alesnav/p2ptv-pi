#Embedded file name: ACEStream\Core\Utilities\EncryptedStorage.pyo
import os
import hashlib
from ACEStream.Core.Utilities.TSCrypto import block_encrypt, block_decrypt
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class EncryptedStorageStream:

    def __init__(self, path, infohash, file_size, file_offset, piecelen, places = None, decrypt = True, offset_fix = None):
        self.path = path
        self.fp = open(self.path, 'rb')
        self.storage_secret = '8-90jm,2-=320fa&smnk/lsdgil,8as!8_'
        self.infohash = infohash
        file_begin = file_offset
        file_end = file_offset + file_size - 1
        self.file_range = ((file_begin / piecelen, file_begin % piecelen), (file_end / piecelen, file_end % piecelen))
        self.first_piecelen = piecelen - self.file_range[0][1]
        self.last_piecelen = self.file_range[1][1] + 1
        self.first_piece = self.file_range[0][0]
        self.last_piece = self.file_range[1][0]
        self.numpieces = self.last_piece - self.first_piece + 1
        self.piecelen = piecelen
        self.places = places
        self.decrypt = decrypt
        self.offset_fix = offset_fix
        self.file_offset = file_offset
        self.file_size = file_size
        self.cur_pos = 0
        if self.decrypt:
            self.encrypt_pieces = {self.first_piece: 1,
             self.last_piece: 1}
        else:
            self.encrypt_pieces = {}
        if DEBUG:
            log('EncryptedStorageStream::__init__: path', path, 'decrypt', decrypt, 'size', file_size, 'offset', file_offset, 'piecelen', piecelen, 'first_piece', self.first_piece, 'last_piece', self.last_piece, 'places', places)

    def read(self, length = None):
        if length is None:
            raise Exception, 'read without length is not implemented'
        pos = self.cur_pos
        if pos + length >= self.file_size:
            length = self.file_size - pos
            if DEBUG:
                log('es>>>read: corrent length: pos', pos, 'size', self.file_size, 'length', length)
        if length == 0:
            return ''
        piece_from = self._piecepos_from_bytepos(pos)
        piece_to = self._piecepos_from_bytepos(pos + length - 1)
        piece_to = (piece_to[0], piece_to[1] + 1)
        if DEBUG:
            log('EncryptedStorageStream::read: pos', pos, 'length', length, 'piece_from', piece_from, 'piece_to', piece_to)
        buf = ''
        for i in xrange(piece_from[0], piece_to[0] + 1):
            first = piece_from[0]
            last = piece_to[0]
            if self.places is not None and self.places.has_key(i):
                piece_place = self.places[i]
            else:
                piece_place = i
            start, end = self._bytepos_from_piecepos(piece_place)
            if i in self.encrypt_pieces:
                key = self.storage_secret + hashlib.sha1(self.infohash).digest() + str(i) + '0' * (10 - len(str(i)))
                start = piece_place * self.piecelen
                if self.offset_fix is not None:
                    start += self.offset_fix
                read_length = self.piecelen
                self.fp.seek(start)
                data = self.fp.read(read_length)
                data = block_decrypt(data, key)
                if DEBUG:
                    log('es>>> decrypt data: piece', i, 'piece_place', piece_place, 'pos', pos, 'start', start, 'read_length', read_length)
                read_from = None
                read_to = None
                if first == last:
                    read_from = piece_from[1]
                    read_to = piece_to[1]
                    data = data[read_from:read_to]
                elif i == first:
                    read_from = piece_from[1]
                    data = data[read_from:]
                elif i == last:
                    read_to = piece_to[1]
                    data = data[:read_to]
                if DEBUG:
                    log('es>>> read_from', read_from, 'read_to', read_to)
                buf += data
            else:
                if first == last:
                    start += piece_from[1]
                    read_length = piece_to[1] - piece_from[1]
                elif i == first:
                    read_length = self.piecelen - piece_from[1]
                    start += piece_from[1]
                elif i == last:
                    read_length = piece_to[1]
                else:
                    read_length = self.piecelen
                if DEBUG:
                    log('es>>> read raw data: piece', i, 'piece_place', piece_place, 'pos', pos, 'start', start, 'read_length', read_length)
                self.fp.seek(start)
                buf += self.fp.read(read_length)

        self.cur_pos += len(buf)
        if DEBUG:
            log('es>>> read done: want', length, 'read', len(buf), 'cur_pos', self.cur_pos)
        return buf

    def seek(self, pos, whence = os.SEEK_SET):
        if DEBUG:
            log('EncryptedStorageStream::seek: pos', pos, 'whence', whence)
        if whence != os.SEEK_SET:
            raise Exception, 'unsupported seek type: ' + str(whence)
        if pos < 0:
            raise Exception, 'position before file start'
        if pos >= self.file_size:
            raise Exception, 'position after file end'
        self.cur_pos = pos

    def close(self):
        if DEBUG:
            log('EncryptedStorageStream::close: ---')
        self.fp.close()

    def _piecepos_from_bytepos(self, bytepos, check_last = True):
        real_pos = bytepos + self.file_offset
        piece = real_pos / self.piecelen
        offset = real_pos % self.piecelen
        return (piece, offset)

    def _bytepos_from_piecepos(self, piece):
        if piece == self.first_piece:
            start = self.file_offset
            length = self.first_piecelen
        elif piece == self.last_piece:
            start = piece * self.piecelen
            length = self.last_piecelen
        else:
            start = piece * self.piecelen
            length = self.piecelen
        if self.offset_fix is not None:
            start += self.offset_fix
            if DEBUG:
                log('es::_bytepos_from_piecepos: fix start: offset_fix', self.offset_fix, 'piece', piece, 'start', start, 'length', length)
        return (start, start + length - 1)
