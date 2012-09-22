#!/usr/bin/env python

"""
Extensible git and git-svn toolkit.

Written by Marc Liyanage <http://www.github.com/liyanage>

Usage help:
    githelper.py -h

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
    """
    A helper class for printing ANSI color sequences to the terminal.
    
    """

    red = '1'
    green = '2'
    yellow = '3'
    blue = '4'

    @classmethod
    @contextlib.contextmanager
    def terminal_color(cls, stdout_color=None, stderr_color=red):
        """
        Provide a context manager for the "with" statement. Exmaple:
        
        with ANSIColor.terminal_color(ANSIColor.red):
            
        
        """

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


STOP_TRAVERSAL = False

class GitWorkingCopy(object):

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
        output = self.output_for_git_command('git branch -a'.split())
        [branch] = [i[2:] for i in output if i.startswith('* ')]
        return branch

    def has_branch(self, branch_name):
        return branch_name in self.branch_names()

    def branch_names(self):
        output = self.output_for_git_command('git branch -a'.split())
        return [i[2:] for i in output]

    def remote_branch_names(self):
        return [i[8:] for i in self.branch_names() if i.startswith('remotes/')]

    def remote_branch_name_for_name_list(self, name_list):
        name_list = [i.lower() for i in name_list]
        candidates = set(name_list)
        candidates.update(['-'.join(i) for i in itertools.permutations(name_list)])

        for name in self.remote_branch_names():
            if name.lower() in candidates:
                return name

        return None

    def switch_to_branch(self, branch_name):
        if not self.has_branch(branch_name):
            raise Exception('{0} does not have a branch named {1}, cannot switch'.format(self, branch_name))

        self.run_shell_command(['git', 'checkout', branch_name])

    def hard_reset_current_branch(self, target):
        self.run_shell_command(['git', 'reset', '--hard', target])

    def run_shell_command(self, command, shell=None):
        if shell is None:
            if isinstance(command, types.StringTypes):
                shell = True
            else:
                shell = False

        with ANSIColor.terminal_color(ANSIColor.blue, ANSIColor.blue):
            subprocess.check_call(command, cwd=self.path, shell=shell)

    def output_for_git_command(self, command, shell=False):
        return subprocess.check_output(command, cwd=self.path, shell=shell).splitlines()

    def is_root(self):
        return self.parent is None

    def ancestors(self):
        ancestors = []
        if not self.is_root():
            ancestors.append(self.parent)
            ancestors.extend(self.parent.ancestors())
        return ancestors

    def root_working_copy(self):
        if self.is_root():
            return self
        return self.parent

    def svn_info(self, key=None):
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
        output = subprocess.check_output('git status --porcelain'.split(), cwd=self.path).splitlines()
        dirty_files = [line for line in output if not line.startswith('?')]
        return bool(dirty_files)

    def is_git_svn(self):
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
        yield self
        for child in self.children:
            for item in child.self_and_descendants():
                yield item

    def self_or_descendants_are_dirty(self, list_dirty=False):
        dirty_working_copies = []
        for item in self.self_and_descendants():
            if item.is_dirty():
                dirty_working_copies.append(item)

        if dirty_working_copies and list_dirty:
            print >> sys.stderr, 'Dirty working copies found, please commit or stash first:'
            for wc in dirty_working_copies:
                print >> sys.stderr, wc

        return bool(dirty_working_copies)

    def traverse(self, iterator):
        if callable(getattr(iterator, "prepare_for_root", None)):
            iterator.prepare_for_root(self)

        for item in self.self_and_descendants():
            with item.chdir_to_path():
                if iterator(item) is STOP_TRAVERSAL:
                    break

    @contextlib.contextmanager
    def chdir_to_path(self):
        oldwd = os.getcwd()
        os.chdir(self.path)
        yield
        os.chdir(oldwd)

    @contextlib.contextmanager
    def switched_to_branch(self, branch_name):
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
            return STOP_TRAVERSAL

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
            return STOP_TRAVERSAL

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
            return STOP_TRAVERSAL

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

        return STOP_TRAVERSAL

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
