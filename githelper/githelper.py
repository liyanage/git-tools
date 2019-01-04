#!/usr/bin/env python
# coding=utf-8

"""
Introduction
============

Githelper is both a module and a command line utility for working with git_ working copies.

It is maintained at https://github.com/liyanage/git-tools/tree/master/githelper

The HTML version of this documentation is available at http://liyanage.github.com/git-tools/

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

You can abbreviate the subcommand name. The abbreviation does not have
to be a contiguous prefix or substring of the full name, any sequence of
characters that unanbiguously identifies one of the subcommands will work
(it must be anchored at the beginning, however).

Command Line Utility Examples
-----------------------------

Below are some command line usage examples. The examples assume a
``gh`` shell alias for githelper defined as follows::

    $ alias gh githelper.py

To get an overview of the nested working copies, use the ``tree`` subcommand::

    $ gh tree
    |<Working copy /path/to/my-great-project>
    |--<Working copy /path/to/my-great-project/Foo *>
    |----<Working copy /path/to/my-great-project/Foo/subexternal l*>
    |--<Working copy /path/to/my-great-project/Bar>
    |--<Working copy /path/to/my-great-project/Baz>
    |--<Working copy /path/to/my-great-project/Subproject *>
    |----<Working copy /path/to/my-great-project/Subproject/ABC/Demo>
    |--<Working copy /path/to/my-great-project/Xyz>

The * indicates a working copy with uncommited changes.
The l indicates a local-only branch, i.e. one that's not tracking a remote branch

To get a combined git status view, use ``status``::

    $ gh status
    <Working copy /path/to/my-great-project/Foo *>
     M data.txt
    <Working copy /path/to/my-great-project/Subproject *>
     A xyz.dat

Only working copies that have any interesting status are listed.

As a reminder, you could shorten the subcommand name and type just ``gh sta`` here.

To check out a certain point in time in the past in all nested working copies, you could
use the ``each`` subcommand, which runs a shell command in each one::

    $ gh each "git checkout \$(git rev-list -n 1 --before='2012-01-01 00:00' master)"

Another useful subcommand is ``branch``, it gives a complete overview of the branch
status of each working copy::

    $ gh b
    branch
    </Users/liyanage/Projects/foo>                               0↑ 0↓ master      4c3b6721  1h
    </Users/liyanage/Projects/foo/repositories/LibraryManager>   0↑ 0↓ master      301105f7  1h
    </Users/liyanage/Projects/foo/repositories/Reports *>        0↑ 0↓ master      7ffa7408  2h
    </Users/liyanage/Projects/foo/repositories/analyzer>         0↑ 0↓ feature/xyz c2881596  5h
    </Users/liyanage/Projects/foo/repositories/common l>         0↑ 0↓ master      f0a1ec75 34m

See the subcommand's detailed help for an explanation of the columns.

Many subcommands, ``fetch`` included, run the ``branch`` subcommand automatically after they finish.

These are just a few examples, see the command line help for the remaining subcommands.

Usage as Toolkit Module
=======================

If the utility does not provide what you need, you can write your own script
based on githelper as a module. The rest of this document explains the module's API.

The main entry point is the :py:class:`GitWorkingCopy` class. You instantiate it
with the path to a git working copy (which possibly has nested sub-working copies).

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
import imp
import sys
import types
import pickle
import select
import string
import logging
import getpass
import tempfile
import datetime
import argparse
import textwrap
import StringIO
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
        logging.debug('about to select(), timeout = {}'.format(timeout))
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
            sys.stdout.write(cls.start_sequence(stdout_color))
        if stderr_color:
            sys.stderr.write(cls.start_sequence(stderr_color))

        try:
            yield
        except:
            cls.clear()
            raise

        cls.clear()

    @classmethod
    def clear(cls):
        for stream in [sys.stdout, sys.stderr]:
            stream.write(cls.clear_sequence())

    @classmethod
    def start_sequence(cls, color=red):
        return "\x1b[3{0}m".format(color)

    @classmethod
    def clear_sequence(cls):
        return "\x1b[m"

    @classmethod
    def wrap(cls, value, color=red):
        return u'{}{}{}'.format(cls.start_sequence(color), value, cls.clear_sequence())


class GitRevision(object):

    def __init__(self, revision, message):
        self.revision = revision
        self.message = message

    @classmethod
    def parse_log_line_oneline(cls, log_line):
        match = re.match(r'^([0-9a-f]+)\s+(.*)', log_line)
        if not match:
            print >> sys.stderr, 'Unable to parse git log line "{}":'.format(log_line)
            return None
        return GitRevision(match.group(1), match.group(2))

    @classmethod
    def parse_log_lines_oneline(cls, log_lines):
        return [cls.parse_log_line_oneline(line) for line in log_lines]


class GitWorkingCopy(object):
    """
    A class to represent a git working copy.

    :param str path: The file system path to the working copy.
    :param githelper.GitWorkingCopy parent: A parent instance, you don't usually use this yourself.
    """

    STOP_TRAVERSAL = False
    """returned from a :py:meth:`~AbstractSubcommand.__call__` implementation to stop further recursion by :py:meth:`traverse`."""

    DID_LOG_ABOUT_CACHED_CHILD_LIST = False

    def __init__(self, path, parent=None, verbose=False):
        self.path = os.path.abspath(path)
        self.parent = parent
        self.child_list = None
        self.verbose = verbose

        status = subprocess.call('git status 1>/dev/null 2>/dev/null', shell=True, cwd=self.path)
        if status:
            raise Exception('{0} is not a git working copy'.format(self.path))

    def __str__(self):
        flags = ''
        if not self.current_branch_has_upstream():
            flags += 'l' # l for local-only
        if self.is_dirty():
            flags += '*'
        if flags:
            flags = ' ' + flags

        return '<{0}{1}>'.format(self.root_relative_path(), flags)

    def root_relative_path(self):
        if self.is_root():
            return os.path.basename(self.path)
        else:
            root_prefix = os.path.dirname(self.root_working_copy().path)
            return self.path[len(root_prefix) + 1:]

    def current_branch(self):
        """Returns the name of the current git branch"""
        output = self.output_for_git_command('git branch -a'.split())
        [branch] = [i[2:] for i in output if i.startswith('* ')]
        return branch

    def fork_point_commit_id_for_branch(self, other_branch):
        """Returns the fork point with another branch"""
        cmd = ['git', 'merge-base', '--fork-point', other_branch]
        output = self.output_for_git_command(cmd)
        if len(output) != 1:
            return None
        return output[0].strip()

    def tags_pointing_at(self, commit_reference):
        """Returns a list of tags that point to the given commit"""
        return self.output_for_git_command(['git', 'tag', '-l', '--points-at', commit_reference])

    def tags_pointing_at_head_commit(self):
        """Returns a list of tags that point to the head commit"""
        return self.tags_pointing_at(self.head_commit_hash())

    def head_commit_hash(self):
        return self.output_for_git_command(['git', 'rev-parse', 'HEAD'])[0][:8]

    def head_commit_age(self):
        head_commit_timestamp = self.output_for_git_command(['git', 'show', '--format=%ct', '--no-patch', 'HEAD'])[0]
        return datetime.datetime.now() - datetime.datetime.fromtimestamp(int(head_commit_timestamp))

    def head_commit_age_approximate_string(self):
        seconds = self.head_commit_age().total_seconds()

        days = int(seconds / (60 * 60 * 24))
        if days:
            return '{}d'.format(days)

        hours = int(seconds / (60 * 60))
        if hours:
            return '{}h'.format(hours)

        minutes = int(seconds / 60)
        if minutes:
            return '{}m'.format(minutes)

        return '{}s'.format(int(seconds))

    def current_repository(self):
        """Returns the name of the current git repository."""
        output = self.output_for_git_command('git remote -v'.split())[0]
        repository_names = re.findall(r'/([^/]+?)(?:\s|\.git)', output)
        return repository_names[0]

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

    def output_for_git_command(self, command, shell=False, filter_rules=None, header=None, check_returncode=None, echo_stderr=True):
        """
        Runs the given shell command (array or string) in the receiver's working directory and returns the output.

        :param bool shell: If ``True``, runs the command through the shell. See the :py:mod:`subprocess` library module documentation for details.

        """
        popen = FilteringPopen(command, cwd=self.path, shell=shell)
        popen.run(filter_rules=filter_rules, echo_stdout=False, echo_stderr=echo_stderr, header=header, check_returncode=check_returncode)
        return popen.stdoutlines()

    def is_root(self):
        """Returns True if the receiver does not have a parent working copy."""
        return self.parent is None

    def has_autostash_enabled(self):
        output = self.output_for_git_command('git config rebase.autoStash'.split())
        return output and output[0] == 'true'

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

    def current_branch_upstream(self):
        output = self.output_for_git_command('git rev-parse --abbrev-ref --symbolic-full-name @{u}'.split(), filter_rules=[('-', r'fatal')])
        return output

    def current_branch_has_upstream(self):
        return bool(self.current_branch_upstream())

    def commits_not_in_upstream(self):
        """Returns a list of git commits that have not yet been pushed to upstream."""
        output = self.output_for_git_command('git log --oneline @{u}..HEAD'.split())
        return GitRevision.parse_log_lines_oneline(output)

    def commits_only_in_upstream(self):
        """Returns a list of git commits that are only in upstream but not in the local tracking branch."""

        output = self.output_for_git_command('git log --oneline HEAD..@{u}'.split())
        return GitRevision.parse_log_lines_oneline(output)

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

    def is_dirty(self):
        """
        Returns True if the receiver's working copy has uncommitted modifications.

        Many operations depend on a clean state.

        """
        return bool(self.dirty_file_lines())

    def create_stash_and_reset_hard(self):
        """
        Stashes the uncommitted changes in the working copy using "stash create", i.e. without
        updating the "stash" reference, and runs "git reset --hard". Prints and returns the
        commit id if anything was stashed, None otherwise.

        """
        if not self.is_dirty():
            return None

        stash_commit = None
        output = self.output_for_git_command('git stash create'.split())
        if len(output):
            stash_commit = output[0]
            print 'Stashed changes, restore with "git stash apply {0}"'.format(stash_commit)
            output = self.output_for_git_command('git reset --hard'.split())
            #print '\n'.join(output)

        return stash_commit

    def apply_stash_commit(self, stash_commit):
        #print 'Applying stash ' + stash_commit
        output = self.output_for_git_command('git stash apply'.split() + [stash_commit])

    def dirty_file_lines(self):
        """Returns the output of git status for the files marked as modified, renamed etc."""
        output = self._check_output_in_path('git status --porcelain'.split()).splitlines()
        dirty_file_lines = [line[3:].strip('"') for line in output if not line.startswith('?')]
        return dirty_file_lines

    def info(self):
        config_path = os.path.join(self.path, '.git/config')
        with open(config_path) as file:
            pass

        return self.basename()

    def basename(self):
        return os.path.basename(self.path)

    def children(self):
        if self.child_list is None:
            self.child_list = self.cached_child_list()
            if self.child_list is None:
                self.child_list = []
                for (dirpath, dirnames, filenames) in os.walk(self.path, followlinks=True):
                    if dirpath == self.path:
                        continue

                    if not '.git' in dirnames:
                        continue

                    del dirnames[:]

                    wc = GitWorkingCopy(dirpath, parent=self, verbose=self.verbose)
                    self.child_list.append(wc)
                self.store_cached_child_list(self.child_list)
        return self.child_list

    def cached_child_list(self):
        if not self.is_root():
            return None
        cache_file_path = os.path.join(self.githelper_config_directory(), 'cached_child_list')
        if os.path.exists(cache_file_path):
            age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.stat(cache_file_path).st_mtime)
            if age.total_seconds() > 24 * 60 * 60:
                return None
            if self.verbose:
                self.print_cache_message(cache_file_path)
            with open(cache_file_path) as f:
                return [GitWorkingCopy(dirpath, parent=self, verbose=self.verbose) for dirpath in pickle.load(f)]

    @classmethod
    def print_cache_message(cls, cache_file_path):
        if cls.DID_LOG_ABOUT_CACHED_CHILD_LIST:
            return
        cls.DID_LOG_ABOUT_CACHED_CHILD_LIST = True
        print 'Using cached subrepository list from {}'.format(cache_file_path)

    def store_cached_child_list(self, child_list):
        cache_file_path = os.path.join(self.githelper_config_directory(should_create=True), 'cached_child_list')
        with open(cache_file_path, 'w') as f:
            pickle.dump([wc.path for wc in child_list], f)

    def githelper_config_directory(self, should_create=False):
        config_directory_path = os.path.join(self.git_directory(), 'githelper')
        if should_create and not os.path.exists(config_directory_path):
            os.mkdir(config_directory_path)
        return config_directory_path

    def git_directory(self):
        with self.chdir_to_path():
            return os.path.abspath(self.output_for_git_command('git rev-parse --git-dir'.split())[0])

    def __iter__(self):
        """
        Returns an iterator over ``self`` and all of its nested git working copies.

        See the :ref:`example above <iteration-example>`.

        """
        yield self
        for child in self.children():
            for item in child:
                yield item

    def self_or_descendants_dirty_working_copies(self):
        """
        Returns True if the receiver's or one of its nested working copies are dirty.

        :param bool list_dirty: If ``True``, prints the working copy path and the list of dirty files.

        """
        dirty_working_copies = []
        for item in self:
            if item.is_dirty():
                dirty_working_copies.append(item)

        return dirty_working_copies

    def traverse(self, iterator):
        """
        Runs the given callable ``iterator`` on the receiver and all of its
        nested sub-working copies.

        Before each call to iterator for a given working copy, the current directory is first
        set to that working copy's path.

        See the :ref:`example above <iteration-example>`.
        """
        if callable(getattr(iterator, "prepare_for_root", None)):
            if iterator.prepare_for_root(self) is GitWorkingCopy.STOP_TRAVERSAL:
                return

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

    def prepare_for_root(self, root_wc):
        """
        This method gets called on the root working copy only and lets you
        perform preparation steps that you want to do only once for the entire
        tree.

        :param githelper.GitWorkingCopy root_wc: The working copy to check.

        """
        pass

    def chained_post_traversal_subcommand_for_root_working_copy(self, root_wc):
        """
        This method gets called on the root working copy after the traversal
        of a tree has finished. The subcommand class can return another subcommand
        instance that will be run next.

        :param githelper.GitWorkingCopy root_wc: The working copy to process.

        """
        return None

    @classmethod
    def print_dirty_working_copies_error_message(cls):
        print >> sys.stderr, ANSIColor.wrap('Dirty working copies found, please either 1.) commit or stash first, 2.) use git\'s rebase.autoStash configuration option, or 3.) use the -s/--stash-pop option\n', color=ANSIColor.red)

    @classmethod
    def affirmative_answer_for_prompt(cls, prompt_string):
        prompt_input = raw_input('{} [Y/n] '.format(prompt_string))
        return prompt_input == '' or prompt_input.lower().startswith('y')

    @classmethod
    def configure_argument_parser(cls, parser):
        """
        If you override this in your subclass, you can configure additional command line arguments
        for your subcommand's arguments parser.

        :param argparse.ArgumentParser parser: The argument parser that you can configure.

        """
        pass

    @classmethod
    def read_string_from_clipboard(cls):
        string = None
        if sys.platform == 'darwin':
            import AppKit
            pb = AppKit.NSPasteboard.generalPasteboard()
            string = pb.stringForType_('public.utf8-plain-text')
        return string

    @classmethod
    def write_string_to_clipboard(cls, string):
        if sys.platform == 'darwin':
            import AppKit
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.writeObjects_(AppKit.NSArray.arrayWithObject_(string))

    @classmethod
    def format_and_print_dirty_working_copy_list(cls, dirty_working_copies):
        for wc in dirty_working_copies:
            print >> sys.stderr, wc
            with ANSIColor.terminal_color(ANSIColor.red, ANSIColor.red):
                print >> sys.stderr, ''.join([i + '\n' for i in wc.dirty_file_lines()])

    @classmethod
    def wants_working_copy(cls):
        """
        Return ``False`` to allow usage of your subcommand without a git working copy. The default is ``True``.
        """
        return True

    @classmethod
    def subcommand_name(cls):
        return '-'.join([i.lower() for i in re.findall(r'([A-Z][a-z]+)', re.sub(r'^Subcommand', '', cls.__name__))])


class SubcommandTree(AbstractSubcommand):
    """List the tree of nested working copies"""

    def __call__(self, wc):
        print '|{0}{1}'.format(len(wc.ancestors()) * '--', wc)


class SubcommandStatus(AbstractSubcommand):
    """Run git status recursively, omitting output for any working copies without interesting status."""

    def __call__(self, wc):
        rules = (
            ('-', r' On branch '),
            ('-', r'working directory clean'),
        )

        wc.run_shell_command('git status -s', filter_rules=rules, header=wc)


class SubcommandCopyHeadCommitHash(AbstractSubcommand):
    """Copy repository / branch / head hash to clipboard, optionally with a custom template"""

    def __call__(self, wc):
        template_name = self.args.template
        if template_name:
            config_variable = 'githelper.copy-template-' + template_name
            output = wc.output_for_git_command(['git', 'config', config_variable])
            if not output:
                print >> sys.stderr, 'No template found for git configuration variable "{}"'.format(config_variable)
                return GitWorkingCopy.STOP_TRAVERSAL
        else:
            config_variable = 'githelper.copy-template'
            output = wc.output_for_git_command(['git', 'config', config_variable])
            if not output:
                output = ['{repository} {branch} {commit} {tags}']

        output = self.interpolate_data_into_template_lines(wc, output)
        output_string = ''.join([l + '\n' for l in output])

        self.write_string_to_clipboard(output_string)
        print output_string,

        return GitWorkingCopy.STOP_TRAVERSAL

    def interpolate_data_into_template_lines(self, wc, template_lines):
        repository, branch, commit = wc.current_repository(), wc.current_branch(), wc.head_commit_hash()
        tags = ['tags/' + t for t in wc.tags_pointing_at_head_commit()]
        if tags:
            tags = '(' + ', '.join(tags) + ')'
        else:
            tags = None
        data = dict(zip('repository branch commit tags'.split(), (repository, branch, commit, tags)))
        output = []
        for line in template_lines:
            for key, value in data.items():
                token = '{' + key + '}'
                if token in line:
                    line = line.replace(token, value if value else '')
            output.append(line)
        return output

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        description = textwrap.dedent('''        Optional name of a template.

        Templates are snippets of text into which the commit information is interpolated.
        The following replacement tokens are available:

            {branch}          The current branch name
            {repository}      The last path element of the current repository's remote URL,
                              without any file extensions such as ".git"
            {commit}          The head commit ID, abbreviated
            {tags}            a comma-separated, parenthesized list of tags that point to the head commit

        If you don't select a template with this option, the default template is used:

            "{repository} {branch} {commit} {tags}"

        You store a custom template with git config. To change the default, unnamed one:

            $ git config githelper.copy-template 'Repository: {repository} - Branch: {branch} - Commit: {commit}'

        To set any named template, add a dash and the name to the git configuration variable,
        in this example "merge":

            $ git config githelper.copy-template-merge $'- Code Reviewed By: \\n- Branch: {branch} ({commit})\\n- Repository: {repository}\\n- Testing Details: \\n'

        This example also shows how to set multiline-templates with \\n sequences and the Bash $'' construct.

        ''')
        parser.add_argument('template', nargs='?', default=None, help=description)


class SubcommandCheckoutBugfixBranch(AbstractSubcommand):
    """Check out a bugfix branch named user/<username>/name, with name based on the contents of the clipboard."""

    def __call__(self, wc):
        import readline

        clipboard_string = self.read_string_from_clipboard()
        branch_name_suggestion = None
        branch_name_suggestion_raw = None
        if clipboard_string:
            clipboard_string = re.sub(r'\[.+?\]\s+', '', clipboard_string)
            items = re.findall(r'.*?(\d+)(.*)', clipboard_string)
            if items:
                number, string = items[0]
                words = re.findall(r'([a-zA-Z]{3,})', string)
                branch_name_suggestion_raw = 'user/{}/{}'.format(os.environ['USER'], '-'.join([number] + words)).lower()
                if len(words) > 5:
                    del(words[5:])
                branch_name_suggestion = 'user/{}/{}'.format(os.environ['USER'], '-'.join([number] + words)).lower()

        if branch_name_suggestion:
            prompt = 'Type branch name or hit return to accept "{}"\n'.format(branch_name_suggestion)
            self.write_string_to_clipboard(branch_name_suggestion_raw)
        else:
            prompt = 'Type branch name\n'

        branch_name = raw_input(prompt)
        if not len(branch_name):
            if not branch_name_suggestion:
                print >> sys.stderr, 'No suitable branch name'
                return GitWorkingCopy.STOP_TRAVERSAL
            branch_name = branch_name_suggestion

        self.write_string_to_clipboard(branch_name)
        wc.run_shell_command('git checkout -b {}'.format(branch_name))

        output = wc.output_for_git_command('git status --porcelain -uno'.split())
        staged = [l for l in output if l.startswith('M')]
        if staged:
            wc.run_shell_command(['git', 'commit', '-m', clipboard_string])

        return GitWorkingCopy.STOP_TRAVERSAL


class SubcommandDropBugfixBranch(AbstractSubcommand):
    """Delete a bugfix branch locally and remotely. The branch must be prefixed with "user/" """

    def __call__(self, wc):
        local_branch_ref = self.args.branch
        output = wc.output_for_git_command('git rev-parse --abbrev-ref HEAD'.split())
        current_branch_ref = output[0]
        if not local_branch_ref:
            local_branch_ref = current_branch_ref

        if self.args.template:
            self.print_manual_help('Git commands template', ['remote_name'], 'branch_name')
            return GitWorkingCopy.STOP_TRAVERSAL

        remote_names = wc.output_for_git_command('git remote'.split())
        if len(remote_names) > 1:
            self.print_manual_help('More than one remote: "{}", please delete manually'.format(', '.join(remote_names)), remote_names, local_branch_ref)
            return GitWorkingCopy.STOP_TRAVERSAL
        remote_name = None
        if remote_names:
            remote_name = remote_names[0]

        if not local_branch_ref.startswith('user/'):
            self.print_manual_help('Branch name does not start with "user/"', remote_names, local_branch_ref)
            return GitWorkingCopy.STOP_TRAVERSAL

        remote_branch_ref = None
        if remote_name:
            remote_branch_symbolic_ref = local_branch_ref + '@{u}'
            output = wc.output_for_git_command(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', remote_branch_symbolic_ref], filter_rules=[('-', r'fatal')], check_returncode=False, echo_stderr=False)

            if output and output != [remote_branch_symbolic_ref]:
                remote_branch_ref = output[0][len(remote_name) + 1:]
                if not remote_branch_ref.startswith('user/'):
                    self.print_manual_help('Remote branch name "{}" does not start with "user/", please delete manually'.format(remote_branch_ref), remote_names, local_branch_ref)
                    return GitWorkingCopy.STOP_TRAVERSAL
            else:
                print >> sys.stderr, 'No upstream branch configured, will delete only local branch'

        if not self.args.no_prompt:
            prompt = 'Delete local branch "{}"'.format(local_branch_ref)
            if remote_branch_ref:
                prompt += ' and remote branch "{}:{}"'.format(remote_name, remote_branch_ref)
            if not self.affirmative_answer_for_prompt(prompt + '?'):
                return GitWorkingCopy.STOP_TRAVERSAL

        if current_branch_ref == local_branch_ref:
            output = wc.output_for_git_command('git rev-parse --abbrev-ref --symbolic-full-name @{-1}'.split())
            if not output:
                self.print_manual_help('Current branch is branch to be deleted, but previous branch is unknown, please delete manually', remote_names, local_branch_ref)
                return GitWorkingCopy.STOP_TRAVERSAL
            wc.run_shell_command('git checkout @{-1}'.split())

        wc.run_shell_command('git branch -D'.split() + [local_branch_ref])
        if remote_branch_ref:
            wc.run_shell_command('git push -d'.split() + [remote_name, remote_branch_ref])

        return GitWorkingCopy.STOP_TRAVERSAL

    def print_manual_help(self, reason, remotes=None, branch='<branch-name>'):
        print >> sys.stderr, reason + ', please delete manually:'
        print >> sys.stderr, 'git branch -D {}'.format(branch)
        if remotes:
            if len(remotes) > 1:
                remotes = '(' + '|'.join(remotes) + ')'
            else:
                remotes = remotes[0]
            print >> sys.stderr, 'git push -d {} {}'.format(remotes, branch)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('branch', nargs='?', default=None, help='The name of the branch that should be deleted, defaults to the currently checked out branch')
        parser.add_argument('-n', '--no-prompt', action='store_true', help="Don't prompt for confirmation")
        parser.add_argument('-t', '--template', action='store_true', help='Just print the git command template')


class WorkingCopyTreeStashingSubcommand(AbstractSubcommand):

    def prepare_for_root(self, root_wc):
        dirty_working_copies = root_wc.self_or_descendants_dirty_working_copies()
        if dirty_working_copies:
            if self.args.stash_pop:
                return
            dirty_wcs_without_autostash = [wc for wc in dirty_working_copies if not wc.has_autostash_enabled()]
            if not dirty_wcs_without_autostash:
                print >> sys.stderr, 'Proceeding with dirty working copies because rebase.autoStash is set\n'
                return
            self.print_dirty_working_copies_error_message()
            self.format_and_print_dirty_working_copy_list(dirty_working_copies)
            return GitWorkingCopy.STOP_TRAVERSAL

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('-s', '--stash-pop', action='store_true', help='Allow dirty working copy. Stash before checkout and pop afterwards.')


class SubcommandCheckout(WorkingCopyTreeStashingSubcommand):
    """Check out a given branch if it exists"""

    def __call__(self, wc):
        target_branch_candidates = self.args.branch
        current_branch = wc.current_branch()

        target_branch = None

        for target_branch_candidate in target_branch_candidates:
            target_branch = self.target_branch_for_branch_name(target_branch_candidate, wc)
            if target_branch:
                break

        if not target_branch:
            if len(target_branch_candidates) == 1:
                print >> sys.stderr, 'No branch found matching "{0}" in {1}, staying on "{2}"'.format(target_branch_candidates[0], wc, current_branch)
            else:
                print >> sys.stderr, 'No branch found matching any of "{0}" in {1}, staying on "{2}"'.format(', '.join(target_branch_candidates), wc, current_branch)
            return

        if current_branch == target_branch:
            return

        print ANSIColor.wrap(wc, color=ANSIColor.green)
        stash_commit = None
        if wc.is_dirty():
            stash_commit = wc.create_stash_and_reset_hard()

        try:
            rules = [
                ('-', r'use "git pull"'),
                ('-', r'Switched to branch'),
                ('-', r'is up-to-date'),
                ('-', r'Your branch is behind'),
            ]
            wc.run_shell_command('git checkout {0}'.format(target_branch), filter_rules=rules)
        finally:
            if stash_commit:
                wc.apply_stash_commit(stash_commit)

    def target_branch_for_branch_name(self, target_branch_candidate, wc):
        local_branch_candidates = [i for i in wc.local_branch_names() if target_branch_candidate in i]
        remote_branch_candidates = [re.sub(r'^[^/]+/', '', i) for i in wc.remote_branch_names() if target_branch_candidate in i]

        TargetBranchResult = collections.namedtuple('TargetBranchResult', ['name', 'needs_remote_checkout', 'should_abort'])

        def find_exact_local_match():
            if target_branch_candidate in local_branch_candidates:
                return TargetBranchResult(target_branch_candidate, False, False)

        def find_exact_remote_match():
            if target_branch_candidate in remote_branch_candidates:
                return TargetBranchResult(target_branch_candidate, True, False)

        def find_local_substring_match():
            count = len(local_branch_candidates)
            if count > 1:
                print >> sys.stderr, 'Branch name "{}" is ambiguous in {}: {}'.format(target_branch_candidate, wc, ', '.join(local_branch_candidates))
                return TargetBranchResult(None, False, True)
            elif count == 1:
                return TargetBranchResult(local_branch_candidates[0], False, False)

        def find_remote_substring_match():
            if target_branch_candidate in remote_branch_candidates:
                remote_branch_candidates.remove(target_branch_candidate) # remove exact remote match whose checkout user must have declined
            count = len(remote_branch_candidates)
            if count > 1:
                print >> sys.stderr, 'Branch name "{}" is ambiguous for remote branches in {}: {}'.format(target_branch_candidate, wc, ', '.join(remote_branch_candidates))
                return TargetBranchResult(None, False, True)
            elif count == 1:
                return TargetBranchResult(remote_branch_candidates[0], True, False)

        ordered_strategies = [find_exact_local_match, find_exact_remote_match, find_local_substring_match, find_remote_substring_match]
        for strategy in ordered_strategies:
            target_branch_result = strategy()
            if not target_branch_result:
                continue

            if target_branch_result.should_abort:
                return

            if target_branch_result.needs_remote_checkout:
                if not self.affirmative_answer_for_prompt('No local branch found for "{0}" in {1} but a remote branch exists, check it out?'.format(target_branch_candidate, wc)):
                    continue
                wc.run_shell_command('git checkout {}'.format(target_branch_result.name))

            return target_branch_result.name

    def chained_post_traversal_subcommand_for_root_working_copy(self, root_wc):
        return SubcommandBranch(self.args)

    @classmethod
    def configure_argument_parser(cls, parser):
        super(SubcommandCheckout, cls).configure_argument_parser(parser)
        parser.add_argument('branch', nargs='+', help='One or more names of the branch that should be checked out. The first one to exist will be used')


class SubcommandPull(WorkingCopyTreeStashingSubcommand):
    """Run git pull recursively, optionally stashing and unstashing uncommitted changes automatically."""

    def __call__(self, wc):
        stash_commit = None
        print ANSIColor.wrap(wc, color=ANSIColor.green)
        if wc.is_dirty() and not wc.has_autostash_enabled():
            stash_commit = wc.create_stash_and_reset_hard()

        if not wc.current_branch_has_upstream():
            print 'Current branch {} has no upstream branch to pull from'.format(wc.current_branch())
            return

        try:
            rules = [
                ('-', r'Rebasing'),
                ('-', r'Successfully rebased'),
            ]
            wc.run_shell_command('git pull', filter_rules=rules)
        finally:
            if stash_commit:
                wc.apply_stash_commit(stash_commit)

    def chained_post_traversal_subcommand_for_root_working_copy(self, root_wc):
        return SubcommandBranch(self.args)


class SubcommandForkPoint(AbstractSubcommand):

    """Print the fork point of the current branch and another branch"""

    def __call__(self, wc):
        fork_point_commit = wc.fork_point_commit_id_for_branch(self.args.target_branch)
        if fork_point_commit:
            print '\nFork-point between "head" ({}) and "{}":'.format(wc.current_branch(), self.args.target_branch)
            cmd = ['git', 'log', '-1', '--pretty=format:%h  %ad  %s', fork_point_commit]
            wc.run_shell_command(cmd)

            print
            for other_branch in 'head', self.args.target_branch:
                cmd = ['git', 'log', '--pretty=format:%h  %ad  %s', other_branch, '^' + fork_point_commit]
                output = wc.output_for_git_command(cmd)
                print '{} commits in "{}" but not in fork-point {}'.format(len(output), other_branch, fork_point_commit[:12])
                print ''.join([line + '\n' for line in output])
        else:
            print 'Unable to find fork point between "{}" and "{}"'.format(wc.current_branch(), self.args.target_branch)
        return GitWorkingCopy.STOP_TRAVERSAL

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('target_branch', help='The target branch for the current branch for which we want to find the fork point')


class SubcommandSquashToForkPoint(AbstractSubcommand):
    """Find the fork point of the current branch and squash multiple commits between that and head into one"""

    def __call__(self, wc):
        if wc.is_dirty():
            print >> sys.stderr, ANSIColor.wrap('Dirty working copies found, please commit or stash first', color=ANSIColor.red)
            self.format_and_print_dirty_working_copy_list([wc])
            return GitWorkingCopy.STOP_TRAVERSAL

        fork_point_commit = wc.fork_point_commit_id_for_branch(self.args.target_branch)
        if not fork_point_commit:
            print 'Unable to find fork point between "{}" and "{}"'.format(wc.current_branch(), self.args.target_branch)
            return GitWorkingCopy.STOP_TRAVERSAL

        print '\nFork-point between "head" ({}) and "{}":'.format(wc.current_branch(), self.args.target_branch)
        cmd = ['git', 'log', '-1', '--pretty=format:%h  %ad  %s', fork_point_commit]
        wc.run_shell_command(cmd)

        cmd = ['git', 'log', '--pretty=format:%h  %ad  %s', 'head', '^' + fork_point_commit]
        output = wc.output_for_git_command(cmd)
        commit_count = len(output)
        print '\n{} commits in head but not in fork-point {}'.format(commit_count, fork_point_commit[:12])
        print ''.join(['{}) {}\n'.format(commit_count - number, line) for number, line in enumerate(output)])

        if commit_count < 2:
            print 'Fewer than two commits, nothing to squash'
            return GitWorkingCopy.STOP_TRAVERSAL

        prompt_input = raw_input('Pick commit from which to reuse subject/author/date for squashed commit (1-{}, anything else to cancel) '.format(commit_count))
        authorship_commit = None
        try:
            value = int(prompt_input)
            if value >= 1 and value <= commit_count:
                authorship_commit = output[commit_count - value].split()[0]
        except ValueError as e:
            pass

        if not authorship_commit:
            return GitWorkingCopy.STOP_TRAVERSAL

        print 'Squashing with the following commands, head before squash is {}:'.format(wc.head_commit_hash())
        for cmd in (['git', 'reset', '--soft', fork_point_commit], ['git', 'commit', '-C', authorship_commit]):
            print ' '.join(cmd)
            if not self.args.dry_run:
                wc.run_shell_command(cmd)

        return GitWorkingCopy.STOP_TRAVERSAL

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('target_branch', help='The target branch for the current branch, which is assumed to be a feature branch with multiple commits that need to be squashed.')
        parser.add_argument('--dry-run', '-n', action='store_true', help="Don't make any changes, just print the git commands")


class SubcommandBranch(AbstractSubcommand):
    """Show checked out branch and other status information of each working copy"""

    column_justifiers_and_accessors = (
        (string.ljust, lambda x: unicode(x)),
        (string.rjust, lambda x: unicode(len(x.commits_not_in_upstream())) + u'↑' if x.current_branch_has_upstream() else '-'),
        (string.rjust, lambda x: unicode(len(x.commits_only_in_upstream())) + u'↓' if x.current_branch_has_upstream() else '-'),
        (string.ljust, lambda x: x.current_branch()),
        (string.ljust, lambda x: x.head_commit_hash()),
        (string.rjust, lambda x: str(x.head_commit_age_approximate_string())),
    )

    def column_count(self):
        return len(SubcommandBranch.column_justifiers_and_accessors)

    def prepare_for_root(self, root_wc):
        self.maxlen = [0] * self.column_count()
        for wc in root_wc:
            for index, (justifier, accessor) in enumerate(SubcommandBranch.column_justifiers_and_accessors):
                self.maxlen[index] = max((self.maxlen[index], len(accessor(wc))))

    def __call__(self, wc):
        def access(index, item):
            return self.column_justifiers_and_accessors[index][1](item)

        def justify(index, string, length):
            return self.column_justifiers_and_accessors[index][0](string, length)

        format = ' '.join(['{' + unicode(i) + '}' for i in range(self.column_count())])
        output = format.format(*[justify(i, access(i, wc), self.maxlen[i]) for i in xrange(self.column_count())])
        print output

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.formatter_class = argparse.RawDescriptionHelpFormatter

        parser.description = textwrap.dedent('''            This subcommand gives a complete overview of the branch
            status of each subrepository:

                $ gh b
                branch
                </Users/liyanage/Projects/foo>                               0↑ 0↓ master      4c3b6721  1h
                </Users/liyanage/Projects/foo/repositories/LibraryManager>   0↑ 0↓ master      301105f7  1h
                </Users/liyanage/Projects/foo/repositories/Reports *>        0↑ 0↓ master      7ffa7408  2h
                </Users/liyanage/Projects/foo/repositories/analyzer>         0↑ 0↓ feature/xyz c2881596  5h
                </Users/liyanage/Projects/foo/repositories/common l>         0↑ 0↓ master      f0a1ec75 34m

            In column order, it lists:
            - the path to the working copy
            - the number of commits to push
            - the number of commits to pull
            - the branch name
            - the head commit ID
            - the age of the head commit

            For the "commits to pull" information to be up to date, you have to run the "fetch" subcommand first.

            Many subcommands (among them "fetch") automatically run the branch subcommand afterwards.''')


class SubcommandFetch(AbstractSubcommand):
    """Run git fetch recursively"""

    def __call__(self, wc):
        wc.run_shell_command('git fetch')

    def chained_post_traversal_subcommand_for_root_working_copy(self, root_wc):
        return SubcommandBranch(self.args)


class SubcommandEach(AbstractSubcommand):
    """Run a shell command in each working copy"""

    def __call__(self, wc):
        command = ' '.join(self.args.shell_command)
        wc.run_shell_command(command, header=wc, check_returncode=False)

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('shell_command', nargs='+', help='A shell command to execute in the context of each working copy. If you need to use options starting with -, add " -- " before the first one.')


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
            if k.startswith('Subcommand') and callable(getattr(v, 'subcommand_name', None)):
                subcommand_map[v.subcommand_name()] = v

        return subcommand_map

    @classmethod
    def resolve_subcommand_abbreviation(cls, subcommand_map):
        non_option_arguments = [i for i in sys.argv[1:] if not i.startswith('-')]
        if not non_option_arguments:
            return True

        subcommand = non_option_arguments[0]
        if subcommand in subcommand_map.keys():
            return True

        # converts a string like 'abc' to a regex like '(a).*?(b).*?(c)'
        regex = re.compile('.*?'.join(['(' + char + ')' for char in subcommand]))
        subcommand_candidates = []
        for subcommand_name in subcommand_map.keys():
            match = regex.match(subcommand_name)
            if not match:
                continue
            subcommand_candidates.append(cls.subcommand_candidate_for_abbreviation_match(subcommand_name, match))

        if not subcommand_candidates:
            return True

        if len(subcommand_candidates) == 1:
#            print >> sys.stderr, subcommand_candidates[0].decorated_name
            sys.argv[sys.argv.index(subcommand)] = subcommand_candidates[0].name
            return True

        print >> sys.stderr, 'Ambiguous subcommand "{}": {}'.format(subcommand, ', '.join([i.decorated_name for i in subcommand_candidates]))
        return False

    @classmethod
    def subcommand_candidate_for_abbreviation_match(cls, subcommand_name, match):
        SubcommandCandidate = collections.namedtuple('SubcommandCandidate', ['name', 'decorated_name'])
        decorated_name = ''
        for i in range(1, match.lastindex + 1):
            span = match.span(i)
            preceding = subcommand_name[match.span(i - 1)[1]:span[0]] if span[0] else ''
            letter = subcommand_name[span[0]:span[1]]
            decorated_name += preceding + ANSIColor.wrap(letter, color=ANSIColor.green)
        trailing = subcommand_name[span[1]:]
        decorated_name += trailing
        return SubcommandCandidate(subcommand_name, decorated_name)

    @classmethod
    def run(cls):
        subcommand_map = cls.subcommand_map()
        if not cls.resolve_subcommand_abbreviation(subcommand_map):
            exit(1)

        parser = argparse.ArgumentParser(description='Git helper')
        parser.add_argument('--root_path', help='Path to root working copy', default=os.getcwd())
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debug logging')
        subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand_name')
        for subcommand_name, subcommand_class in subcommand_map.items():
            subparser = subparsers.add_parser(subcommand_name, help=subcommand_class.__doc__)
            subcommand_class.configure_argument_parser(subparser)

        args = parser.parse_args()
        if args.verbose:
            logging.basicConfig(level=logging.INFO)

        subcommand_class = subcommand_map[args.subcommand_name]
        subcommand = subcommand_class(args)

        if subcommand_class.wants_working_copy():
            while subcommand:
                wc = GitWorkingCopy(args.root_path, verbose=args.verbose)
                wc.traverse(subcommand)
                subcommand = subcommand.chained_post_traversal_subcommand_for_root_working_copy(wc)
        else:
            subcommand()

if __name__ == "__main__":
    GitHelperCommandLineDriver.run()
