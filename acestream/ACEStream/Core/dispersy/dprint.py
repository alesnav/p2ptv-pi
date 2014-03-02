#Embedded file name: ACEStream\Core\dispersy\dprint.pyo
from pickle import dumps
from os.path import dirname, basename, expanduser, isfile, join
from sys import stdout, stderr, exc_info
from time import time
from traceback import extract_stack, print_exception, print_stack, format_list
import inspect
import re
import socket
from os import getcwd
try:
    from sys import maxsize
except ImportError:
    from sys import maxint as maxsize

LEVEL_DEBUG = 0
LEVEL_NORMAL = 128
LEVEL_LOG = 142
LEVEL_NOTICE = 167
LEVEL_WARNING = 192
LEVEL_ERROR = 224
level_map = {'debug': LEVEL_DEBUG,
 'normal': LEVEL_NORMAL,
 'log': LEVEL_LOG,
 'notice': LEVEL_NOTICE,
 'warning': LEVEL_WARNING,
 'error': LEVEL_ERROR}
level_tag_map = {LEVEL_DEBUG: 'D',
 LEVEL_NORMAL: ' ',
 LEVEL_LOG: 'L',
 LEVEL_NOTICE: 'N',
 LEVEL_WARNING: 'W',
 LEVEL_ERROR: 'E'}
_dprint_settings = {'box': False,
 'box_char': '-',
 'box_width': 80,
 'binary': False,
 'callback': None,
 'exception': False,
 'glue': '',
 'level': LEVEL_NORMAL,
 'line': False,
 'line_char': '-',
 'line_width': 80,
 'lines': False,
 'meta': False,
 'remote': False,
 'remote_host': 'localhost',
 'remote_port': 12345,
 'source_file': None,
 'source_function': None,
 'source_line': None,
 'stack': False,
 'stack_origin_modifier': -1,
 'stack_ident': None,
 'stderr': False,
 'stdout': True,
 'style': 'column'}
_filters = {'ENTRY': [True, []]}
_filter_entry = _filters['ENTRY']
_filter_policy_map = {'accept': True,
 'drop': False,
 'return': None}
_filter_reverse_policy_map = {True: 'accept',
 False: 'drop',
 None: 'return'}
_filter_reverse_target_map = {True: 'accept',
 False: 'drop',
 None: 'continue'}
_filter_target_map = {'accept': True,
 'drop': False,
 'continue': None}

def _filter_reverse_dictionary_lookup(dic, value):
    for key, value_ in dic.items():
        if value is value_:
            return key


def filter_chains_get():
    return [ (chain, _filter_reverse_policy_map[policy]) for chain, (policy, rules) in _filters.items() ]


def filter_get(chain):
    return [ (function.__name__, target in (True, False, None) and _filter_reverse_target_map[target] or 'jump', target not in (True, False, None) and _filter_reverse_dictionary_lookup(_filters, target) or None) for function, target in _filters[chain][1] ]


def filter_chain_create(chain, policy):
    _filters[chain] = [_filter_policy_map[policy], []]


def filter_chain_policy(chain, policy):
    _filters[chain][0] = _filter_policy_map[policy]


def filter_chain_remove(chain):
    del _filters[chain]


def filter_add(chain, function, target, jump = None, position = maxsize):
    if target in _filter_target_map:
        target = _filter_target_map[target]
    else:
        target = _filters[jump]
    _filters[chain][1].insert(position, [function, target])


def filter_remove(chain, position):
    del _filters[chain][1][position]


def filter_add_by_source(chain, target, file = None, function = None, path = None, jump = None, position = maxsize):

    def match(args, settings):
        result = True
        if file:
            result = result and settings['source_file'].endswith(file)
        if path:
            result = result and path in settings['source_file']
        if function:
            result = result and function == settings['source_function']
        return result

    if path is not None:
        path = join(*path.split('.'))
    match.__name__ = 'by_source(%s, %s, %s)' % (file, function, path)
    filter_add(chain, match, target, jump=jump, position=position)


def filter_add_by_level(chain, target, exact = None, min = None, max = None, jump = None, position = maxsize):
    if exact in level_map:
        exact = level_map[exact]
    if min in level_map:
        min = level_map[min]
    if max in level_map:
        max = level_map[max]
    if exact is None:

        def match(args, settings):
            return min <= settings['level'] <= max

    else:

        def match(args, settings):
            return exact == settings['level']

    match.__name__ = 'by_level(%s, %s, %s)' % (exact, min, max)
    filter_add(chain, match, target, jump=jump, position=position)


def filter_add_by_pattern(chain, target, pattern, jump = None, position = maxsize):
    pattern = re.compile(pattern)

    def match(args, settings):
        for arg in args:
            if pattern.match(str(arg)):
                return True

        return False

    match.__name__ = 'by_pattern(%s)' % pattern.pattern
    filter_add(chain, match, target, jump=jump, position=position)


