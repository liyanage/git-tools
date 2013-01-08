#!/usr/bin/env python

"""
Introduction
============

githelper is both a module and a command line utility for working
with git_ working copies, especially git-svn ones where
``svn:externals`` references are mapped to nested git-svn working copies.

Maintained at https://github.com/liyanage/git-tools/tree/master/githelper

HTML version of this documentation at http://liyanage.github.com/git-tools/

.. _git: http://git-scm.com

Installation
============

You can install githelper directly from github like this::

    sudo curl -o /usr/local/bin/githelper.py -L https://github.com/liyanage/git-tools/raw/master/githelper/githelper.py
    sudo chmod 755 /usr/local/bin/githelper.py

Command Line Utility
====================

This documentation does not cover the command line utility usage
in detail because you can get that with the help option::

    githelper.py -h

The utility is subcommand-based, and each subcommand has its own options.
You can get a list of subcommands with the -h option shown above, and each
subcommand in turn supports the -h flag::

    githelper.py some_subcommand -h

You can extend the set of subcommands by writing plug-in classes. See
`Extending with Plug-In Classes`_ for details.

Command Line Utility Examples
-----------------------------

Below are some command line usage examples. The examples assume a
``gh`` shell alias for githelper::

    alias gh githelper.py

Start out by cloning an SVN repository with svn:externals as nested git working copies::

    $ gh cloneexternals https://svn.example.com/repo/project my-great-project
    ...
    $ cd my-great-project

To get an overview of the nested working copies, use the ``tree`` subcommand::

    $ gh tree
    |<Working copy /path/to/my-great-project>
    |--<Working copy /path/to/my-great-project/Foo *>
    |----<Working copy /path/to/my-great-project/Foo/subexternal>
    |--<Working copy /path/to/my-great-project/Bar>
    |--<Working copy /path/to/my-great-project/Baz>
    |--<Working copy /path/to/my-great-project/Subproject *>
    |----<Working copy /path/to/my-great-project/Subproject/ABC/Demo>
    |--<Working copy /path/to/my-great-project/Xyz>

(The * indicates a working copy with uncommited changes)

To get a combined git status view, use ``status``::

    $ gh status
    <Working copy /path/to/my-great-project/Foo *>
     M data.txt
    <Working copy /path/to/my-great-project/Subproject *>
     A xyz.dat

Only working copies that have any interesting status are listed.

To recursively update all git-svn sandboxes to the latest SVN state (i.e. perform a
``git svn rebase`` in all sub-working copies), use ``svnrebase``::

    $ gh svnrebase
    <Working copy /path/to/my-great-project/Foo>
        M	Widget/Foo/Foo.m
    r1234 = a7fca99445fa4518cdc47b008656359c1d8ce188 (refs/remotes/svn)
        M	Engine/Bar/Bar.m
    r1235 = d8faece12674ac8c670a15e10992c13876577834 (refs/remotes/svn)
    First, rewinding head to replay your work on top of it...
    Fast-forwarded master to refs/remotes/svn.

To check out a certain point in time in the past in all nested sandboxes, you could
use the ``each`` subcommand, which runs a shell command in each working copy:

    $ gh each "git checkout \$(git rev-list -n 1 --before='2012-01-01 00:00' master)"

These are just a few examples, see the command line help for the remaining subcommands.

Usage as Toolkit Module
=======================

If the utility does not provide what you need, you can write your own script
based on githelper as a module. The rest of this document explains the module's API.

The main entry point is the :py:class:`GitWorkingCopy` class. You instantiate it
with the path to a git or git-svn working copy (which possibly
has nested sub-working copies).

.. _iteration-example:

You can then traverse the tree of nested working copies by iterating over the
GitWorkingCopy instance::

    #!/usr/bin/env python

    import githelper
    import os
    import sys

    root_wc = githelper.GitWorkingCopy(sys.argv[1])

    for wc in root_wc:
        # Gets called once for root_wc and all sub-working copies.
        # Do something interesting with wc using its API here...

The :py:meth:`~GitWorkingCopy.traverse` method provides another way to do this,
it takes a callable, in the following example a function::

    def process_working_copy(wc):
        print wc.current_branch()

    root_wc = githelper.GitWorkingCopy(sys.argv[1])
    root_wc.traverse(process_working_copy)

Any callable object works, in the following example an instance of a class that implements :py:meth:`~object.__call__`::

    class Foo:

        def __init__(self, some_state):
            self.some_state = some_state

        def __call__(self, wc):
            # possibly use self.some_state
            print wc.current_branch()

    root_wc = githelper.GitWorkingCopy(sys.argv[1])
    iterator = Foo('bar')
    root_wc.traverse(iterator)

You can take a look at the various ``Subcommand...`` classes in the `module's
source code`_ to see examples of the API usage. These classes implement the various
subcommands provided by the command line utility front end and they exercise most of
the :py:class:`GitWorkingCopy` API.

.. _`module's source code`: https://github.com/liyanage/git-tools/blob/master/githelper/githelper.py

Extending with Plug-In Classes
==============================

To extend the command line utility with additional custom subcommands, create a
file called :file:`githelper_local.py` and store it somewhere in your :envvar:`PATH`.
The file must contain one class per subcommand. Each class name must start with
``Subcommand``, anything after that part is used as the actual subcommand name
that you pass on the command line to invoke it.

Here is an example :file:`githelper_local.py` with one subcommand named ``foo``::

    from githelper import AbstractSubcommand, GitWorkingCopy

    class SubcommandFoo(AbstractSubcommand):
        # The class-level doc comment is reused for the command-line usage help string.
        \"""Provide a useful description of this subcommand here\"""

        def __call__(self, wc):
            print wc
            return GitWorkingCopy.STOP_TRAVERSAL

        @classmethod
        def configure_argument_parser(cls, parser):
            # Add any command line options here. If you don't need any, just add a "pass" statement instead.
            parser.add_argument('-b', '--bar', help='Provide a useful description of this option here')

API Documentation
=================

"""

