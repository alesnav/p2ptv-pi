#Embedded file name: ACEStream\Core\dispersy\singleton.pyo
from __future__ import with_statement
from threading import RLock

class Singleton(object):
    _singleton_lock = RLock()

    @classmethod
    def has_instance(cls, singleton_superclass = None):
        if singleton_superclass is not None:
            cls = singleton_superclass
        if hasattr(singleton_superclass, '_singleton_instance'):
            return getattr(singleton_superclass, '_singleton_instance')

    @classmethod
    def get_instance(cls, *args, **kargs):
        if 'singleton_superclass' in kargs:
            singleton_superclass = kargs['singleton_superclass']
            del kargs['singleton_superclass']
        else:
            singleton_superclass = cls
        if hasattr(singleton_superclass, '_singleton_instance'):
            return getattr(singleton_superclass, '_singleton_instance')
        with cls._singleton_lock:
            if not hasattr(singleton_superclass, '_singleton_instance'):
                setattr(singleton_superclass, '_singleton_instance', cls(*args, **kargs))
            return getattr(singleton_superclass, '_singleton_instance')

    @classmethod
    def del_instance(cls, singleton_superclass = None):
        if singleton_superclass is not None:
            cls = singleton_superclass
        with cls._singleton_lock:
            if hasattr(cls, '_singleton_instance'):
                delattr(cls, '_singleton_instance')


class Parameterized1Singleton(object):
    _singleton_lock = RLock()

    @classmethod
    def has_instance(cls, arg):
        if hasattr(cls, '_singleton_instances') and arg in getattr(cls, '_singleton_instances'):
            return getattr(cls, '_singleton_instances')[arg]

    @classmethod
    def get_instance(cls, *args, **kargs):
        if hasattr(cls, '_singleton_instances') and args[0] in getattr(cls, '_singleton_instances'):
            return getattr(cls, '_singleton_instances')[args[0]]
        with cls._singleton_lock:
            instance = cls(*args, **kargs)
            if not hasattr(cls, '_singleton_instances'):
                setattr(cls, '_singleton_instances', {})
            getattr(cls, '_singleton_instances')[args[0]] = instance
            return instance

    @classmethod
    def del_instance(cls, arg):
        with cls._singleton_lock:
            if hasattr(cls, '_singleton_instances') and arg in getattr(cls, '_singleton_instances'):
                del getattr(cls, '_singleton_instances')[arg]
                if not getattr(cls, '_singleton_instances'):
                    delattr(cls, '_singleton_instances')
