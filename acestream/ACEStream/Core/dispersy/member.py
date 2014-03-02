#Embedded file name: ACEStream\Core\dispersy\member.pyo
from __future__ import with_statement
from hashlib import sha1
from singleton import Parameterized1Singleton
from dispersydatabase import DispersyDatabase
from crypto import ec_from_private_bin, ec_from_public_bin, ec_to_public_bin, ec_signature_length, ec_verify, ec_sign
from encoding import encode, decode

class Public(object):

    @property
    def mid(self):
        raise NotImplementedError()

    @property
    def public_key(self):
        raise NotImplementedError()

    @property
    def signature_length(self):
        raise NotImplementedError()

    def verify(self, data, signature, offset = 0, length = 0):
        raise NotImplementedError()


class Private(object):

    @property
    def private_key(self):
        raise NotImplementedError()

    def sign(self, data, offset = 0, length = 0):
        raise NotImplementedError()


class Member(Public, Parameterized1Singleton):
    _singleton_instances = {}

    def __init__(self, public_key, ec = None, sync_with_database = True):
        self._public_key = public_key
        if ec is None:
            self._ec = ec_from_public_bin(public_key)
        else:
            self._ec = ec
        self._signature_length = ec_signature_length(self._ec)
        self._mid = sha1(public_key).digest()
        self._database_id = -1
        self._address = ('', -1)
        self._tags = []
        if sync_with_database:
            if not self.update():
                database = DispersyDatabase.get_instance()
                database.execute(u'INSERT INTO user(mid, public_key) VALUES(?, ?)', (buffer(self._mid), buffer(self._public_key)))
                self._database_id = database.last_insert_rowid

    def update(self):
        try:
            execute = DispersyDatabase.get_instance().execute
            self._database_id, host, port, tags = execute(u'SELECT id, host, port, tags FROM user WHERE public_key = ? LIMIT 1', (buffer(self._public_key),)).next()
            self._address = (str(host), port)
            self._tags = []
            if tags:
                self._tags = list(execute(u'SELECT key FROM tag WHERE value & ?', (tags,)))
            return True
        except StopIteration:
            return False

    @property
    def mid(self):
        return self._mid

    @property
    def public_key(self):
        return self._public_key

    @property
    def signature_length(self):
        return self._signature_length

    @property
    def database_id(self):
        return self._database_id

    @property
    def address(self):
        return self._address

    def _set_tag(self, tag, value):
        if value:
            if tag in self._tags:
                return False
            self._tags.append(tag)
        else:
            if tag not in self._tags:
                return False
            self._tags.remove(tag)
        with DispersyDatabase.get_instance() as execute:
            tags = list(execute(u'SELECT key, value FROM tag'))
            int_tags = [0, 0] + [ key for key, value in tags if value in self._tags ]
            reduced = reduce(lambda a, b: a | b, int_tags)
            execute(u'UPDATE user SET tags = ? WHERE public_key = ?', (reduced, buffer(self._public_key)))
        return True

    def __get_must_store(self):
        return u'store' in self._tags

    def __set_must_store(self, value):
        return self._set_tag(u'store', value)

    must_store = property(__get_must_store, __set_must_store)

    def __get_must_ignore(self):
        return u'ignore' in self._tags

    def __set_must_ignore(self, value):
        return self._set_tag(u'ignore', value)

    must_ignore = property(__get_must_ignore, __set_must_ignore)

    def __get_must_drop(self):
        return u'drop' in self._tags

    def __set_must_drop(self, value):
        return self._set_tag(u'drop', value)

    must_drop = property(__get_must_drop, __set_must_drop)

    def verify(self, data, signature, offset = 0, length = 0):
        length = length or len(data)
        return self._signature_length == len(signature) and ec_verify(self._ec, sha1(data[offset:offset + length]).digest(), signature)

    def __eq__(self, member):
        return self._public_key.__eq__(member._public_key)

    def __ne__(self, member):
        return self._public_key.__ne__(member._public_key)

    def __cmp__(self, member):
        return self._public_key.__cmp__(member._public_key)

    def __hash__(self):
        return self._public_key.__hash__()

    def __str__(self):
        return '<%s %d %s>' % (self.__class__.__name__, self._database_id, self._mid.encode('HEX'))


class PrivateMember(Private, Member):

    def __init__(self, public_key, private_key = None, sync_with_database = True):
        if sync_with_database:
            if private_key is None:
                database = DispersyDatabase.get_instance()
                try:
                    private_key = str(database.execute(u'SELECT private_key FROM key WHERE public_key == ? LIMIT 1', (buffer(public_key),)).next()[0])
                except StopIteration:
                    pass

            else:
                database = DispersyDatabase.get_instance()
                database.execute(u'INSERT OR IGNORE INTO key(public_key, private_key) VALUES(?, ?)', (buffer(public_key), buffer(private_key)))
        if private_key is None:
            raise ValueError('The private key is unavailable')
        super(PrivateMember, self).__init__(public_key, ec_from_private_bin(private_key), sync_with_database)
        self._private_key = private_key

    @property
    def private_key(self):
        return self._private_key

    def sign(self, data, offset = 0, length = 0):
        return ec_sign(self._ec, sha1(data[offset:length or len(data)]).digest())


class MasterMember(Member):
    pass


class ElevatedMasterMember(MasterMember, PrivateMember):
    pass


class MyMember(PrivateMember):
    pass
