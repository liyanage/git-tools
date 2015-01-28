#!/usr/bin/env python

#
# Split diff into per-person sets
#
# Maintained at https://github.com/liyanage/git-tools
#

import sys
import os
import re
import argparse
import logging
import subprocess


class Patch(object):

    def __init__(self):
        self.items = []
    
    def new_item(self, path):
        class PatchItem(object):

            def __init__(self, path):
                self.path = path
                self.text = []
            
            def append_text(self, line):
                self.text.append(line)
            
            def item_text(self):
                return ''.join(self.text)
            
            def parent_directory_last_committer_for_branch(self, branch):
                parent_dir, file = os.path.split(self.path)
                cmd = ['git', 'log', '-n', '1', '--format=format:%ae', branch, '--', parent_dir]
                output = subprocess.check_output(cmd).strip()
                return output

            def last_committer_for_branch(self, branch):
                cmd = ['git', 'log', '-n', '1', '--format=format:%ae', branch, '--', self.path]
                output = subprocess.check_output(cmd).strip()
                return output
                
        item = PatchItem(path)
        self.items.append(item)
        return item
    
    def last_committer_to_item_map(self, branch):
        map = {}
        for item in self.items:
            committer = item.last_committer_for_branch(branch)
            if not committer:
                committer = '(unknown)'
            map.setdefault(committer, []).append(item)
        return map
    
    def parent_directory_last_committer_to_item_map(self, branch):
        map = {}
        for item in self.items:
            committer = item.parent_directory_last_committer_for_branch(branch)
            if not committer:
                committer = '(unknown)'
            map.setdefault(committer, []).append(item)
        return map
    
    @classmethod
    def parse_file(cls, file):
        patch = Patch()

        state = 'start'
        current_item = None
        for line in file:
            while True:
                if state == 'start':
                    match = re.match(r'diff --git a/(.+) b/\1', line)
                    if match:
                        path = match.group(1)
                        current_item = patch.new_item(path)
                        current_item.append_text(line)
                        state = 'reading_item'
                        break
                if state == 'reading_item':
                    match = re.match(r'diff --git a/(.+) b/\1', line)
                    if match:
                        state = 'start'
                        continue
                    current_item.append_text(line)
                    break
                raise Exception('unexpected input in state {}: {}'.format(state, line))

        return patch


class Tool(object):

    def __init__(self, args):
        self.args = args

    def run(self):
        cmd = ['git', 'diff', self.args.target_branch, self.args.source_branch]
        diff = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        patch = Patch.parse_file(diff.stdout)
        
        map = patch.last_committer_to_item_map(self.args.target_branch)
        author_mapping = {
            'foo@example.com': 'bar@example.com',
        }
        map = self.merge_keys(map, author_mapping)
        
        for committer, items in map.items():
            print '\n\n>>>>>>>>>>>>>>>>>>>>>>> {} {} items'.format(committer, len(items))
            for item in items:
                print item.item_text()
            print '<<<<<<<<<<<<<<<<<<<<<<<'
    
    def merge_keys(self, map, key_mapping):
        result = {}
        for key, value_list in map.items():
            result.setdefault(key_mapping.get(key, key), []).extend(value_list)
        return result

    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser(description='Description')
        parser.add_argument('source_branch', help='Source Branch')
        parser.add_argument('target_branch', help='Target Branch')
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debug logging')

        args = parser.parse_args()
        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)

        cls(args).run()


if __name__ == "__main__":
    Tool.main()
