#!/usr/bin/env python
#

import argparse
import os
import sys
import re
import subprocess


class Tool(object):

    def __init__(self, root, add_missing_email=None):
        self.root = os.path.expanduser(root)
        self.add_missing_email = add_missing_email
    
    def run(self):
        for root, dirs, files in os.walk(self.root):
            if '.git' not in dirs:
                continue
            
            del dirs[:]
            
            email = subprocess.check_output(['git', 'config', 'user.email'], cwd=root).strip()
            if '@' not in email:
                print '*** No e-mail configured in {}'.format(root)
                if self.add_missing_email:
                    print '--> Configuring {}'.format(self.add_missing_email)
                    cmd = ['git', 'config', 'user.email', self.add_missing_email]
                    subprocess.check_output(cmd, cwd=root)
            else:
                print '{} {}'.format(email, root)
                
    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser(description='Run some checks on git working copies')
        parser.add_argument('root', help='Root in which to search for git working copies')
        parser.add_argument('--add-missing-email', help='If user.email setting is missing, configure this one')

        args = parser.parse_args()
        cls(root=args.root, add_missing_email=args.add_missing_email).run()


if __name__ == '__main__':
    Tool.main()