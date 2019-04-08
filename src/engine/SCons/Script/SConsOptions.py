#
# __COPYRIGHT__
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

__revision__ = "__FILE__ __REVISION__ __DATE__ __DEVELOPER__"

import argparse
import optparse
import re
import sys
import textwrap

no_hyphen_re = re.compile(r'(\s+|(?<=[\w\!\"\'\&\.\,\?])-{2,}(?=\w))')

try:
    from gettext import gettext
except ImportError:
    def gettext(message):
        return message
_ = gettext

import SCons.Node.FS
import SCons.Platform.virtualenv
import SCons.Warnings

from argparse import ArgumentError, SUPPRESS

diskcheck_all = SCons.Node.FS.diskcheck_types()

def diskcheck_convert(value):
    if value is None:
        return []
    if not SCons.Util.is_List(value):
        value = value.split(',')
    result = []
    for v in value:
        v = v.lower()
        if v == 'all':
            result = diskcheck_all
        elif v == 'none':
            result = []
        elif v in diskcheck_all:
            result.append(v)
        else:
            raise ValueError(v)
    return result


class SConsValues(argparse.Namespace):
    """
    Holder class for uniform access to SCons options, regardless
    of whether or not they can be set on the command line or in the
    SConscript files (using the SetOption() function).

    A SCons option value can originate three different ways:

        1)  set on the command line;
        2)  set in an SConscript file;
        3)  the default setting (from the the op.add_option()
            calls in the Parser() function, below).

    The command line always overrides a value set in a SConscript file,
    which in turn always overrides default settings.  Because we want
    to support user-specified options in the SConscript file itself,
    though, we may not know about all of the options when the command
    line is first parsed, so we can't make all the necessary precedence
    decisions at the time the option is configured.

    The solution implemented in this class is to keep these different sets
    of settings separate (command line, SConscript file, and default)
    and to override the __getattr__() method to check them in turn.
    This should allow the rest of the code to just fetch values as
    attributes of an instance of this class, without having to worry
    about where they came from.

    Note that not all command line options are settable from SConscript
    files, and the ones that are must be explicitly added to the
    "settable" list in this class, and optionally validated and coerced
    in the set_option() method.
    """

    def __init__(self, defaults):
        self.__dict__['__defaults__'] = defaults
        self.__dict__['__SConscript_settings__'] = {}

    def __getattr__(self, attr):
        """
        Fetches an options value, checking first for explicit settings
        from the command line (which are direct attributes), then the
        SConscript file settings, then the default values.
        """
        try:
            return self.__dict__[attr]
        except KeyError:
            try:
                return self.__dict__['__SConscript_settings__'][attr]
            except KeyError:
                try:
                    return getattr(self.__dict__['__defaults__'], attr)
                except KeyError:
                    # Added because with py3 this is a new class,
                    # not a classic class, and due to the way
                    # In that case it will create an object without
                    # __defaults__, and then query for __setstate__
                    # which will throw an exception of KeyError
                    # deepcopy() is expecting AttributeError if __setstate__
                    # is not available.
                    raise AttributeError(attr)


    settable = [
        'clean',
        'diskcheck',
        'duplicate',
        'help',
        'implicit_cache',
        'max_drift',
        'md5_chunksize',
        'no_exec',
        'num_jobs',
        'random',
        'stack_size',
        'warn',
        'silent'
    ]

    def set_option(self, name, value):
        """
        Sets an option from an SConscript file.
        """
        if not name in self.settable:
            raise SCons.Errors.UserError("This option is not settable from a SConscript file: %s"%name)

        if name == 'num_jobs':
            try:
                value = int(value)
                if value < 1:
                    raise ValueError
            except ValueError:
                raise SCons.Errors.UserError("A positive integer is required: %s"%repr(value))
        elif name == 'max_drift':
            try:
                value = int(value)
            except ValueError:
                raise SCons.Errors.UserError("An integer is required: %s"%repr(value))
        elif name == 'duplicate':
            try:
                value = str(value)
            except ValueError:
                raise SCons.Errors.UserError("A string is required: %s"%repr(value))
            if not value in SCons.Node.FS.Valid_Duplicates:
                raise SCons.Errors.UserError("Not a valid duplication style: %s" % value)
            # Set the duplicate style right away so it can affect linking
            # of SConscript files.
            SCons.Node.FS.set_duplicate(value)
        elif name == 'diskcheck':
            try:
                value = diskcheck_convert(value)
            except ValueError as v:
                raise SCons.Errors.UserError("Not a valid diskcheck value: %s"%v)
            if 'diskcheck' not in self.__dict__:
                # No --diskcheck= option was specified on the command line.
                # Set this right away so it can affect the rest of the
                # file/Node lookups while processing the SConscript files.
                SCons.Node.FS.set_diskcheck(value)
        elif name == 'stack_size':
            try:
                value = int(value)
            except ValueError:
                raise SCons.Errors.UserError("An integer is required: %s"%repr(value))
        elif name == 'md5_chunksize':
            try:
                value = int(value)
            except ValueError:
                raise SCons.Errors.UserError("An integer is required: %s"%repr(value))
        elif name == 'warn':
            if SCons.Util.is_String(value):
                value = [value]
            value = self.__SConscript_settings__.get(name, []) + value
            SCons.Warnings.process_warn_strings(value)

        self.__SConscript_settings__[name] = value


