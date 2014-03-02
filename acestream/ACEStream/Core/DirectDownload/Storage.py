#Embedded file name: ACEStream\Core\DirectDownload\Storage.pyo
import os
import time
import binascii
from threading import Thread, Lock
from traceback import print_exc
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False
MAXLOCKSIZE = 1000000000L
MAXLOCKRANGE = 3999999999L

class Storage:

    def __init__(self, dlhash, config, fileinfo, temp_dir, resumedata, finished_callback, filedata = None):
        self.lock = Lock()
        self.fileinfo = fileinfo
        self.size = fileinfo['size']
        self.amount_left = self.size
        self.notify_finished_done = False
        self.finished_callback = finished_callback
        self.file_allocated = False
        self.closed = False
        self.log_prefix = 'dd-storage::' + binascii.hexlify(dlhash) + ':'
        self.handles = {}
        self.whandles = {}
        self.tops = {}
        self.mtimes = {}
        self.temp_dir = temp_dir
        self.temp_files = {}
        self.got_data_observers_lock = Lock()
        self.got_data_observers = []
        self.ranges = {}
        if config.get('lock_files', True):
            self.lock_file, self.unlock_file = self._lock_file, self._unlock_file
        else:
            self.lock_file, self.unlock_file = lambda x1, x2: None, lambda x1, x2: None
        path = os.path.join(fileinfo['destdir'], fileinfo['filename'])
        if filedata is not None:
            h = open(path, 'wb+')
            h.write(filedata)
            h.flush()
            h.close()
            self.file_allocated = True
            self.amount_left = 0
            self.ranges[0] = self.size
            if DEBUG:
                log(self.log_prefix + '__init__: got filedata: path', path, 'size', self.size, 'ranges', self.ranges)
        if os.path.exists(path):
            self.tops[path] = os.path.getsize(path)
        else:
            h = open(path, 'wb+')
            h.flush()
            h.close()
            self.tops[path] = 0
        self.mtimes[path] = int(os.path.getmtime(path))
        self.path = path
        if resumedata is not None:
            self.restore_state(resumedata)
        if DEBUG:
            log(self.log_prefix + '__init__: path', path, 'size', self.size, 'allocated', self.file_allocated)
        if not self.file_allocated:
            self.init_preallocate()

    def init_preallocate(self):
        t = Thread(target=self.preallocate_file)
        t.setName('dd-storage-' + t.getName())
        t.setDaemon(True)
        t.start()

    def preallocate_file(self):
        try:
            i = 0
            t = time.time()
            path = self.path
            pos = self.tops[path]
            total_write = pos
            size = self.size
            allocsize = 1048576
            allocbuf = chr(255) * allocsize
            h = self.get_file_handle(path, True)
            h.seek(pos)
            while pos < size:
                if self.closed:
                    if DEBUG:
                        log(self.log_prefix + 'preallocate_file: storage is closed')
                    return
                e = min(size - pos, allocsize)
                total_write += e
                h.write(allocbuf[:e])
                pos += allocsize
                if DEBUG:
                    if i % 100 == 0:
                        log(self.log_prefix + 'preallocate_file: progress: path', self.path, 'progress', int(total_write / float(size) * 100), 'size', size, 'done', total_write)
                    i += 1
                time.sleep(0.01)

            if DEBUG:
                log(self.log_prefix + 'preallocate_file: path', self.path, 'size', self.size, 'written', total_write, 'time', time.time() - t)
            h.flush()
            self.lock.acquire()
            try:
                self.move_temp_files()
                self.file_allocated = True
                if self.amount_left == 0:
                    if DEBUG:
                        log(self.log_prefix + 'preallocate_file: download completed: ranges', self.ranges, 'size', self.size)
                    self.notify_finished()
            finally:
                self.lock.release()

        except:
            log_exc()

    def move_temp_files(self):
        if self.closed:
            if DEBUG:
                log(self.log_prefix + 'move_temp_files: storage is closed')
            return
        read_size = 1048576
        for pos, tmp_path in self.temp_files.iteritems():
            t = time.time()
            tmp = self.get_file_handle(tmp_path, False)
            main = self.get_file_handle(self.path, True)
            tmp.flush()
            tmp.seek(0)
            main.seek(pos)
            total_length = 0
            filesize = os.path.getsize(tmp_path)
            while True:
                data = tmp.read(read_size)
                if not data:
                    break
                total_length += len(data)
                main.write(data)

            if total_length != filesize:
                if DEBUG:
                    log(self.log_prefix + 'move_temp_files: size mismatch: path', tmp_path, 'filesize', filesize, 'total_length', total_length)
                raise ValueError('Failed to move temp file')
            if DEBUG:
                log(self.log_prefix + 'move_temp_files: file moved: pos', pos, 'path', tmp_path, 'filesize', filesize, 'time', time.time() - t)
            self._close(tmp_path)
            os.remove(tmp_path)

        self.temp_files = {}

    def add_got_data_observer(self, observer):
        self.got_data_observers_lock.acquire()
        try:
            if DEBUG:
                log(self.log_prefix + 'add_got_data_observer: observer', observer)
            self.got_data_observers.append(observer)
        finally:
            self.got_data_observers_lock.release()

    def remove_got_data_observer(self, observer):
        self.got_data_observers_lock.acquire()
        try:
            if DEBUG:
                log(self.log_prefix + 'remove_got_data_observer: observer', observer)
            if observer in self.got_data_observers:
                self.got_data_observers.remove(observer)
        finally:
            self.got_data_observers_lock.release()

    def get_dest_path(self):
        return self.path

    def get_content_length(self):
        return self.size

    def checkpoint(self):
        self.lock.acquire()
        try:
            temp_files = []
            for pos, path in self.temp_files.iteritems():
                top = self.tops[path]
                mtime = self.mtimes[path]
                temp_files.append((pos,
                 path,
                 top,
                 mtime))

            data = {'ranges': self.ranges,
             'size': self.size,
             'top': self.tops[self.path],
             'mtime': self.mtimes[self.path],
             'allocated': self.file_allocated,
             'temp_files': temp_files}
            return data
        finally:
            self.lock.release()

    def restore_state(self, data):
        self.lock.acquire()
        try:
            curtop = self.tops[self.path]
            curmtime = self.mtimes[self.path]
            file_valid = True
            if curtop != data['top']:
                if DEBUG:
                    log(self.log_prefix + 'restore_state: bad top: path', self.path, 'top', data['top'], 'curtop', curtop)
                file_valid = False
            elif curmtime > data['mtime'] + 1 or curmtime < data['mtime'] - 1:
                if DEBUG:
                    log(self.log_prefix + 'restore_state: bad mtime: path', self.path, 'mtime', data['mtime'], 'curmtime', curmtime)
                file_valid = False
            temp_files = {}
            for pos, path, top, mtime in data.get('temp_files', []):
                if temp_files.has_key(pos):
                    if DEBUG:
                        log(self.log_prefix + 'restore_state: duplicate temp file: path', path, 'pos', pos)
                    file_valid = False
                    break
                if not os.path.exists(path):
                    if DEBUG:
                        log(self.log_prefix + 'restore_state: temp file does not exists: path', path)
                    file_valid = False
                    break
                curtop = os.path.getsize(path)
                curmtime = os.path.getmtime(path)
                if top != curtop:
                    if DEBUG:
                        log(self.log_prefix + 'restore_state: bad top for temp file: path', path, 'top', top, 'curtop', curtop)
                    file_valid = False
                    break
                if curmtime > mtime + 1 or curmtime < mtime - 1:
                    if DEBUG:
                        log(self.log_prefix + 'restore_state: bad mtime for temp file: path', path, 'mtime', mtime, 'curmtime', curmtime)
                    file_valid = False
                    break
                if DEBUG:
                    log(self.log_prefix + 'restore_state: add temp file: pos', pos, 'path', path, 'top', curtop, 'mtime', curmtime)
                temp_files[pos] = path
                self.tops[path] = curtop
                self.mtimes[path] = curmtime

            if file_valid:
                allocated = data.get('allocated', False)
                if allocated:
                    curtop = self.tops[self.path]
                    if curtop != self.size:
                        if DEBUG:
                            log(self.log_prefix + 'restore_state: file allocated but size is incorrent: curtop', curtop, 'size', self.size, 'path', self.path)
                        file_valid = False
                    else:
                        self.file_allocated = True
            if file_valid:
                self.temp_files = temp_files
                self.ranges = data['ranges']
                for begin, length in self.ranges.iteritems():
                    self.amount_left -= length

            elif DEBUG:
                log(self.log_prefix + 'restore_state: invalid file: path', self.path)
            if DEBUG:
                log(self.log_prefix + 'restore_state: amount_left', self.amount_left, 'ranges', self.ranges)
        finally:
            self.lock.release()

    def get_progress(self):
        if not self.size:
            return 0.0
        if self.amount_left <= 0:
            return 1.0
        return 1.0 - self.amount_left / float(self.size)

    def get_amount_left(self):
        return self.amount_left

    def is_finished(self):
        if not self.size:
            return False
        return self.amount_left <= 0

    def get_unfinished_pos(self, pos):
        self.lock.acquire()
        try:
            avail, read_start, read_pos = self._get_available_length(pos)
            unfinished_pos = pos + avail
            if DEBUG:
                log(self.log_prefix + 'get_unfinished_pos: pos', pos, 'size', self.size, 'avail', avail, 'unfinished_pos', unfinished_pos)
            if unfinished_pos >= self.size:
                return
            return unfinished_pos
        finally:
            self.lock.release()

    def read(self, pos, size):
        self.lock.acquire()
        try:
            if self.closed:
                raise ValueError('Storage is closed')
            if self.size is None:
                raise ValueError('Size is not initialized')
            if pos >= self.size:
                raise ValueError('Read beyond content length')
            avail, read_start, read_pos = self._get_available_length(pos)
            if avail == 0:
                if DEBUG:
                    log(self.log_prefix + 'read: no data available: pos', pos, 'size', size)
                return
            if size > avail:
                size = avail
            if self.file_allocated:
                h = self.get_file_handle(self.path, False)
                h.seek(pos)
                data = h.read(size)
            else:
                if not self.temp_files.has_key(read_start):
                    if DEBUG:
                        log(self.log_prefix + 'read: missing temp file: pos', pos, 'read_start', read_start)
                    raise ValueError('Read error')
                if DEBUG:
                    log(self.log_prefix + 'read: read from temp file: pos', pos, 'read_start', read_start, 'read_pos', read_pos, 'path', self.temp_files[read_start])
                path = self.temp_files[read_start]
                h = self.get_file_handle(path, False)
                h.seek(read_pos)
                data = h.read(size)
            if DEBUG:
                log(self.log_prefix + 'read: got data: pos', pos, 'size', size, 'datalen', len(data))
            return data
        finally:
            self.lock.release()

    def write(self, pos, data):
        self.lock.acquire()
        try:
            if self.closed:
                raise ValueError('Storage is closed')
            if self.size is None:
                raise ValueError('Size is not initialized')
            datalen = len(data)
            if pos + datalen > self.size:
                raise ValueError('Write beyong content length')
            new_data_len, write_start, write_pos = self.update_ranges(pos, datalen)
            self.amount_left -= new_data_len
            if new_data_len != 0:
                if self.file_allocated:
                    h = self.get_file_handle(self.path, True)
                    h.seek(pos)
                    h.write(data)
                    if self.amount_left == 0:
                        if DEBUG:
                            log(self.log_prefix + 'write: download completed: ranges', self.ranges, 'size', self.size)
                        self.notify_finished()
                else:
                    self.write_temp_file(write_start, write_pos, data)
                self.got_data_observers_lock.acquire()
                try:
                    if len(self.got_data_observers):
                        new_observers = []
                        for observer in self.got_data_observers:
                            if observer(pos, datalen):
                                new_observers.append(observer)

                        self.got_data_observers = new_observers
                except:
                    if DEBUG:
                        print_exc()
                finally:
                    self.got_data_observers_lock.release()

            return new_data_len
        finally:
            self.lock.release()

    def notify_finished(self):
        if not self.notify_finished_done:
            self.sync()
            self.notify_finished_done = True
            self.finished_callback()

    def delete_temp_file(self, start):
        if self.temp_files.has_key(start):
            path = self.temp_files[start]
            if DEBUG:
                log(self.log_prefix + 'delete_temp_file: start', start, 'path', path)
            self._close(path)
            os.remove(path)

    def write_temp_file(self, start, pos, data):
        if self.closed:
            if DEBUG:
                log(self.log_prefix + 'write_temp_file: storage is closed: start', start, 'pos', pos)
            return False
        if not self.temp_files.has_key(start):
            temp_filename = self.fileinfo['filename'] + '.' + str(start) + '.tmp'
            path = os.path.join(self.temp_dir, temp_filename)
            if DEBUG:
                log(self.log_prefix + 'write_temp_file: create temp file: start', start, 'pos', pos, 'path', path)
            f = open(path, 'wb+')
            f.flush()
            f.close()
            self.temp_files[start] = path
            self.mtimes[path] = os.path.getmtime(path)
            self.tops[path] = os.path.getsize(path)
        path = self.temp_files[start]
        h = self.get_file_handle(path, True)
        h.seek(pos)
        h.write(data)
        return True

    def get_available_length(self, pos):
        self.lock.acquire()
        try:
            avail, read_start, read_pos = self._get_available_length(pos)
            return avail
        finally:
            self.lock.release()

    def _get_available_length(self, pos):
        avail_len = 0
        read_start = 0
        read_pos = 0
        for begin, rlen in self.ranges.iteritems():
            end = begin + rlen
            if begin <= pos < end:
                read_start = begin
                read_pos = pos - begin
                avail_len = end - pos
                if DEBUG:
                    log(self.log_prefix + 'get_available_length: found range: begin', begin, 'len', rlen, 'end', end, 'pos', pos, 'avail', avail_len)
                break

        if DEBUG:
            log(self.log_prefix + 'get_available_length: pos', pos, 'avail', avail_len, 'read_start', read_start, 'read_pos', read_pos)
        return (avail_len, read_start, read_pos)

    def update_ranges(self, pos, length):
        new_data_len = 0
        write_start = 0
        write_pos = 0
        updated_range_start = None
        updated_range_end = None
        if self.ranges.has_key(pos):
            if self.ranges[pos] >= length:
                if DEBUG:
                    log(self.log_prefix + 'update_ranges: duplicate data: pos', pos, 'datalen', length)
            else:
                new_data_len = length - self.ranges[pos]
                self.ranges[pos] = length
                updated_range_start = pos
                updated_range_end = pos + length
                write_start = pos
                write_pos = 0
        else:
            for begin, rlen in self.ranges.iteritems():
                end = begin + rlen
                if begin <= pos <= end:
                    if pos + length <= end:
                        if DEBUG:
                            log(self.log_prefix + 'update_ranges: found in existing data: pos', pos, 'datalen', length)
                        skip = True
                    else:
                        newlen = rlen + length - end + pos
                        new_data_len = newlen - self.ranges[begin]
                        self.ranges[begin] = newlen
                        updated_range_start = begin
                        updated_range_end = begin + newlen
                        write_start = updated_range_start
                        write_pos = pos - write_start
                    break
            else:
                self.ranges[pos] = length
                new_data_len = length
                write_start = pos
                write_pos = 0

        if updated_range_start is not None:
            swallow = []
            for begin, rlen in self.ranges.iteritems():
                if begin == updated_range_start:
                    continue
                if updated_range_start <= begin <= updated_range_end:
                    end = begin + rlen
                    if end > updated_range_end:
                        addlen = rlen + begin - updated_range_end
                        self.ranges[updated_range_start] += addlen
                        new_data_len += addlen - rlen
                        if DEBUG:
                            log(self.log_prefix + 'update_ranges: update range: updated_range_start', updated_range_start, 'updated_range_end', updated_range_end, 'begin', begin, 'rlen', rlen, 'addlen', addlen, 'write_start', write_start, 'write_pos', write_pos)
                    elif DEBUG:
                        log(self.log_prefix + 'update_ranges: skip update range: updated_range_start', updated_range_start, 'updated_range_end', updated_range_end, 'begin', begin, 'rlen', rlen, 'end', end)
                    swallow.append(begin)

            for begin in swallow:
                self.delete_temp_file(begin)
                del self.ranges[begin]

        return (new_data_len, write_start, write_pos)

    def sync(self):
        for file in self.whandles.keys():
            self._close(file)

    def close(self):
        self.lock.acquire()
        try:
            self.closed = True
            for file in self.handles.keys():
                self._close(file)

            self.handles = {}
            self.whandles = {}
        finally:
            self.lock.release()

    def get_file_handle(self, file, for_write):
        if self.handles.has_key(file):
            if for_write and not self.whandles.has_key(file):
                self._close(file)
                try:
                    f = self._open(file, 'rb+')
                    self.handles[file] = f
                    self.whandles[file] = 1
                    self.lock_file(file, f)
                except (IOError, OSError) as e:
                    if DEBUG:
                        log_exc()
                    raise IOError('unable to reopen ' + file + ': ' + str(e))

        else:
            try:
                if for_write:
                    f = self._open(file, 'rb+')
                    self.handles[file] = f
                    self.whandles[file] = 1
                    self.lock_file(file, f)
                else:
                    f = self._open(file, 'rb')
                    self.handles[file] = f
            except (IOError, OSError) as e:
                if DEBUG:
                    log_exc()
                raise IOError('unable to open ' + file + ': ' + str(e))

        return self.handles[file]

    def _open(self, file, mode):
        if self.mtimes.has_key(file):
            try:
                newmtime = os.path.getmtime(file)
                oldmtime = self.mtimes[file]
            except:
                if DEBUG:
                    log(self.log_prefix + '_open:' + file + ' modified: ' + strftime('(%x %X)', time.localtime(self.mtimes[file])) + strftime(' != (%x %X) ?', time.localtime(os.path.getmtime(file))))
                raise IOError('modified during download')

        try:
            return open(file, mode)
        except:
            if DEBUG:
                log_exc()
            raise

    def _close(self, file):
        f = self.handles[file]
        del self.handles[file]
        if self.whandles.has_key(file):
            del self.whandles[file]
            f.flush()
            self.unlock_file(file, f)
            f.close()
            self.tops[file] = os.path.getsize(file)
            self.mtimes[file] = os.path.getmtime(file)
        else:
            f.close()

    if os.name == 'nt':

        def _lock_file(self, name, f):
            if name == self.path:
                size = self.size
            else:
                size = self.tops[name]
            import msvcrt
            for p in range(0, min(size, MAXLOCKRANGE), MAXLOCKSIZE):
                f.seek(p)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, min(MAXLOCKSIZE, size - p))

        def _unlock_file(self, name, f):
            if name == self.path:
                size = self.size
            else:
                size = self.tops[name]
            import msvcrt
            for p in range(0, min(size, MAXLOCKRANGE), MAXLOCKSIZE):
                f.seek(p)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, min(MAXLOCKSIZE, size - p))

    elif os.name == 'posix':

        def _lock_file(self, name, f):
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

        def _unlock_file(self, name, f):
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    else:

        def _lock_file(self, name, f):
            pass

        def _unlock_file(self, name, f):
            pass