# autopep8 -i --ignore E501 githelper.py

import os
import re
import sys
import types
import select
import string
import argparse
import itertools
import subprocess
import contextlib
import collections
import xml.etree.ElementTree

class PopenOutputFilter:
    """
    Represents a set of inclusion/exclusion rules to filter the output of :py:class:`FilteringPopen`.
    You create instance of this class to pass to :py:meth:`FilteringPopen.run` (but see ``run()``'s
    ``filter_rules`` parameter for a convenience shortcut).

    There are two independent rule sets to filter stdout and stderr individually. If you don't
    supply the (optional) rule set for stderr, the (mandatory) one for stdout is reused.

    Rule sets are lists of lists of this form::

        rules = [
            ('-', r'^foo'),
            ('-', r'bar$'),
            ...
        ]

    Each rule is a two-element list where the first element is either the string "-" or "+"
    representing the actions for exclusion and inclusion, and the second element is a
    regular expression.

    Each line of stdout or stderr output is matched against each regular expression. If one
    of them matches, the line is filtered out if the action element is "-" or included if
    the action is "+". After the first rule matches, no further rules are evaluated.

    If no rule matches a given line, the line is included (not filtered out), i.e. there is
    an implicit last rule like this::

        ('+', '.*')

    In the example given above, all lines beginning with ``foo`` or ending with ``bar``
    are filtered out.

    In the following example, only lines containing foo or bar are included, everything else
    is filtered out::

        rules = [
            ('+', r'foo'),
            ('+', r'bar'),
            ('-', '.*')
        ]

    """

    def __init__(self, stdout_rules, stderr_rules=None):
        self.stdout_rules = self.compile_rules(stdout_rules)
        if stderr_rules is None:
            self.stderr_rules = self.stdout_rules
        else:
            self.stderr_rules = self.compile_rules(stderr_rules)

    def compile_rules(self, ruleset):
        if not ruleset:
            return None
        return [(action, re.compile(regex_string)) for action, regex_string in ruleset]

    def filtered_stdoutlines(self, lines):
        if not lines:
            return lines
        ruleset = self.stdout_rules
        return [line for line in lines if self.keep_line(line, ruleset)]

    def keep_stdoutline(self, line):
        return self.keep_line(line, self.stdout_rules)

    def keep_stderrline(self, line):
        return self.keep_line(line, self.stderr_rules)

    def filtered_stderrlines(self, lines):
        if not lines:
            return lines
        ruleset = self.stderr_rules
        return [line for line in lines if self.keep_line(line, ruleset)]

    def keep_line(self, line, ruleset):
        for rule in ruleset:
#            print '{0} {1} {2} {3}'.format(action, regex, regex.search(line), line)
            action, regex = rule
            if regex.search(line):
                if action == '+':
                    return True
                if action == '-':
                    return False
        return True


