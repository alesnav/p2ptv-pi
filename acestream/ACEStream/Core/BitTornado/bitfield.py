#Embedded file name: ACEStream\Core\BitTornado\bitfield.pyo
import sys
try:
    True
except:
    True = 1
    False = 0
    bool = lambda x: not not x

try:
    sum([1])
    negsum = lambda a: len(a) - sum(a)
except:
    negsum = lambda a: reduce(lambda x, y: x + (not y), a, 0)

def _int_to_booleans(x):
    r = []
    for i in range(8):
        r.append(bool(x & 128))
        x <<= 1

    return tuple(r)


lookup_table = []
reverse_lookup_table = {}
for i in xrange(256):
    x = _int_to_booleans(i)
    lookup_table.append(x)
    reverse_lookup_table[x] = chr(i)

class Bitfield:

    def __init__(self, length = None, bitstring = None, copyfrom = None, fromarray = None, calcactiveranges = False):
        self.activeranges = []
        if copyfrom is not None:
            self.length = copyfrom.length
            self.array = copyfrom.array[:]
            self.numfalse = copyfrom.numfalse
            return
        if length is None:
            raise ValueError, 'length must be provided unless copying from another array'
        self.length = length
        if bitstring is not None:
            extra = len(bitstring) * 8 - length
            if extra < 0 or extra >= 8:
                raise ValueError
            t = lookup_table
            r = []
            chr0 = chr(0)
            inrange = False
            startpiece = 0
            countpiece = 0
            for c in bitstring:
                r.extend(t[ord(c)])
                if calcactiveranges:
                    if c != chr0:
                        if inrange:
                            pass
                        else:
                            startpiece = countpiece
                            inrange = True
                    elif inrange:
                        self.activeranges.append((startpiece, countpiece))
                        inrange = False
                    countpiece += 8

            if calcactiveranges:
                if inrange:
                    self.activeranges.append((startpiece, min(countpiece, self.length - 1)))
            if extra > 0:
                if r[-extra:] != [0] * extra:
                    raise ValueError
                del r[-extra:]
            self.array = r
            self.numfalse = negsum(r)
        elif fromarray is not None:
            self.array = fromarray
            self.numfalse = negsum(self.array)
        else:
            self.array = [False] * length
            self.numfalse = length

    def __setitem__(self, index, val):
        val = bool(val)
        self.numfalse += self.array[index] - val
        self.array[index] = val

    def __getitem__(self, index):
        return self.array[index]

    def __len__(self):
        return self.length

    def tostring(self):
        booleans = self.array
        t = reverse_lookup_table
        s = len(booleans) % 8
        r = [ t[tuple(booleans[x:x + 8])] for x in xrange(0, len(booleans) - s, 8) ]
        if s:
            r += t[tuple(booleans[-s:] + [0] * (8 - s))]
        return ''.join(r)

    def complete(self):
        return not self.numfalse

    def copy(self):
        return self.array[:self.length]

    def toboollist(self):
        bools = [False] * self.length
        for piece in range(0, self.length):
            bools[piece] = self.array[piece]

        return bools

    def get_active_ranges(self):
        return self.activeranges

    def get_numtrue(self):
        return self.length - self.numfalse


def test_bitfield():
    try:
        x = Bitfield(7, 'ab')
    except ValueError:
        pass

    try:
        x = Bitfield(7, 'ab')
    except ValueError:
        pass

    try:
        x = Bitfield(9, 'abc')
    except ValueError:
        pass

    try:
        x = Bitfield(0, 'a')
    except ValueError:
        pass

    try:
        x = Bitfield(1, '')
    except ValueError:
        pass

    try:
        x = Bitfield(7, '')
    except ValueError:
        pass

    try:
        x = Bitfield(8, '')
    except ValueError:
        pass

    try:
        x = Bitfield(9, 'a')
    except ValueError:
        pass

    try:
        x = Bitfield(7, chr(1))
    except ValueError:
        pass

    try:
        x = Bitfield(9, chr(0) + chr(64))
    except ValueError:
        pass

    x = Bitfield(1)
    x[0] = 1
    x[0] = 1
    x = Bitfield(7)
    x[6] = 1
    x = Bitfield(8)
    x[7] = 1
    x = Bitfield(9)
    x[8] = 1
    x = Bitfield(8, chr(196))