def filter_print():
    for chain, policy in filter_chains_get():
        print 'Chain %s (policy %s)' % (chain, policy)
        for check, target, jump in filter_get(chain):
            if not jump:
                jump = ''
            print '%-6s %-15s %s' % (target, jump, check)

        print ()


def filter_check(args, settings):
    return _filter_check(args, settings, _filter_entry)


def _filter_check(args, settings, chain_info):
    for filter_info in chain_info[1]:
        if filter_info[0](args, settings):
            if filter_info[1] is True:
                return True
            if filter_info[1] is False:
                return False
            if filter_info[1] is None:
                continue
            else:
                result = _filter_check(args, settings, filter_info[1])
                if result is None:
                    continue
                else:
                    return result

    return chain_info[0]


def _config_read():

    def get_arguments(string, conversions, glue):

        def helper(index, func):
            if len(args) > index:
                return func(args[index])

        args = string.split(glue)
        return [ helper(index, func) for index, func in zip(xrange(len(conversions)), conversions) ]

    def strip(string):
        return string.strip()

    re_section = re.compile('^\\s*\\[\\s*(.+?)\\s*\\]\\s*$')
    re_option = re.compile('^\\s*([^#].+?)\\s*=\\s*(.+?)\\s*$')
    re_true = re.compile('^true|t|1$')
    options = []
    sections = {'default': options}
    for file_ in ['dprint.conf', expanduser('~/dprint.conf')]:
        if isfile(file_):
            line_number = 0
            for line in open(file_, 'r'):
                line_number += 1
                match = re_option.match(line)
                if match:
                    options.append((line_number,
                     line[:-1],
                     match.group(1),
                     match.group(2)))
                    continue
                match = re_section.match(line)
                if match:
                    section = match.group(1)
                    if section in sections:
                        options = sections[section]
                    else:
                        options = []
                        sections[section] = options
                    continue

    string = ['box_char',
     'glue',
     'line_char',
     'remote_host',
     'source_file',
     'source_function',
     'style']
    int_ = ['box_width',
     'line_width',
     'remote_port',
     'source_line',
     'stack_origin_modifier']
    boolean = ['box',
     'binary',
     'exception',
     'exclude_policy',
     'line',
     'lines',
     'meta',
     'remote',
     'stack',
     'stderr',
     'stdout']
    for line_number, line, before, after in sections['default']:
        try:
            if before in string:
                _dprint_settings[before] = after
            elif before in int_:
                if after.isdigit():
                    _dprint_settings[before] = int(after)
                else:
                    raise ValueError('Not a number')
            elif before in boolean:
                _dprint_settings[before] = bool(re_true.match(after))
            elif before == 'level':
                _dprint_settings['level'] = int(level_map.get(after, after))
        except Exception as e:
            raise Exception('Error parsing line %s "%s"\n%s %s' % (line_number,
             line,
             type(e),
             str(e)))

    chains = []
    for section in sections:
        if section.startswith('filter '):
            chain = section.split(' ', 1)[1]
            filter_chain_create(chain, 'return')
            chains.append((section, chain))

    if 'filter' in sections:
        chains.append(('filter', 'ENTRY'))
    for section, chain in chains:
        for line_number, line, before, after in sections[section]:
            try:
                if before == 'policy':
                    filter_chain_policy(chain, after)
                else:
                    type_, before = before.split(' ', 1)
                    after, jump = get_arguments(after, (strip, strip), ' ')
                    if type_ == 'source':
                        file_, function, path = get_arguments(before, (strip, strip, strip), ',')
                        filter_add_by_source(chain, after, file=file_, function=function, path=path, jump=jump)
                    elif type_ == 'level':
                        conv = lambda x: not x.isdigit() and strip(x) or int(x)
                        exact, min_, max_ = get_arguments(before, (conv, conv, conv), ',')
                        filter_add_by_level(chain, after, exact=exact, min=min_, max=max_, jump=jump)
                    elif type_ == 'pattern':
                        filter_add_by_pattern(chain, after, before, jump=jump)
            except Exception as e:
                raise Exception('Error parsing line %s "%s"\n%s %s' % (line_number,
                 line,
                 type(e),
                 str(e)))


_config_read()

def dprint_wrap(func):
    source_file = inspect.getsourcefile(func)
    source_line = inspect.getsourcelines(func)[1]
    source_function = func.__name__

    def wrapper(*args, **kargs):
        dprint('PRE ', args, kargs, source_file=source_file, source_line=source_line, source_function=source_function)
        try:
            result = func(*args, **kargs)
        except Exception as e:
            dprint('POST', e, source_file=source_file, source_line=source_line, source_function=source_function)
            raise
        else:
            dprint('POST', result, source_file=source_file, source_line=source_line, source_function=source_function)
            return result

    return wrapper


def dprint_pre(func):
    source_file = inspect.getsourcefile(func)
    source_line = inspect.getsourcelines(func)[1]
    source_function = func.__name__

    def wrapper(*args, **kargs):
        dprint('PRE ', args, kargs, source_file=source_file, source_line=source_line, source_function=source_function)
        return func(*args, **kargs)

    return wrapper