class FilteringPopen(object):
    """
    A wrapper around :py:class:`subprocess.Popen` that filters the subprocess's output.

    The constructor's parameters are forwarded mostly unchanged to :py:class:`Popen's constructor <subprocess.Popen>`.
    Exceptions are ``bufsize``, which is set to ``1`` for line-buffered output, and ``stdout``, and ``stderr``,
    which are both set to :py:data:`subprocess.PIPE`.

    This method sets up the Popen instance but does not run it. See :py:meth:`run` for that.

    """

    def __init__(self, *args, **kwargs):
        self.stdoutbuffer = []
        self.stderrbuffer = []
        self.cmd = args[0]
        self.wd = kwargs.get('cwd', None)

        kwargs['bufsize'] = 1;
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE

        self.popen = subprocess.Popen(*args, **kwargs)

    def run(self, filter=None, filter_rules=None, store_stdout=True, store_stderr=True, echo_stdout=True, echo_stderr=True, check_returncode=True, header=None):
        """
        Run the command and capture its (potentially filtered) output, similar to :py:meth:`subprocess.Popen.communicate`.

        :param githelper.PopenOutputFilter filter: An optional filter for stderr and stdout.
        :param array filter_rules: Instead of a :py:class:`PopenOutputFilter` instance, you can also pass a rule set directly.
        :param bool store_stdout: If ``False``, the command's output will not be stored for later retrieval. If set to ``True``, the output can be retrieved through the :py:meth:`stdoutlines` method after it has finished executing.
        :param bool store_stderr: If ``False``, the command's output will not be stored for later retrieval. If set to ``True``, the output can be retrieved through the :py:meth:`stderrlines` method after it has finished executing.
        :param bool echo_stdout: If ``False``, the command's output will not be printed to stdout.
        :param bool echo_stderr: If ``False``, the command's output will not be printed to stderr.
        :param bool check_returncode: If ``True``, the method raises an exception if the command terminates with a non-zero exit code.
        :param object header: This value will be printed to the console exactly once if the subcommand produces any output that does not get filtered out.
                              This is useful if you want to print something, but not if the command would not produce any output anyway.

        """
        self.filter = filter
        if filter and filter_rules:
            raise Exception("'filter' and 'filter_rules' can't be used together")
        if filter_rules:
            self.filter = PopenOutputFilter(filter_rules)

        self.header = header
        self.did_print_header = False

        self.store_stdout = store_stdout
        self.store_stderr = store_stderr
        self.echo_stdout = echo_stdout
        self.echo_stderr = echo_stderr

        returncode = None
        while returncode is None:
            self.check_pipes()
            returncode = self.popen.poll()
        self.check_pipes(0)

        if check_returncode and returncode:
            wd = self.wd if self.wd else os.getcwd()
            raise Exception('Non-zero exit status for shell command "{}" in {}'.format(self.cmd, self.wd))

    def check_pipes(self, timeout=1):
        ready_read_handles = select.select([self.popen.stdout, self.popen.stderr], (), (), timeout)[0]
        for handle in ready_read_handles:
            is_stdout = False
            is_stderr = False
            if handle == self.popen.stdout:
                is_stdout = True
            if handle == self.popen.stderr:
                is_stderr = True
            while True:
                line = handle.readline().rstrip('\n')
                if not line:
                    break
                if handle == self.popen.stdout:
                    if self.filter and not self.filter.keep_stdoutline(line):
                        continue
                    if self.store_stdout:
                        self.stdoutbuffer.append(line)
                    if self.echo_stdout:
                        self.print_header_once()
                        with ANSIColor.terminal_color(ANSIColor.blue, ANSIColor.blue):
                            print >> sys.stderr, line
                elif handle == self.popen.stderr:
                    if self.filter and not self.filter.keep_stderrline(line):
                        continue
                    if self.store_stderr:
                        self.stderrbuffer.append(line)
                    if self.echo_stderr:
                        self.print_header_once()
                        with ANSIColor.terminal_color(ANSIColor.blue, ANSIColor.blue):
                            print >> sys.stdout, line

    def print_header_once(self):
        if self.did_print_header or not self.header:
            return

        self.did_print_header = True
        print self.header

    def stdoutlines(self):
        """Returns an array of the stdout lines that were not filtered, with trailing newlines removed."""
        return self.stdoutbuffer

    def stderrlines(self):
        """Returns an array of the stderr lines that were not filtered, with trailing newlines removed."""
        return self.stderrbuffer

    def returncode(self):
        """
        Returns the command's exit code.

        :rtype: int

        """
        return self.popen.returncode


class ANSIColor(object):

    red = '1'
    green = '2'
    yellow = '3'
    blue = '4'

    @classmethod
    @contextlib.contextmanager
    def terminal_color(cls, stdout_color=None, stderr_color=red):

        if stdout_color:
            sys.stdout.write("\x1b[3{0}m".format(stdout_color))
        if stderr_color:
            sys.stderr.write("\x1b[3{0}m".format(stderr_color))

        try:
            yield
        except:
            cls.clear()
            raise

        cls.clear()

    @classmethod
    def clear(cls):
        for stream in [sys.stdout, sys.stderr]:
            stream.write("\x1b[m")