class SConsOption(optparse.Option):
    def convert_value(self, opt, value):
        if value is not None:
            if self.nargs in (1, '?'):
                return self.check_value(opt, value)
            else:
                return tuple([self.check_value(opt, v) for v in value])

    def process(self, opt, value, values, parser):

        # First, convert the value(s) to the right type.  Howl if any
        # value(s) are bogus.
        value = self.convert_value(opt, value)

        # And then take whatever action is expected of us.
        # This is a separate method to make life easier for
        # subclasses to add new actions.
        return self.take_action(
            self.action, self.dest, opt, value, values, parser)

    def _check_nargs_optional(self):
        if self.nargs == '?' and self._short_opts:
            fmt = "option %s: nargs='?' is incompatible with short options"
            raise SCons.Errors.UserError(fmt % self._short_opts[0])

    try:
        _orig_CONST_ACTIONS = optparse.Option.CONST_ACTIONS

        _orig_CHECK_METHODS = optparse.Option.CHECK_METHODS

    except AttributeError:
        # optparse.Option had no CONST_ACTIONS before Python 2.5.

        _orig_CONST_ACTIONS = ("store_const",)

        def _check_const(self):
            if self.action not in self.CONST_ACTIONS and self.const is not None:
                raise OptionError(
                    "'const' must not be supplied for action %r" % self.action,
                    self)

        # optparse.Option collects its list of unbound check functions
        # up front.  This sucks because it means we can't just override
        # the _check_const() function like a normal method, we have to
        # actually replace it in the list.  This seems to be the most
        # straightforward way to do that.

        _orig_CHECK_METHODS = [optparse.Option._check_action,
                     optparse.Option._check_type,
                     optparse.Option._check_choice,
                     optparse.Option._check_dest,
                     _check_const,
                     optparse.Option._check_nargs,
                     optparse.Option._check_callback]

    CHECK_METHODS = _orig_CHECK_METHODS + [_check_nargs_optional]

    CONST_ACTIONS = _orig_CONST_ACTIONS + optparse.Option.TYPED_ACTIONS

class SConsOptionGroup(optparse.OptionGroup):
    """
    A subclass for SCons-specific option groups.

    The only difference between this and the base class is that we print
    the group's help text flush left, underneath their own title but
    lined up with the normal "SCons Options".
    """
    def format_help(self, formatter):
        """
        Format an option group's help text, outdenting the title so it's
        flush with the "SCons Options" title we print at the top.
        """
        formatter.dedent()
        result = formatter.format_heading(self.title)
        formatter.indent()
        result = result + optparse.OptionContainer.format_help(self, formatter)
        return result

