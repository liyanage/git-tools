#!/usr/bin/env python

"""
Introduction
------------

githelper is both a module and a command line utility for working
with git_ working copies, especially git-svn ones where
``svn:externals`` references are mapped to nested git-svn working copies.

Maintained at https://github.com/liyanage/git-tools/tree/master/githelper

HTML version of this documentation at http://liyanage.github.com/git-tools/

.. _git: http://git-scm.com

Command Line Utility
--------------------

This documentation does not cover the command line utility usage
in detail because you can get that with the help option::

    githelper.py -h

The utility is subcommand-based, and each subcommand has its own options.
You can get a list of subcommands with the -h option shown above, and each
subcommand in turn supports the -h flag::

    githelper.py some_subcommand -h

Usage as Toolkit Module
-----------------------

If the utility does not provide what need, you can write your own script
based on githelper as a module. The rest of this document explains the API.

The main entry point is the ``GitWorkingCopy`` class. You instantiate it
with the path to a git or git-svn working copy (which possibly
has nested sub-working copies).

You can then traverse the tree of nested working copies with the
``self_and_descendants()`` method::

    #!/usr/bin/env python
    
    import githelper
    import os
    import sys
    
    root_wc = githelper.GitWorkingCopy(sys.argv[1])

    for wc in root_wc.self_and_descendants():
        # do something interesting with wc using its API

The ``traverse()`` method provides another way to do this,
it takes a callable, in the following example a function::

    def process_working_copy(wc):
        print wc.current_branch()

    root_wc = githelper.GitWorkingCopy(sys.argv[1])
    root_wc.traverse(process_working_copy)

Or a callable object::

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
the ``GitWorkingCopy`` API.

.. _`module's source code`: https://github.com/liyanage/git-tools/blob/master/githelper/githelper.py

API Documentation
-----------------

"""

# autopep8 -i --ignore E501 githelper.py

import argparse
import os
import re
import sys
import types
import string
import subprocess
import contextlib
import itertools


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
    """A class to represent a git or git-svn working copy."""

    STOP_TRAVERSAL = False

    def __init__(self, path, parent=None):
        self.path = path
        self._svn_info = None
        self.parent = parent
        self.children = []

        status = subprocess.call('git status 1>/dev/null 2>/dev/null', shell=True, cwd=self.path)
        if status:
            raise Exception('{0} is not a git working copy'.format(self.path))

        for (dirpath, dirnames, filenames) in os.walk(path):
            if dirpath == path:
                continue

            if not '.git' in dirnames:
                continue

            del dirnames[:]

            wc = GitWorkingCopy(dirpath, parent=self)
            self.children.append(wc)

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

    def remote_branch_name_for_name_list(self, name_list):
        """
        Returns a remote branch name matching a list of candidate strings.
        
        Tries to find a remote branch names using all possible combinations
        of the names in the list. For example, given::
        
            ['foo', 'bar']
        
        as name_list, it would find any of these::
        
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

    def run_shell_command(self, command, shell=None):
        """Runs the given shell command (array or string) in the receiver's working directory."""
        if shell is None:
            if isinstance(command, types.StringTypes):
                shell = True
            else:
                shell = False

        with ANSIColor.terminal_color(ANSIColor.blue, ANSIColor.blue):
            subprocess.check_call(command, cwd=self.path, shell=shell)

    def output_for_git_command(self, command, shell=False):
        """
        Runs the given shell command (array or string) in the receiver's working directory and returns the output.

        :param shell: If ``True``, runs the command through the shell. See the subprocess_ library module documentation for details.
        
        .. _subprocess: http://docs.python.org/library/subprocess.html#frequently-used-arguments

        """
        return subprocess.check_output(command, cwd=self.path, shell=shell).splitlines()

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

    def svn_info(self, key=None):
        """
        Returns a dictionary containing the key/value pairs in the output of ``git svn info``.
        
        :param key: When present, returns just the one value associated with the given key.
        
        """
        if not self._svn_info:
            output = subprocess.check_output('git svn info'.split(), cwd=self.path)
            self._svn_info = {}
            for match in re.finditer('^([^:]+): (.*)$', output, re.MULTILINE):
                self._svn_info[match.group(1)] = match.group(2)

        if key:
            return self._svn_info[key]
        else:
            return self._svn_info

    def is_dirty(self):
        """
        Returns True if the receiver's working copy has uncommitted modifications.
        
        Many operations depend on a clean state.
        
        """
        return bool(self.dirty_file_lines())

    def dirty_file_lines(self):
        """Returns the output of git status for the files marked as modified, renamed etc."""
        output = subprocess.check_output('git status --porcelain'.split(), cwd=self.path).splitlines()
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

    def self_and_descendants(self):
        """
        Returns a generator for self and all nested git working copies.
        
        See the example above.
        
        """
        yield self
        for child in self.children:
            for item in child.self_and_descendants():
                yield item

    def self_or_descendants_are_dirty(self, list_dirty=False):
        """
        Returns True if the receiver's or one of its nested working copies are dirty.

        :param list_dirty: If ``True``, prints the working copy path and the list of dirty files.

        """
        dirty_working_copies = []
        for item in self.self_and_descendants():
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
        Runs the given callable ``iterator`` on each item returned by ``self_and_descendants()``.

        Before each call to iterator for a given working copy, the current directory is first
        set to that working copy's path.
        
        See example above.
        """
        if callable(getattr(iterator, "prepare_for_root", None)):
            iterator.prepare_for_root(self)

        if not callable(iterator):
            raise Exception('{0} is not callable'.format(iterator))

        for item in self.self_and_descendants():
            with item.chdir_to_path():
                if iterator(item) is GitWorkingCopy.STOP_TRAVERSAL:
                    break

    @contextlib.contextmanager
    def chdir_to_path(self):
        """
        A context manager for the ``with`` statement that temporarily switches the current working directory to the receiver's working copy directory.
        
        Example::
            
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
        A context manager for the ``with`` statement that temporarily switches the current git branch to another one and afterwards restores the original one.
        
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

    def __init__(self, argument_parser):
        self.args = argument_parser

    def __call__(self, wc):
        pass

    def check_preconditions(self, wc):
        # perform this check only once at the root
        if not wc.is_root():
            return True

        return not wc.self_or_descendants_are_dirty(list_dirty=True)

    def prepare_for_root(self, root_wc):
        pass
        
    def check_for_git_svn_and_warn(self, wc):
        if not wc.is_git_svn():
            print >> sys.stderr, '{0} is not git-svn, skipping'.format(wc)
            return False
        return True

    @classmethod
    def argument_parser_help(cls):
        return '(No help available)'

    @classmethod
    def configure_argument_parser(cls, parser):
        pass