class GitWorkingCopy(object):
    """
    A class to represent a git or git-svn working copy.

    :param str path: The file system path to the working copy.
    :param githelper.GitWorkingCopy parent: A parent instance, you don't usually use this yourself.
    """

    STOP_TRAVERSAL = False
    """returned from a :py:meth:`~AbstractSubcommand.__call__` implementation to stop further recursion by :py:meth:`traverse`."""

    def __init__(self, path, parent=None):
        self.path = os.path.abspath(path)
        self._svn_info = None
        self._svn_externals = None
        self.parent = parent
        self.child_list = None

        status = subprocess.call('git status 1>/dev/null 2>/dev/null', shell=True, cwd=self.path)
        if status:
            raise Exception('{0} is not a git working copy'.format(self.path))

    def __str__(self):
        is_dirty = ''
        if self.is_dirty():
            is_dirty = ' *'

        return '<Working copy {0}{1}>'.format(self.path, is_dirty)

    def current_branch(self):
        """Returns the name of the current git branch."""
        output = self.output_for_git_command('git branch -a'.split())
        [branch] = [i[2:] for i in output if i.startswith('* ')]
        return branch

    def has_branch(self, branch_name):
        """Returns True if the working copy has a git branch with the given name"""
        return branch_name in self.branch_names()

    def branch_names(self):
        """Returns a list of git branch names."""
        output = self.output_for_git_command('git branch -a'.split())
        return [i[2:] for i in output]

    def remote_branch_names(self):
        """
        Returns a list of git branch names starting with ``remote/``.

        The leading ``remote/`` part will be removed.
        """
        return [i[8:] for i in self.branch_names() if i.startswith('remotes/')]

    def local_branch_names(self):
        """Returns a list of git branch names not starting with ``remote/``."""
        return [i for i in self.branch_names() if not i.startswith('remotes/')]

    def remote_branch_name_for_name_list(self, name_list):
        """
        Returns a remote branch name matching a list of candidate strings.

        Tries to find a remote branch names using all possible combinations
        of the names in the list. For example, given::

            ['foo', 'bar']

        as ``name_list``, it would find any of these::

            remotes/foo
            remotes/Foo
            remotes/bar
            remotes/Bar
            remotes/Foo-Bar
            remotes/foo-bar
            remotes/Bar-Foo
            remotes/bar-foo

        etc. and return the part after ``remotes/`` of the first match.

        """
        name_list = [i.lower() for i in name_list]
        candidates = set(name_list)
        candidates.update(['-'.join(i) for i in itertools.permutations(name_list)])

        for name in self.remote_branch_names():
            if name.lower() in candidates:
                return name

        return None

    def switch_to_branch(self, branch_name):
        """Checks out the given git branch"""
        if not self.has_branch(branch_name):
            raise Exception('{0} does not have a branch named {1}, cannot switch'.format(self, branch_name))

        self.run_shell_command(['git', 'checkout', branch_name])

    def hard_reset_current_branch(self, target):
        """Hard-resets the current branch to the given ref"""
        self.run_shell_command(['git', 'reset', '--hard', target])

    def run_shell_command(self, command, filter_rules=None, shell=None, header=None, check_returncode=True):
        """
        Runs the given shell command (array or string) in the receiver's working directory using :py:class:`FilteringPopen`.

        :param str command: Passed to :py:class:`FilteringPopen`'s constructor. Can also be an array.
        :param array filter_rules: Passed to :py:class:`FilteringPopen`'s constructor.
        :param bool shell: Passed to :py:class:`FilteringPopen`'s constructor.
        :param object header: Passed to :py:class:`FilteringPopen.run`.

        """
        if shell is None:
            if isinstance(command, types.StringTypes):
                shell = True
            else:
                shell = False

        popen = FilteringPopen(command, cwd=self.path, shell=shell)
        popen.run(filter_rules=filter_rules, store_stdout=False, store_stderr=False, header=header, check_returncode=check_returncode)

    def output_for_git_command(self, command, shell=False, filter_rules=None, header=None):
        """
        Runs the given shell command (array or string) in the receiver's working directory and returns the output.

        :param bool shell: If ``True``, runs the command through the shell. See the :py:mod:`subprocess` library module documentation for details.

        """
        popen = FilteringPopen(command, cwd=self.path, shell=shell)
        popen.run(filter_rules=filter_rules, echo_stdout=False, header=header)
        return popen.stdoutlines()

    def is_root(self):
        """Returns True if the receiver does not have a parent working copy."""
        return self.parent is None

    def ancestors(self):
        """
        Returns a list of parent working copies.

        If the receiver is the root working copy, this returns an empty list.

        """
        ancestors = []
        if not self.is_root():
            ancestors.append(self.parent)
            ancestors.extend(self.parent.ancestors())
        return ancestors

    def root_working_copy(self):
        """Returns the root working copy, which could be self."""
        if self.is_root():
            return self
        return self.parent.root_working_copy()

    def _check_output_in_path(self, command):
        try:
            return subprocess.check_output(command, cwd=self.path)
        except:
            print >> sys.stderr, 'Error running shell command in "{}":'.format(self.path)
            raise

    def svn_info(self, key=None):
        """
        Returns a dictionary containing the key/value pairs in the output of ``git svn info``.

        :param str key: When present, returns just the one value associated with the given key.

        """
        if not self._svn_info:
            output = self._check_output_in_path('git svn info'.split())
            self._svn_info = {}
            for match in re.finditer('^([^:]+): (.*)$', output, re.MULTILINE):
                self._svn_info[match.group(1)] = match.group(2)

        if key:
            return self._svn_info[key]
        else:
            return self._svn_info

    def svn_externals(self):
        """
        Returns a dictionary with the externals in the output of ``git svn show-externals``.
        """
        if not self._svn_externals:
            output = self._check_output_in_path('git svn show-externals'.split())
            self._svn_externals = {}
            for match in re.finditer('^/(\S+)\s+(\S+)[\t ]*$', output, re.MULTILINE):
                self._svn_externals[match.group(1)] = match.group(2)

        return self._svn_externals

    def svn_ignore_paths(self):
        """
        Returns a dictionary with the items in the output of ``git svn show-ignore``.
        """
        output = self._check_output_in_path('git svn show-ignore'.split())
        ignore_paths = []
        for match in re.finditer('^/(\S+)', output, re.MULTILINE):
            ignore_paths.append(match.group(1))
        return ignore_paths

    def is_dirty(self):
        """
        Returns True if the receiver's working copy has uncommitted modifications.

        Many operations depend on a clean state.

        """
        return bool(self.dirty_file_lines())

    def dirty_file_lines(self):
        """Returns the output of git status for the files marked as modified, renamed etc."""
        output = self._check_output_in_path('git status --porcelain'.split()).splitlines()
        dirty_file_lines = [line[3:].strip('"') for line in output if not line.startswith('?')]
        return dirty_file_lines

    def is_git_svn(self):
        """Returns True if the receiver's git working copy is a git-svn working copy."""
        status = subprocess.call('git svn info 1>/dev/null 2>/dev/null', shell=True, cwd=self.path)
        return not status

    def info(self):
        config_path = os.path.join(self.path, '.git/config')
        with open(config_path) as file:
            pass

        return self.basename()

    def basename(self):
        return os.path.basename(self.path)

    def children(self):
        if self.child_list is None:
            self.child_list = []
            for (dirpath, dirnames, filenames) in os.walk(self.path):
                if dirpath == self.path:
                    continue

                if not '.git' in dirnames:
                    continue

                del dirnames[:]

                wc = GitWorkingCopy(dirpath, parent=self)
                self.child_list.append(wc)

        return self.child_list

    def __iter__(self):
        """
        Returns an iterator over ``self`` and all of its nested git working copies.

        See the :ref:`example above <iteration-example>`.

        """
        yield self
        for child in self.children():
            for item in child:
                yield item

    def self_or_descendants_are_dirty(self, list_dirty=False):
        """
        Returns True if the receiver's or one of its nested working copies are dirty.

        :param bool list_dirty: If ``True``, prints the working copy path and the list of dirty files.

        """
        dirty_working_copies = []
        for item in self:
            if item.is_dirty():
                dirty_working_copies.append(item)

        if dirty_working_copies and list_dirty:
            print >> sys.stderr, 'Dirty working copies found, please commit or stash first:'
            for wc in dirty_working_copies:
                print >> sys.stderr, wc
                with ANSIColor.terminal_color(ANSIColor.red, ANSIColor.red):
                    print >> sys.stderr, ''.join([i + '\n' for i in wc.dirty_file_lines()])

        return bool(dirty_working_copies)

    def traverse(self, iterator):
        """
        Runs the given callable ``iterator`` on the receiver and all of its
        nested sub-working copies.

        Before each call to iterator for a given working copy, the current directory is first
        set to that working copy's path.

        See the :ref:`example above <iteration-example>`.
        """
        if callable(getattr(iterator, "prepare_for_root", None)):
            iterator.prepare_for_root(self)

        if not callable(iterator):
            raise Exception('{0} is not callable'.format(iterator))

        for item in self:
            with item.chdir_to_path():
                if iterator(item) is GitWorkingCopy.STOP_TRAVERSAL:
                    break

    @contextlib.contextmanager
    def chdir_to_path(self):
        """
        A :ref:`context manager <context-managers>` for the :py:keyword:`with` statement
        that temporarily switches the current working directory to the receiver's working
        copy directory::

            with wc.chdir_to_path():
                # do something useful here inside the working copy directory.

        """
        oldwd = os.getcwd()
        os.chdir(self.path)
        yield
        os.chdir(oldwd)

    @contextlib.contextmanager
    def switched_to_branch(self, branch_name):
        """
        A :ref:`context manager <context-managers>` for the :py:keyword:`with` statement
        that temporarily switches the current git branch to another one and afterwards
        restores the original one.

        Example::

            with wc.switched_to_branch('master'):
                # do something useful here on the 'master' branch.

        """
        old_branch = self.current_branch()
        different_branch = old_branch != branch_name
        if different_branch:
            print >> sys.stderr, 'Temporarily switching {0} from branch {1} to {2}'.format(self, old_branch, branch_name)
            self.switch_to_branch(branch_name)

        yield

        if different_branch:
            print >> sys.stderr, 'Switching {0} back to branch {1}'.format(self, old_branch)
            self.switch_to_branch(old_branch)


