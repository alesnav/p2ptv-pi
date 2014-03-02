#Embedded file name: ACEStream\Core\Utilities\mp4metadata.pyo
import binascii
import os
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

def clear_mp4_metadata_tag(tag, data):
    try:
        pos = data.find(tag)
        if pos == -1:
            return None
        if DEBUG:
            log('clear_mp4_metadata_tag: tag found: tag', tag, 'pos', pos)
        if pos < 4:
            if DEBUG:
                log('clear_mp4_metadata_tag: truncated data start: tag', tag, 'pos', pos)
            return None
        item_atom_size = data[pos - 4:pos]
        item_atom_size = int(binascii.hexlify(item_atom_size), 16)
        datalen = len(data)
        if pos - 1 + item_atom_size > datalen:
            if DEBUG:
                log('clear_mp4_metadata_tag: truncated data end: tag', tag, 'pos', pos, 'item_atom_size', item_atom_size, 'datalen', datalen)
            return None
        data_size = data[pos + 4:pos + 8]
        data_size = int(binascii.hexlify(data_size), 16)
        if item_atom_size - data_size != 8:
            if DEBUG:
                log('clear_mp4_metadata_tag: sizse does not match: item_atom_size', item_atom_size, 'data_size', data_size)
            return None
        data_elem = data[pos + 8:pos + 12]
        data_flags = data[pos + 12:pos + 20]
        data_flags = binascii.hexlify(data_flags)
        value_start = pos + 20
        value_end = pos + 4 + data_size
        value = data[value_start:value_end]
        if DEBUG:
            log('clear_mp4_metadata_tag: item_atom_size', item_atom_size, 'data_size', data_size, 'data_elem', data_elem, 'data_flags', data_flags, 'value_start', value_start, 'value_end', value_end)
        if data_elem != 'data' or data_flags != '0000000100000000':
            if DEBUG:
                log('clear_mp4_metadata_tag: malformed data')
            return None
        new_data = data[:value_start] + chr(0) * len(value) + data[value_end:]
        if len(new_data) != datalen:
            if DEBUG:
                log('clear_mp4_metadata_tag: modified data size mismatch: datalen', datalen, 'newdatalen', len(new_data))
            return None
        return new_data
    except:
        log_exc()
        return None


def clear_mp4_metadata_tags_from_file(path, tags, max_offset = 524288):
    try:
        if not os.path.exists(path):
            raise ValueError, 'File not exists: ' + str(path)
        cleared_tags = []
        f = open(path, 'rb+')
        data = f.read(max_offset)
        if data:
            for tag in tags:
                updated_data = clear_mp4_metadata_tag(tag, data)
                if updated_data is not None:
                    if DEBUG:
                        log('clear_mp4_metadata_tags_from_file: cleared tag:', tag)
                    cleared_tags.append(tag)
                    data = updated_data

            if len(cleared_tags):
                f.seek(0)
                f.write(data)
        f.close()
        return cleared_tags
    except:
        return []