class SubcommandResetMasterToSvnBranch(AbstractSubcommand):

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
    def argument_parser_help(cls):
        return 'Hard-reset the master branch of a working copy to a specific remote branch. Aborts if the working copy is dirty.'

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('remote_branch_names', nargs='+', help='A list of one or more remote branch names. The tool will try to find a remote name using all combinations of the given items, ignoring case.')


class SubcommandSvnRebase(AbstractSubcommand):

    def __call__(self, wc):
        if not self.check_preconditions(wc):
            return GitWorkingCopy.STOP_TRAVERSAL

        if not self.check_for_git_svn_and_warn(wc):
            return

        if not wc.has_branch('master'):
            print >> sys.stderr, '{0} does not have a master branch, skipping'.format(wc)
            return

        with wc.switched_to_branch('master'):
            print wc
            wc.run_shell_command('git svn rebase')

    @classmethod
    def argument_parser_help(cls):
        return 'Perform git svn rebase in each working copy. Temporarily switches to branch "master" if not already there. Aborts if the working copy is dirty.'


class SubcommandTree(AbstractSubcommand):

    def __call__(self, wc):
        print '|{0}{1}'.format(len(wc.ancestors()) * '--', wc)

    @classmethod
    def argument_parser_help(cls):
        return 'List the tree of nested working copies'


class SubcommandStatus(AbstractSubcommand):

    def __call__(self, wc):
        print wc
        wc.run_shell_command('git status')

    @classmethod
    def argument_parser_help(cls):
        return 'Run git status in each working copy'


class SubcommandBranch(AbstractSubcommand):

    def __init__(self, args):
        super(SubcommandBranch, self).__init__(args)

    def prepare_for_root(self, root_wc):
        maxlen = 0
        for i in root_wc.self_and_descendants():
            maxlen = max((maxlen, len(str(i))))
        self.maxlen = maxlen

    def __call__(self, wc):
        url = wc.svn_info('URL')
        svn_basename = os.path.basename(url)
        branch = wc.current_branch()
        print '{0} {1} {2}'.format(string.ljust(str(wc), self.maxlen), string.ljust(branch, 10), string.ljust(svn_basename, 10))

    @classmethod
    def argument_parser_help(cls):
        return 'Show local and SVN branch of each working copy'


class SubcommandEach(AbstractSubcommand):

    def __call__(self, wc):
        print wc
        wc.run_shell_command(self.args.shell_command)

    @classmethod
    def argument_parser_help(cls):
        return 'Run a shell command in each working copy'

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('shell_command', nargs='+', help='A shell command to execute in the context of each working copy. If you need to use options starting with -, add " -- " before the first one.')


class SubcommandSvnDiff(AbstractSubcommand):

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
    def argument_parser_help(cls):
        return 'Get a diff for a git-svn working copy that matches the corresponding svn diff'

    @classmethod
    def configure_argument_parser(cls, parser):
        parser.add_argument('-c', '--copy', action='store_true', help='Copy the diff output to the OS X clipboard instead of printing it')
        parser.add_argument('git_diff_args', nargs='*', help='Optional arguments to git diff. If you need to pass options starting with -, add " -- " before the first one.')


class GitHelperCommandLineDriver(object):

    @classmethod
    def run(cls):
        subcommand_map = {}
        for k, v in globals().items():
            if not k.startswith('Subcommand'):
                continue
            subcommand_map[k[10:].lower()] = v

        parser = argparse.ArgumentParser(description='Git-SVN helper')
        parser.add_argument('--root_path', help='Path to root working copy', default=os.getcwd())
        subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand_name')
        for subcommand_name, subcommand_class in subcommand_map.items():
            subparser = subparsers.add_parser(subcommand_name, help=subcommand_class.argument_parser_help())
            subcommand_class.configure_argument_parser(subparser)

        args = parser.parse_args()

        subcommand_class = subcommand_map[args.subcommand_name]
        subcommand = subcommand_class(args)

        wc = GitWorkingCopy(args.root_path)
        wc.traverse(subcommand)


if __name__ == "__main__":
    GitHelperCommandLineDriver.run()