class AbstractSubcommand(object):
    """
    A base class for custom subcommand plug-in classes.

    You can, but don't have to, derive from this class for
    your custom subcommand extension classes. It also documents
    the interface you are expected to implement in your class
    and it provides some convenience methods.

    :param argparse.Namespace arguments: The command-line options passed to your subcommand
                                         in the form of a namespace instance as returned by
                                         :py:meth:`argparse.ArgumentParser.parse_args`.

    """

    def __init__(self, arguments):
        self.args = arguments

    def __call__(self, wc=None):
        """
        This gets called once per working copy to perform the subcommand's task.

        If you are only interested in the root-level working copy, you can stop
        the traversal by returning :py:data:`githelper.GitWorkingCopy.STOP_TRAVERSAL`.

        :param githelper.GitWorkingCopy wc: The working copy to process.

        """
        pass

    def check_preconditions(self, wc):
        """
        This method returns False if any of the working copies are dirty.

        You can call this as a first step in your :py:meth:`__call__` implementation
        and abort if your custom subcommand performs operations that require
        clean working copies.

        :param githelper.GitWorkingCopy wc: The working copy to check.

        """
        # perform this check only once at the root
        if not wc.is_root():
            return True

        return not wc.self_or_descendants_are_dirty(list_dirty=True)

    def prepare_for_root(self, root_wc):
        """
        This method gets called on the root working copy only and lets you
        perform preparation steps that you want to do only once for the entire
        tree.

        :param githelper.GitWorkingCopy wc: The working copy to check.

        """
        pass

    def check_for_git_svn_and_warn(self, wc):
        """
        This returns False and warns if the given working copy is not a git-svn working copy.

        :param githelper.GitWorkingCopy wc: The working copy to check.

        """
        if not wc.is_git_svn():
            print >> sys.stderr, '{0} is not git-svn, skipping'.format(wc)
            return False
        return True

    @classmethod
    def configure_argument_parser(cls, parser):
        """
        If you override this in your subclass, you can configure additional command line arguments
        for your subcommand's arguments parser.

        :param argparse.ArgumentParser parser: The argument parser that you can configure.

        """
        pass


    @classmethod
    def wants_working_copy(cls):
        """
        Return ``False`` to allow usage of your subcommand without a git working copy. The default is ``True``.
        """
        return True


