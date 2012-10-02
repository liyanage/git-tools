#!/usr/bin/env python

import githelper
import unittest
import subprocess


class TestFilteringPopen(unittest.TestCase):

    def test_nofilter(self):
        popen = githelper.FilteringPopen('echo $\'foo1\\nfoo2\'; echo $\'bar1\\nbar2\' 1>&2', shell=True)
        popen.run()
        self.assertEquals(popen.returncode(), 0)
        self.assertEquals(popen.stdoutlines(), ['foo1', 'foo2'])
        self.assertEquals(popen.stderrlines(), ['bar1', 'bar2'])

    def test_filter(self):
        popen = githelper.FilteringPopen('echo $\'foo1\\nfoo2\'; echo $\'bar1\\nbar2\' 1>&2', shell=True)
        rules = [
            ('-', r'^#'),
            ('-', r'1$'),
        ]
        popen.run(filter_rules=rules)
        self.assertEquals(popen.returncode(), 0)
        self.assertEquals(popen.stdoutlines(), ['foo2'])
        self.assertEquals(popen.stderrlines(), ['bar2'])

    def test_check_returncode(self):
        popen = githelper.FilteringPopen('false', shell=True)
        with self.assertRaises(Exception):
            popen.run()

        popen = githelper.FilteringPopen('false', shell=True)
        popen.run(check_returncode=False)
        self.assertEquals(popen.returncode(), 1)

    def test_progressive_output(self):
        popen = githelper.FilteringPopen('for i in $(seq 1 5); do /bin/echo $i xxxxxxxx; for j in $(seq 1 5); do echo $i $j; done; sleep 1; done', shell=True)
        rules = [
            ('-', r'^2'),
        ]
        popen.run(filter_rules=rules)
        self.assertEquals(popen.returncode(), 0)

    def test_header(self):
        popen = githelper.FilteringPopen('echo $\'foo1\\nfoo2\'; echo $\'bar1\\nbar2\' 1>&2', shell=True)
        rules = [
            ('-', r'^foo'),
            ('-', r'^bar'),
        ]
        popen.run(filter_rules=rules, header='Should not show up')

    def test_header(self):
        popen = githelper.FilteringPopen('echo $\'foo1\\nfoo2\'; echo $\'bar1\\nbar2\' 1>&2', shell=True)
        rules = [
            ('-', r'^foo'),
        ]
        popen.run(filter_rules=rules, header='Should show up')

if __name__ == '__main__':
    unittest.main()
