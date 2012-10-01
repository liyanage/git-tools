#!/usr/bin/env python

import githelper
import os
import sys


class Foo:

	def __init__(self, some_state):
		self.some_state = some_state

	def __call__(self, wc):
		# possibly use self.some_state
		print wc.current_branch()	

def process(wc):
	print wc.current_branch()

# Construct a GitWorkingCopy instance with a path
root_wc = githelper.GitWorkingCopy(sys.argv[1])

# Now process this working copy and all sub working copies recursively.

# Variant 1: Iterate over instance and all its children
for wc in root_wc:
	print wc.current_branch()

# Variant 2: Pass a function to traverse(), the function gets called for and with each working copy
root_wc.traverse(process)

# Variant 3: Pass an object that implements __call__, the method gets called for and with each working copy
iterator = Foo('bar')
root_wc.traverse(iterator)