class SubcommandResetMasterToSvnBranch(AbstractSubcommand):
    """Hard-reset the master branch of a working copy to a specific remote branch. Aborts if the working copy is dirty."""

    def __call__(self, wc):
        if not self.check_preconditions(wc):
            return GitWorkingCopy.STOP_TRAVERSAL

        if not self.check_for_git_svn_and_warn(wc):
            return

        if not wc.has_branch('master'):
            print >> sys.stderr, '{0} does not have a master branch, skipping'.format(wc)
            return

        branch_names = self.args.remote_branch_names

        target_remote_branch = wc.remote_branch_name_for_name_list(branch_names)
        if not target_remote_branch:
            print >> sys.stderr, 'No remote branch matches {0}, skipping {1}'.format(branch_names, wc)
            return

        with wc.switched_to_branch('master'):
            full_target_remote_branch = 'remotes/' + target_remote_branch
            print >> sys.stderr, 'Hard-resetting {0} to {1}'.format(wc, full_target_remote_branch)
            wc.hard_reset_current_branch(full_target_remote_branch)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('remote_branch_names', nargs='+', help='A list of one or more remote branch names. The tool will try to find a remote name using all combinations of the given items, ignoring case.')


class SubcommandSvnRebase(AbstractSubcommand):
    """Perform git svn rebase in each working copy. Temporarily switches to branch "master" if not already there. Aborts if the working copy is dirty."""

    def __call__(self, wc):
        if not self.check_preconditions(wc):
            return GitWorkingCopy.STOP_TRAVERSAL

        if not self.check_for_git_svn_and_warn(wc):
            return

        if not wc.has_branch('master'):
            print >> sys.stderr, '{0} does not have a master branch, skipping'.format(wc)
            return

        rules = (
            ('-', r'Current branch master is up to date'),
        )

        with wc.switched_to_branch('master'):
            wc.run_shell_command('git svn rebase', header=wc, filter_rules=rules)


class SubcommandTree(AbstractSubcommand):
    """List the tree of nested working copies"""

    def __call__(self, wc):
        print '|{0}{1}'.format(len(wc.ancestors()) * '--', wc)


class SubcommandStatus(AbstractSubcommand):
    """Run git status in each working copy"""

    def __call__(self, wc):
        rules = (
            ('-', r' On branch '),
            ('-', r'working directory clean'),
        )

        wc.run_shell_command('git status -s', filter_rules=rules, header=wc)


class SubcommandCheckout(AbstractSubcommand):
    """Check out a given branch if it exists"""

    def __call__(self, wc):
        if not self.check_preconditions(wc):
            return GitWorkingCopy.STOP_TRAVERSAL

        target_branch = self.args.branch
        current_branch = wc.current_branch()

        branch_candidates = [i for i in wc.local_branch_names() if target_branch in i]

        if not branch_candidates:
            print >> sys.stderr, 'No branch "{0}" in {1}, staying on "{2}"'.format(target_branch, wc, current_branch)
            return

        if len(branch_candidates) > 1:
            print >> sys.stderr, 'Branch name "{0}" is ambiguous in {1}, staying on "{2}":'.format(target_branch, wc, current_branch)
            print >> sys.stderr, [i + '\n' for i in branch_candidates]
            return

        target_branch = branch_candidates[0]

        if current_branch == target_branch:
            print >> sys.stderr, '{0} is already on branch "{1}"'.format(wc, target_branch)
            return

        wc.run_shell_command('git checkout {0}'.format(target_branch), header=wc)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('branch', help='The name of the branch that should be checked out')

class SubcommandBranch(AbstractSubcommand):
    """Show local and SVN branch of each working copy"""

    column_accessors = (
        lambda x: str(x),
        lambda x: os.path.basename(x.svn_info('URL')),
        lambda x: x.current_branch(),
    )

    def column_count(self):
        return len(SubcommandBranch.column_accessors)

    def prepare_for_root(self, root_wc):
        self.maxlen = [0] * self.column_count()
        for wc in root_wc:
            for index, accessor in enumerate(SubcommandBranch.column_accessors):
                self.maxlen[index] = max((self.maxlen[index], len(accessor(wc))))

    def __call__(self, wc):
        format = ' '.join(['{' + str(i) + '}' for i in range(self.column_count())])
        print format.format(*[string.ljust(SubcommandBranch.column_accessors[i](wc), self.maxlen[i]) for i in xrange(self.column_count())])


