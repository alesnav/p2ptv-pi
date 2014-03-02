#Embedded file name: ACEStream\Core\Merkle\merkle.pyo
from math import log, pow, floor
from ACEStream.Core.Utilities.TSCrypto import sha
import sys
DEBUG = False

class MerkleTree:

    def __init__(self, piece_size, total_length, root_hash = None, hashes = None):
        self.npieces = len2npieces(piece_size, total_length)
        self.treeheight = get_tree_height(self.npieces)
        self.tree = create_tree(self.treeheight)
        if hashes is None:
            self.root_hash = root_hash
        else:
            fill_tree(self.tree, self.treeheight, self.npieces, hashes)
            if root_hash is None:
                self.root_hash = self.tree[0]
            else:
                raise AssertionError, 'merkle: if hashes not None, root_hash must be'

    def get_root_hash(self):
        return self.root_hash

    def compare_root_hashes(self, other):
        return self.root_hash == other

    def get_hashes_for_piece(self, index):
        return get_hashes_for_piece(self.tree, self.treeheight, index)

    def check_hashes(self, hashlist):
        return check_tree_path(self.root_hash, self.treeheight, hashlist)

    def update_hash_admin(self, hashlist, piece_hashes):
        update_hash_admin(hashlist, self.tree, self.treeheight, piece_hashes)

    def get_piece_hashes(self):
        return get_piece_hashes(self.tree, self.treeheight, self.npieces)


def create_fake_hashes(info):
    total_length = calc_total_length(info)
    npieces = len2npieces(info['piece length'], total_length)
    return ['\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'] * npieces


def len2npieces(piece_size, total_length):
    npieces = total_length / piece_size
    if piece_size * npieces < total_length:
        npieces += 1
    return npieces


def calc_total_length(info):
    if info.has_key('length'):
        return info['length']
    files = info['files']
    total_length = 0
    for i in range(0, len(files)):
        total_length += files[i]['length']

    return total_length


def get_tree_height(npieces):
    if DEBUG:
        print >> sys.stderr, 'merkle: number of pieces is', npieces
    height = log(npieces, 2)
    if height - floor(height) > 0.0:
        height = int(height) + 1
    else:
        height = int(height)
    if DEBUG:
        print >> sys.stderr, 'merkle: tree height is', height
    return height


def create_tree(height):
    treesize = int(pow(2, height + 1) - 1)
    if DEBUG:
        print >> sys.stderr, 'merkle: treesize', treesize
    tree = ['\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'] * treesize
    return tree


def fill_tree(tree, height, npieces, hashes):
    startoffset = int(pow(2, height) - 1)
    if DEBUG:
        print >> sys.stderr, 'merkle: bottom of tree starts at', startoffset
    for offset in range(startoffset, startoffset + npieces):
        tree[offset] = hashes[offset - startoffset]

    for level in range(height, 0, -1):
        if DEBUG:
            print >> sys.stderr, 'merkle: calculating level', level
        for offset in range(int(pow(2, level) - 1), int(pow(2, level + 1) - 2), 2):
            parentstartoffset, parentoffset = get_parent_offset(offset, level)
            data = tree[offset] + tree[offset + 1]
            digester = sha()
            digester.update(data)
            digest = digester.digest()
            tree[parentoffset] = digest

    return tree


def get_hashes_for_piece(tree, height, index):
    startoffset = int(pow(2, height) - 1)
    myoffset = startoffset + index
    if DEBUG:
        print >> sys.stderr, 'merkle: myoffset', myoffset
    hashlist = [[myoffset, tree[myoffset]]]
    if myoffset % 2 == 0:
        siblingoffset = myoffset - 1
    else:
        siblingoffset = myoffset + 1
    if DEBUG:
        print >> sys.stderr, 'merkle: siblingoffset', siblingoffset
    if siblingoffset != -1:
        hashlist.append([siblingoffset, tree[siblingoffset]])
    uncleoffset = myoffset
    for level in range(height, 0, -1):
        uncleoffset = get_uncle_offset(uncleoffset, level)
        if DEBUG:
            print >> sys.stderr, 'merkle: uncleoffset', uncleoffset
        hashlist.append([uncleoffset, tree[uncleoffset]])

    return hashlist


def check_tree_path(root_hash, height, hashlist):
    maxoffset = int(pow(2, height + 1) - 2)
    mystartoffset = int(pow(2, height) - 1)
    i = 0
    a = hashlist[i]
    if a[0] < 0 or a[0] > maxoffset:
        return False
    i += 1
    b = hashlist[i]
    if b[0] < 0 or b[0] > maxoffset:
        return False
    i += 1
    myindex = a[0] - mystartoffset
    sibindex = b[0] - mystartoffset
    for level in range(height, 0, -1):
        if DEBUG:
            print >> sys.stderr, 'merkle: checking level', level
        a = check_fork(a, b, level)
        b = hashlist[i]
        if b[0] < 0 or b[0] > maxoffset:
            return False
        i += 1

    if DEBUG:
        print >> sys.stderr, 'merkle: ROOT HASH', `(str(root_hash))`, '==', `(str(a[1]))`
    if a[1] == root_hash:
        return True
    else:
        return False


def update_hash_admin(hashlist, tree, height, hashes):
    mystartoffset = int(pow(2, height) - 1)
    for i in range(0, len(hashlist)):
        if i < 2:
            index = hashlist[i][0] - mystartoffset
            if index < len(hashes):
                if DEBUG:
                    print >> sys.stderr, 'merkle: update_hash_admin: saving hash of', index
                hashes[index] = hashlist[i][1]
        tree[hashlist[i][0]] = hashlist[i][1]


def check_fork(a, b, level):
    myoffset = a[0]
    siblingoffset = b[0]
    if myoffset > siblingoffset:
        data = b[1] + a[1]
        if DEBUG:
            print >> sys.stderr, 'merkle: combining', siblingoffset, myoffset
    else:
        data = a[1] + b[1]
        if DEBUG:
            print >> sys.stderr, 'merkle: combining', myoffset, siblingoffset
    digester = sha()
    digester.update(data)
    digest = digester.digest()
    parentstartoffset, parentoffset = get_parent_offset(myoffset, level - 1)
    return [parentoffset, digest]


def get_parent_offset(myoffset, level):
    parentstartoffset = int(pow(2, level) - 1)
    mystartoffset = int(pow(2, level + 1) - 1)
    parentoffset = parentstartoffset + (myoffset - mystartoffset) / 2
    return [parentstartoffset, parentoffset]


def get_uncle_offset(myoffset, level):
    if level == 1:
        return 0
    parentstartoffset, parentoffset = get_parent_offset(myoffset, level - 1)
    if DEBUG:
        print >> sys.stderr, 'merkle: parent offset', parentoffset
    parentindex = parentoffset - parentstartoffset
    if parentoffset % 2 == 0:
        uncleoffset = parentoffset - 1
    else:
        uncleoffset = parentoffset + 1
    return uncleoffset


def get_piece_hashes(tree, height, npieces):
    startoffset = int(pow(2, height) - 1)
    hashes = ['\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'] * npieces
    for offset in range(startoffset, startoffset + npieces):
        hashes[offset - startoffset] = tree[offset]

    return hashes
