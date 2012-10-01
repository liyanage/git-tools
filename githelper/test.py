#!/usr/bin/env python

import githelper
import unittest
import subprocess


class TestFilteringPopen(unittest.TestCase):

    def setUp(self):
        self.instance = githelper.FilteringPopen('echo $\'foo1\\nfoo2\'; echo $\'bar1\\nbar2\' 1>&2', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_popen(self):
        rules = [
            ('-', r'^#'),
            ('-', r'1$'),
        ]
        result = self.instance.communicate(filter=githelper.PopenOutputFilter(rules))
        self.assertEquals(list(result), ['foo2\n', 'bar2\n'])

    def test_popen2(self):
        rules = [
            ('+', r'1$'),
            ('-', r'.*'),
        ]
        result = self.instance.communicate(filter=githelper.PopenOutputFilter(rules))
        self.assertEquals(list(result), ['foo1\n', 'bar1\n'])

    def test_popen2(self):
        rules = [
            ('-', r'.*'),
            ('+', r'1$'),
        ]
        result = self.instance.communicate(filter=githelper.PopenOutputFilter(rules))
        self.assertEquals(list(result), ['', ''])
    

if __name__ == '__main__':
    unittest.main()