class SubcommandCloneExternals(AbstractSubcommand):
    """Clone an SVN repository and its ``svn:externals`` recursively."""

    def __call__(self):
        path = self.args.checkout_directory
        self.checkout_svn_url(self.args.checkout_directory, self.args.svn_url)

    def checkout_svn_url(self, path, svn_url):
        print 'Checking out "{0}" into "{1}"'.format(svn_url, path)

        if not os.path.exists(path):
            cmd = 'git svn clone -r HEAD'.split() + [svn_url, path]
            popen = FilteringPopen(cmd)
            popen.run()
        else:
            print '"{0}" already exists'.format(path)

        wc = GitWorkingCopy(path)
        print wc
        with wc.chdir_to_path():
            externals = wc.svn_externals()
 #           print externals
            self.update_exclude_file_with_paths(externals.keys() + wc.svn_ignore_paths())
            for directory, svn_url in externals.viewitems():
                self.checkout_svn_url(directory, svn_url)

    def update_exclude_file_with_paths(self, paths):
        lines_to_add = [path + '\n' for path in paths]
        excludefile_path = '.git/info/exclude'
        with open(excludefile_path, 'r+') as f:
            lines = f.readlines()
            lines_to_add = [line for line in lines_to_add if not line in lines]
            if not lines_to_add:
                return

#            print 'Adding "{0}" to "{1}"'.format(lines_to_add, os.path.abspath(excludefile_path))
            lines.extend(lines_to_add)
            f.seek(0)
            f.truncate()
            f.writelines(lines)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('svn_url', help='The toplevel SVN repository to clone')
        parser.add_argument('checkout_directory', help='The path to the sandbox directory to create')

    @classmethod
    def wants_working_copy(cls):
        return False


class SubcommandEach(AbstractSubcommand):
    """Run a shell command in each working copy"""

    def __call__(self, wc):
        command = ' '.join(self.args.shell_command)
        wc.run_shell_command(command, header=wc, check_returncode=False)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('shell_command', nargs='+', help='A shell command to execute in the context of each working copy. If you need to use options starting with -, add " -- " before the first one.')


class SubcommandSvnDiff(AbstractSubcommand):
    """Get a diff for a git-svn working copy that matches the corresponding svn diff"""

    def __call__(self, wc):
        if not self.check_for_git_svn_and_warn(wc):
            return GitWorkingCopy.STOP_TRAVERSAL

        svn_rev = wc.svn_info('Last Changed Rev')
        git_diff_command = 'git diff --no-prefix'.split() + self.args.git_diff_args
        git_diff = wc.output_for_git_command(git_diff_command)
        current_path = None
        output_lines = []
        for line in git_diff:
            output_line = line
            if line.startswith("diff --git "):
                current_path = re.search(r'diff --git (.+) \1', line).group(1)
            elif line.startswith('index'):
                output_line = 'Index {0}'.format(current_path)
            elif line.startswith('---'):
                output_line = '{0}\t(revision {1})'.format(line, svn_rev)
            elif line.startswith('+++'):
                output_line = '{0}\t(working copy)'.format(line)

            output_lines.append(output_line)

        output_string = ''.join([line + '\n' for line in output_lines])

        if self.args.copy and sys.platform == 'darwin':
            import AppKit
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.writeObjects_(AppKit.NSArray.arrayWithObject_(output_string))
        else:
            print output_string

        return GitWorkingCopy.STOP_TRAVERSAL

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('-c', '--copy', action='store_true', help='Copy the diff output to the OS X clipboard instead of printing it')
        parser.add_argument('git_diff_args', nargs='*', help='Optional arguments to git diff. If you need to pass options starting with -, add " -- " before the first one.')


# Some SVN-related subcommands that don't require a Git working copy

class SvnAbstractSubcommand(AbstractSubcommand):

    @classmethod
    def wants_working_copy(cls):
        return False


class SvnInfo(object):
    
    def __init__(self, xml_element):
        self.xml_element = xml_element
    
    def root(self):
        return self.xml_element.findtext('entry/repository/root')

    def url(self):
        return self.xml_element.findtext('entry/url')
    
    def revision(self):
        return self.xml_element.find('entry').get('revision')
    
    def last_changed_revision(self):
        return self.xml_element.find('entry/commit').get('revision')

    @classmethod
    def info_for_url_or_path(cls, svn_url_or_path):
        info = subprocess.check_output(['svn', 'info', '--xml', svn_url_or_path])
        tree = xml.etree.ElementTree.fromstring(info)
        return cls(tree)
        

SvnLocation = collections.namedtuple('SvnLocation', ['url', 'root', 'revision'])


class SvnLogEntry(object):
    
    def __init__(self, xml_element, svn_location):
        self.xml_element = xml_element
        self.location = svn_location
    
    def revision(self):
        return self.xml_element.get('revision')
    
    def timestamp(self):
        return self.xml_element.findtext('date')
    
    def date(self):
        return self.timestamp()[:10]
    
    def copyfrom_location(self):
        for path_element in [path for path in self.xml_element.findall('paths/path') if path.get('action') == 'A']:
            path = path_element.text
            if self.location.url.endswith(path):
                copyfrom_path = path_element.get('copyfrom-path')
                if copyfrom_path:
                    copyfrom_url = self.location.url.replace(path, copyfrom_path)
                    copyfrom_revision = path_element.get('copyfrom-rev')
                    return SvnLocation(copyfrom_url, self.location.root, copyfrom_revision)
        return None