class SConsOptionParser(argparse.ArgumentParser):
    """
    A subclass for SCons-specific option parsing.

    SCons options are either set by the core script or the user and we
    want to abstract away the lower level details of the actual parser.
    Historically, SCons had to extend :class:`optparse.OptionParser` in
    order to handle complex parsing.  The new way is to use the
    :class:`argparse.ArgumentParser`, because it already handles the
    advanced option parsing.  However, we want to change as little about
    the parser as possible.
    """
    preserve_unknown_options = False

    def __init__(self, *args, **kwargs):
        super(SConsOptionParser, self).__init__(*args, **kwargs)
        self.values = SConsValues(argparse.Namespace)
        self.largs = None
        self.local_option_group = None

    def parse_args(self, args=None, namespace=None):
        f = super(SConsOptionParser, self).parse_args
        values = f(args, namespace if namespace else self.values)
        if values is not self.values:
            self.values = SConsValues(values)
        return self.values

    def parse_known_args(self, args=None, namespace=None):
        f = super(SConsOptionParser, self).parse_known_args
        values, self.largs = f(args if args else self.largs,
                               namespace if namespace else self.values)
        if values is not self.values:
            self.values = SConsValues(values)
        return self.values, self.largs

    def get_default_values(self):
        self.parse_known_args()
        return self.values

    def error(self, message):
        # overridden ArgumentParser exception handler
        self.print_usage(sys.stderr)
        sys.stderr.write("SCons Error: %s\n" % message)
        sys.exit(2)

    def add_local_option(self, *args, **kw):
        """
        Adds a local option to the parser.

        This is initiated by a SetOption() call to add a user-defined
        command-line option.  We add the option to a separate option
        group for the local options, creating the group if necessary.
        """
        if self.local_option_group is None:
            group = self.add_argument_group('Local Options')
            self.local_option_group = group
        else:
            group = self.local_option_group

        result = group.add_argument(*args, **kw)

        if result:
            # The option was added successfully.  We now have to add the
            # default value to our object that holds the default values
            # (so that an attempt to fetch the option's attribute will
            # yield the default value when not overridden) and then
            # we re-parse the leftover command-line options, so that
            # any value overridden on the command line is immediately
            # available if the user turns around and does a GetOption()
            # right away.
            setattr(self.values.__defaults__, result.dest, result.default)
            self.parse_known_args(self.largs, self.values)

        return result