def dprint_post(func):
    source_file = inspect.getsourcefile(func)
    source_line = inspect.getsourcelines(func)[1]
    source_function = func.__name__

    def wrapper(*args, **kargs):
        try:
            result = func(*args, **kargs)
            return result
        finally:
            dprint('POST', result, source_file=source_file, source_line=source_line, source_function=source_function)

    return wrapper


def dprint_wrap_object(object_, pattern = '^(?!__)'):
    re_pattern = re.compile(pattern)
    for name, member in inspect.getmembers(object_):
        if hasattr(member, '__call__') and re_pattern.match(name):
            try:
                setattr(object_, member.__name__, dprint_wrap(member))
            except:
                dprint('Failed wrapping', member, 'in object', object_)


def dprint(*args, **kargs):
    for key in kargs:
        if key not in _dprint_settings:
            raise ValueError('Unknown options: %s' % key)

    for key, value in _dprint_settings.items():
        if key not in kargs:
            kargs[key] = value

    callstack = extract_stack()[:kargs['stack_origin_modifier']]
    if callstack:
        if kargs['source_file'] is None:
            kargs['source_file'] = callstack[-1][0]
        if kargs['source_line'] is None:
            kargs['source_line'] = callstack[-1][1]
        if kargs['source_function'] is None:
            kargs['source_function'] = callstack[-1][2]
    else:
        if kargs['source_file'] is None:
            kargs['source_file'] = 'unknown'
        if kargs['source_line'] is None:
            kargs['source_line'] = 0
        if kargs['source_function'] is None:
            kargs['source_function'] = 'unknown'
    if kargs['level'] in level_map:
        kargs['level'] = level_map[kargs['level']]
    if kargs['level'] < LEVEL_ERROR and not _filter_check(args, kargs, _filter_entry):
        return
    if kargs['source_file'].endswith('.py'):
        short_source_file = join(basename(dirname(kargs['source_file'])), basename(kargs['source_file'][:-3]))
    else:
        short_source_file = join(basename(dirname(kargs['source_file'])), basename(kargs['source_file']))
    if kargs['style'] == 'short':
        prefix = '%s %s:%s %s ' % (level_tag_map.get(kargs['level'], 'U'),
         short_source_file,
         kargs['source_line'],
         kargs['source_function'])
    elif kargs['style'] == 'column':
        prefix = '%s %25s:%-4s %-25s | ' % (level_tag_map.get(kargs['level'], 'U'),
         short_source_file[-25:],
         kargs['source_line'],
         kargs['source_function'])
    else:
        raise ValueError('Invalid/unknown style: "%s"' % kargs['style'])
    messages = []
    if kargs['callback']:
        args = args + (kargs['callback'](),)
    if kargs['binary']:
        string = kargs['glue'].join([ str(v) for v in args ])
        messages.append(' '.join([ '%08d' % int(bin(ord(char))[2:]) for char in string ]))
    elif kargs['meta']:
        messages.extend([ dprint_format_variable(v) for v in args ])
    elif kargs['lines'] and len(args) == 1 and type(args[0]) in (list, tuple):
        messages.extend([ str(v) for v in args[0] ])
    elif kargs['lines'] and len(args) == 1 and type(args[0]) is dict:
        messages.extend([ '%s: %s' % (str(k), str(v)) for k, v in args[0].items() ])
    elif kargs['lines']:
        messages.extend([ str(v) for v in args ])
    else:
        messages.append(kargs['glue'].join([ str(v) for v in args ]))
    if kargs['line']:
        messages.insert(0, ''.join(kargs['line_char'] * kargs['line_width']))
    if kargs['box']:
        messages.insert(0, ''.join(kargs['box_char'] * kargs['box_width']))
        messages.append(''.join(kargs['box_char'] * kargs['box_width']))
    if kargs['stdout']:
        print >> stdout, prefix + ('\n' + prefix).join([ msg[:10000] for msg in messages ])
        if kargs['stack']:
            for line in format_list(callstack):
                print >> stdout, line,

        if kargs['exception']:
            print_exception(*exc_info(), **{'file': stdout})
    if kargs['stderr']:
        print >> stderr, prefix + ('\n' + prefix).join([ msg[:10000] for msg in messages ])
        if kargs['stack']:
            print_stack(file=stderr)
        if kargs['exception']:
            print_exception(*exc_info(), **{'file': stderr})
    if kargs['remote']:
        kargs['timestamp'] = time()
        kargs['callstack'] = callstack
        kargs['prefix'] = prefix
        kargs['thread_name'] = current_thread().name
        RemoteConnection.send(args, kargs)


def dprint_format_variable(v):
    return '%22s %s' % (type(v), str(v))


def strip_prefix(prefix, string):
    if string.startswith(prefix):
        return string[len(prefix):]
    else:
        return string