class SvnLog(object):
    
    def __init__(self, svn_location, stop_on_copy=True):
        cmd = ['svn', 'log', '-v', '--xml']
        if stop_on_copy:
            cmd.append('--stop-on-copy')
        cmd.append(svn_location.url)
        
        log = subprocess.check_output(cmd)
        tree = xml.etree.ElementTree.fromstring(log)
        self.log_entries = []
        for entry_element in tree.findall('logentry'):
            entry = SvnLogEntry(entry_element, svn_location)
            self.log_entries.append(entry)
        
    def oldest_log_entry(self):
        return self.log_entries[-1]
    

class SubcommandSvnLineage(SvnAbstractSubcommand):
    """Show the branching history of an SVN branch."""

    def __call__(self):
        def callback(svn_location, log_entry):
            date = '{} '.format(log_entry.date()) if log_entry else 'HEAD       '
            print '{}{}@{}'.format(date, svn_location.url, svn_location.revision)
            sys.stdout.flush()
            
        self.location_list(self.leaf_svn_location(), callback)
    
    def location_list(self, svn_location, callback=None, log_entry=None):
        if callback:
            callback(svn_location, log_entry)
        try:
            log = SvnLog(svn_location)
            oldest_entry = log.oldest_log_entry()
            branch_location = oldest_entry.copyfrom_location()
            if branch_location:
                return self.location_list(branch_location, callback, oldest_entry) + [svn_location]
        except Exception as e:
            print e
            print 'Unable to follow log for SVN location "{}", it might not exist in the repository.'.format(svn_location.url)
            pass

        return [svn_location]
        
    def leaf_svn_location(self):

        svn_url = self.args.url_or_path
        if svn_url:
            info = SvnInfo.info_for_url_or_path(svn_url)
            return SvnLocation(info.url(), info.root(), info.revision())
        
        if os.path.exists('.svn'):
            info = SvnInfo.info_for_url_or_path('.')
            return SvnLocation(info.url(), info.root(), info.revision())
        
        if os.path.exists('.git/svn'):
            wc = GitWorkingCopy('.')
            return SvnLocation(wc.svn_info('URL'), wc.svn_info('Repository Root'), wc.svn_info('Last Changed Rev'))

        raise Exception('No SVN URL given and current directory is neither SVN nor Git root working copy')

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('url_or_path', nargs='?', help='The SVN URL. If not given, the script tries to get it from the current directory, which can be either a git-svn or an SVN working copy.')


class SubcommandSvnConflicts(SvnAbstractSubcommand):
    """Show the conflicted files of svn status."""

    def __call__(self):
        output = subprocess.check_output('svn status'.split())
        for line in output.splitlines():
            if re.match('(?:..... [C>] |C)', line):
                print line


class SubcommandSvnDeleteResolve(SvnAbstractSubcommand):
    """Svn-rm and -resolve one or more tree-conflicted files."""

    def __call__(self):
        for path in self.args.path:
            if os.path.exists(path):
                print subprocess.check_output('svn rm --force'.split() + [path]),
            print subprocess.check_output('svn resolve --accept working'.split() + [path]),

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('path', nargs='+', help='The path of the tree-conflicted file to remove and resolve.')


class GitHelperCommandLineDriver(object):

    @classmethod
    def subcommand_map(cls):
        sys.path.extend(os.environ['PATH'].split(':'))
        githelper_local = None
        try:
            import githelper_local
        except ImportError:
            pass
        except Exception as e:
            print >> sys.stderr, 'Unable to import githelper_local extension module:'
            raise

        namespaces = globals()
        subcommand_map = {}
        if githelper_local:
            namespaces.update({k : getattr(githelper_local, k) for k in dir(githelper_local)})

        for k, v in namespaces.items():
            if not k.startswith('Subcommand'):
                continue
            name_components = [i.lower() for i in re.findall(r'([A-Z][a-z]+)', k)[1:]]
            subcommand_name = '-'.join(name_components)
            subcommand_map[subcommand_name] = v

        return subcommand_map

    @classmethod
    def run(cls):
        subcommand_map = cls.subcommand_map()

        parser = argparse.ArgumentParser(description='Git-SVN helper')
        parser.add_argument('--root_path', help='Path to root working copy', default=os.getcwd())
        subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand_name')
        for subcommand_name, subcommand_class in subcommand_map.items():
            subparser = subparsers.add_parser(subcommand_name, help=subcommand_class.__doc__)
            subcommand_class.configure_argument_parser(subparser)

        args = parser.parse_args()

        subcommand_class = subcommand_map[args.subcommand_name]
        subcommand = subcommand_class(args)

        if subcommand_class.wants_working_copy():
            wc = GitWorkingCopy(args.root_path)
            wc.traverse(subcommand)
        else:
            subcommand()

if __name__ == "__main__":
    GitHelperCommandLineDriver.run()