def Parser(version):
    """
    Returns an options parser object initialized with the standard
    SCons options.
    """

    formatter = lambda prog: argparse.HelpFormatter(prog, max_help_position=30)

    op = SConsOptionParser(allow_abbrev=False,
                           add_help=False,
                           formatter_class=formatter,
                           usage="scons [OPTION] [TARGET] ...",)

    op.preserve_unknown_options = True
    op.add_argument("-v", "--version", action="version", version=version)

    # Add the options to the parser we just created.
    #
    # These are in the order we want them to show up in the -H help
    # text, basically alphabetical.  Each op.add_option() call below
    # should have a consistent format:
    #
    #   op.add_option("-L", "--long-option-name",
    #                 nargs=1, type="string",
    #                 dest="long_option_name", default='foo',
    #                 action="callback", callback=opt_long_option,
    #                 help="help text goes here",
    #                 metavar="VAR")
    #
    # Even though the optparse module constructs reasonable default
    # destination names from the long option names, we're going to be
    # explicit about each one for easier readability and so this code
    # will at least show up when grepping the source for option attribute
    # names, or otherwise browsing the source code.

    # options ignored for compatibility
    class SConsIgnore(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            sys.stderr.write("Warning:  ignoring {0} option\n".format(option_string))

    op.add_argument("-b", "-d", "-e", "-m", "-S", "-t", "-w",
                    "--environment-overrides",
                    "--no-keep-going",
                    "--no-print-directory",
                    "--print-directory",
                    "--stop",
                    "--touch",
                    action=SConsIgnore,
                    nargs=0,
                    help="Ignored for compatibility.")

    op.add_argument('-c', '--clean', '--remove',
                    dest="clean", default=False,
                    action="store_true",
                    help="Remove specified targets and dependencies.")

    op.add_argument('-C', '--directory',
                    nargs=1, type=str,
                    dest="directory", default=[],
                    action="append",
                    help="Change to DIR before doing anything.",
                    metavar="DIR")

    op.add_argument('--cache-debug',
                    nargs=1,
                    dest="cache_debug", default=None,
                    action="store",
                    help="Print CacheDir debug info to FILE.",
                    metavar="FILE")

    op.add_argument('--cache-disable', '--no-cache',
                    dest='cache_disable', default=False,
                    action="store_true",
                    help="Do not retrieve built targets from CacheDir.")

    op.add_argument('--cache-force', '--cache-populate',
                    dest='cache_force', default=False,
                    action="store_true",
                    help="Copy already-built targets into the CacheDir.")

    op.add_argument('--cache-readonly',
                    dest='cache_readonly', default=False,
                    action="store_true",
                    help="Do not update CacheDir with built targets.")

    op.add_argument('--cache-show',
                    dest='cache_show', default=False,
                    action="store_true",
                    help="Print build actions for files from CacheDir.")

    def opt_invalid(group, value, options):
        errmsg = "`{0}' is not a valid {1} option type, try:\n".format(value, group)
        return errmsg + "    {0}".format(", ".join(options))

    config_options = ["auto", "force", "cache"]

    opt_config_help = "Controls Configure subsystem: {0}.".format(
                      ", ".join(config_options))

    op.add_argument('--config',
                    nargs=1, choices=config_options,
                    dest="config", default="auto",
                    help=opt_config_help,
                    metavar="MODE")

    op.add_argument('-D',
                    dest="climb_up", default=None,
                    action="store_const", const=2,
                    help="Search up directory tree for SConstruct,       "
                         "build all Default() targets.")

    deprecated_debug_options = {
        "dtree"         : '; please use --tree=derived instead',
        "nomemoizer"    : ' and has no effect',
        "stree"         : '; please use --tree=all,status instead',
        "tree"          : '; please use --tree=all instead',
    }

    debug_options = ["count", "duplicate", "explain", "findlibs",
                     "includes", "memoizer", "memory", "objects",
                     "pdb", "prepare", "presub", "stacktrace",
                     "time"]

    class SConsDebug(argparse.Action):
        def __call__(self, parser, namespace, value__, option_string=None,
                     debug_options=debug_options,
                     deprecated_debug_options=deprecated_debug_options):
            for value in [v for vs in value__ for v in vs.split(',')]:
                if value in debug_options:
                    try:
                        namespace.debug.append(value)
                    except AttributeError:
                        setattr(namespace, "debug", [value])
                elif value in list(deprecated_debug_options.keys()):
                    try:
                        namespace.debug.append(value)
                    except AttributeError:
                        setattr(namespace, "debug", [value])
                    try:
                        namespace.delayed_warnings
                    except AttributeError:
                        setattr(namespace, "delayed_warnings", [])
                    msg = deprecated_debug_options[value]
                    w = "The --debug={0} option is deprecated{1}.".format(value, msg)
                    t = (SCons.Warnings.DeprecatedDebugOptionsWarning, w)
                    namespace.delayed_warnings.append(t)
                else:
                    raise ArgumentError(value, opt_invalid('debug', value, debug_options))

    opt_debug_help = "Print various types of debugging information: {0}.".format(
                     ", ".join(debug_options))
    op.add_argument('--debug',
                    nargs=1, type=str,
                    dest="debug", default=[],
                    action=SConsDebug,
                    help=opt_debug_help,
                    metavar="TYPE")

    class SConsDiskcheck(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            try:
                diskcheck_value = diskcheck_convert(value)
            except ValueError as e:
                raise ArgumentError(value, "`{0}' is not a valid diskcheck type".format(e))
            setattr(namespace, namespace.dest, diskcheck_value)

    op.add_argument('--diskcheck',
                    nargs=1, type=str,
                    dest='diskcheck', default=None,
                    action=SConsDiskcheck,
                    help="Enable specific on-disk checks.",
                    metavar="TYPE")

    class SConsDuplicate(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            if not value in SCons.Node.FS.Valid_Duplicates:
                raise ArgumentError(value, opt_invalid('duplication', value,
                                                SCons.Node.FS.Valid_Duplicates))
            setattr(namespace, namespace.dest, value)
            # Set the duplicate style right away so it can affect linking
            # of SConscript files.
            SCons.Node.FS.set_duplicate(value)

    opt_duplicate_help = "Set the preferred duplication methods. Must be one of " \
                         + ", ".join(SCons.Node.FS.Valid_Duplicates)

    op.add_argument('--duplicate',
                    nargs=1, type=str,
                    dest="duplicate", default='hard-soft-copy',
                    action=SConsDuplicate,
                    help=opt_duplicate_help)

    if not SCons.Platform.virtualenv.virtualenv_enabled_by_default:
        op.add_argument('--enable-virtualenv',
                        dest="enable_virtualenv",
                        action="store_true",
                        help="Import certain virtualenv variables to SCons")

    op.add_argument('-f', '--file', '--makefile', '--sconstruct',
                    nargs=1, type=str,
                    dest="file", default=[],
                    action="append",
                    help="Read FILE as the top-level SConstruct file.")

    op.add_argument('-h', '--help',
                    dest="help", default=False,
                    action="store_true",
                    help="Print defined help message, or this one.")

    op.add_argument("-H", "--help-options",
                    action="help",
                    help="Print this message and exit.")

    op.add_argument('-i', '--ignore-errors',
                    dest='ignore_errors', default=False,
                    action="store_true",
                    help="Ignore errors from build actions.")

    op.add_argument('-I', '--include-dir',
                    nargs=1,
                    dest='include_dir', default=[],
                    action="append",
                    help="Search DIR for imported Python modules.",
                    metavar="DIR")

    op.add_argument('--ignore-virtualenv',
                   dest="ignore_virtualenv",
                   action="store_true",
                   help="Do not import virtualenv variables to SCons")

    op.add_argument('--implicit-cache',
                    dest='implicit_cache', default=False,
                    action="store_true",
                    help="Cache implicit dependencies")

    class SConsImplicitDeps(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            setattr(namespace, 'implicit_cache', True)
            setattr(namespace, namespace.dest, True)

    op.add_argument('--implicit-deps-changed',
                    dest="implicit_deps_changed", default=False,
                    action=SConsImplicitDeps,
                    help="Ignore cached implicit dependencies.")

    op.add_argument('--implicit-deps-unchanged',
                    dest="implicit_deps_unchanged", default=False,
                    action=SConsImplicitDeps,
                    help="Ignore changes in implicit dependencies.")

    op.add_argument('--interact', '--interactive',
                    dest='interactive', default=False,
                    action="store_true",
                    help="Run in interactive mode.")

    op.add_argument('-j', '--jobs',
                    nargs=1, type=int,
                    dest="num_jobs", default=1,
                    action="store",
                    help="Allow N jobs at once.",
                    metavar="N")

    op.add_argument('-k', '--keep-going',
                    dest='keep_going', default=False,
                    action="store_true",
                    help="Keep going when a target can't be made.")

    op.add_argument('--max-drift',
                    nargs=1, type=int,
                    dest='max_drift', default=SCons.Node.FS.default_max_drift,
                    action="store",
                    help="Set maximum system clock drift to N seconds.",
                    metavar="N")

    op.add_argument('--md5-chunksize',
                    nargs=1, type=int,
                    dest='md5_chunksize', default=SCons.Node.FS.File.md5_chunksize,
                    action="store",
                    help="Set chunk-size for MD5 signature computation to N kilobytes.",
                    metavar="N")

    op.add_argument('-n', '--no-exec', '--just-print', '--dry-run', '--recon',
                    dest='no_exec', default=False,
                    action="store_true",
                    help="Don't build; just print commands.")

    op.add_argument('--no-site-dir',
                    dest='no_site_dir', default=False,
                    action="store_true",
                    help="Don't search or use the usual site_scons dir.")

    op.add_argument('--profile',
                    nargs=1,
                    dest="profile_file", default=None,
                    action="store",
                    help="Profile SCons and put results in FILE.",
                    metavar="FILE")

    op.add_argument('-q', '--question',
                    dest="question", default=False,
                    action="store_true",
                    help="Don't build; exit status says if up to date.")

    op.add_argument('-Q',
                    dest='no_progress', default=False,
                    action="store_true",
                    help="Suppress \"Reading/Building\" progress messages.")

    op.add_argument('--random',
                    dest="random", default=False,
                    action="store_true",
                    help="Build dependencies in random order.")

    op.add_argument('-s', '--silent', '--quiet',
                    dest="silent", default=False,
                    action="store_true",
                    help="Don't print commands.")

    op.add_argument('--site-dir',
                    nargs=1,
                    dest='site_dir', default=None,
                    action="store",
                    help="Use DIR instead of the usual site_scons dir.",
                    metavar="DIR")

    op.add_argument('--stack-size',
                    nargs=1, type=int,
                    dest='stack_size',
                    action="store",
                    help="Set the stack size of the threads used to run jobs to N kilobytes.",
                    metavar="N")

    op.add_argument('--taskmastertrace',
                    nargs=1,
                    dest="taskmastertrace_file", default=None,
                    action="store",
                    help="Trace Node evaluation to FILE.",
                    metavar="FILE")

    tree_options = ["all", "derived", "prune", "status"]

    class SConsTree(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None,
                     tree_options=tree_options):
            from . import Main
            tp = Main.TreePrinter()
            for o in value.split(','):
                if o == 'all':
                    tp.derived = False
                elif o == 'derived':
                    tp.derived = True
                elif o == 'prune':
                    tp.prune = True
                elif o == 'status':
                    tp.status = True
                else:
                    raise ArgumentError(o, opt_invalid('--tree', o, tree_options))
            try:
                namespace.tree_printers.append(tp)
            except AttributeError:
                setattr(namespace, "tree_printers", [tp])

    opt_tree_help = "Print a dependency tree in various formats: {0}.".format(
                    ", ".join(tree_options))

    op.add_argument('--tree',
                    nargs=1, type=str,
                    dest="tree_printers", default=[],
                    action=SConsTree,
                    help=opt_tree_help,
                    metavar="OPTIONS")

    op.add_argument('-u', '--up', '--search-up',
                    dest="climb_up", default=0,
                    action="store_const", const=1,
                    help="Search up directory tree for SConstruct,       "
                         "build targets at or below current directory.")

    op.add_argument('-U',
                    dest="climb_up", default=0,
                    action="store_const", const=3,
                    help="Search up directory tree for SConstruct,       "
                         "build Default() targets from local SConscript.")

    class SConsWarn(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None,
                     tree_options=tree_options):
            if SCons.Util.is_String(value):
                value = value.split(',')
            try:
                namespace.warn.extend(value)
            except AttributeError:
                setattr(namespace, "warn", value)

    op.add_argument('--warn', '--warning',
                    nargs=1, type=str,
                    dest="warn", default=[],
                    action=SConsWarn,
                    help="Enable or disable warnings.",
                    metavar="WARNING-SPEC")

    op.add_argument('-Y', '--repository', '--srcdir',
                    nargs=1,
                    dest="repository", default=[],
                    action="append",
                    help="Search REPOSITORY for source and target files.")


    # Options from Make and Cons classic that we do not yet support,
    # but which we may support someday and whose (potential) meanings
    # we don't want to change.  These all get a "the -X option is not
    # yet implemented" message and don't show up in the help output.

    class SConsNotYet(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            msg = "Warning:  the {0} option is not yet implemented\n".format(option_string)
            sys.stderr.write(msg)

    op.add_argument('-l', '--load-average', '--max-load',
                    nargs=1, type=float,
                    dest="load_average", default=0,
                    action=SConsNotYet,
                    # action="store",
                    # help="Don't start multiple jobs unless load is below "
                    #      "LOAD-AVERAGE."
                    help=SUPPRESS)
    op.add_argument('--list-actions',
                    dest="list_actions",
                    action=SConsNotYet,
                    # help="Don't build; list files and build actions."
                    help=SUPPRESS)
    op.add_argument('--list-derived',
                    dest="list_derived",
                    action=SConsNotYet,
                    # help="Don't build; list files that would be built."
                    help=SUPPRESS)
    op.add_argument('--list-where',
                    dest="list_where",
                    action=SConsNotYet,
                    # help="Don't build; list files and where defined."
                    help=SUPPRESS)
    op.add_argument('-o', '--old-file', '--assume-old',
                    nargs=1, type=str,
                    dest="old_file", default=[],
                    action=SConsNotYet,
                    # action="append",
                    # help = "Consider FILE to be old; don't rebuild it."
                    help=SUPPRESS)
    op.add_argument('--override',
                    nargs=1, type=str,
                    action=SConsNotYet,
                    dest="override",
                    # help="Override variables as specified in FILE."
                    help=SUPPRESS)
    op.add_argument('-p',
                    action=SConsNotYet,
                    dest="p",
                    # help="Print internal environments/objects."
                    help=SUPPRESS)
    op.add_argument('-r', '-R', '--no-builtin-rules', '--no-builtin-variables',
                    action=SConsNotYet,
                    dest="no_builtin_rules",
                    # help="Clear default environments and variables."
                    help=SUPPRESS)
    op.add_argument('--write-filenames',
                    nargs=1, type=str,
                    dest="write_filenames",
                    action=SConsNotYet,
                    # help="Write all filenames examined into FILE."
                    help=SUPPRESS)
    op.add_argument('-W', '--new-file', '--assume-new', '--what-if',
                    nargs=1, type=str,
                    dest="new_file",
                    action=SConsNotYet,
                    # help="Consider FILE to be changed."
                    help=SUPPRESS)
    op.add_argument('--warn-undefined-variables',
                    dest="warn_undefined_variables",
                    action=SConsNotYet,
                    # help="Warn when an undefined variable is referenced."
                    help=SUPPRESS)
    return op

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
